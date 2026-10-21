"""Regressions for the study-guide review: real persistence and Word output."""

import copy
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree

from backend.tests.test_pipeline import SAMPLE, setup


def generate(store, session, pipeline):
    job = pipeline.start_generation(session["id"], {"prompt": "生成"})
    pipeline.run(job["id"])
    assert store.get_job(job["id"])["status"] == "completed"
    return store.get_session(session["id"])["versions"][-1]


def patch(content="补充实验注意事项。"):
    return {"mode": "patch", "changes": [{
        "block_id": "question-1",
        "replacement": [{"type": "paragraph", "content": content}],
    }]}


SERIALIZED = json.dumps([
    {"text": "2[H2] + [O2] "},
    {"text": "点燃", "condition": True},
    {"text": " 2[H2O]"},
], ensure_ascii=False)


@pytest.mark.parametrize("field", ["paragraph", "goals", "thinking", "header", "cell"])
def test_serialized_runs_become_native_content_and_word(tmp_path, field):
    store, session, pipeline = setup(tmp_path)
    raw = copy.deepcopy(SAMPLE)
    outline = raw["outline"]
    if field in ("goals", "thinking"):
        outline[field] = [SERIALIZED]
    elif field == "paragraph":
        outline["sections"][0]["blocks"][0]["content"] = SERIALIZED
    else:
        table = outline["sections"][0]["blocks"][1]
        if field == "header":
            table["headers"][0] = SERIALIZED
        else:
            table["rows"][0][0] = SERIALIZED
    pipeline.model.generate_json = lambda _: copy.deepcopy(raw)
    version = generate(store, session, pipeline)
    text = json.dumps(version["content"], ensure_ascii=False)
    assert '\\"condition\\"' not in text
    with ZipFile(Path(version["directory"]) / "outline.docx") as archive:
        xml = archive.read("word/document.xml").decode()
    assert '"condition"' not in xml and '"text"' not in xml
    root = etree.fromstring(xml.encode())
    assert root.xpath(
        '//w:instrText[contains(text(), "点燃")]',
        namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"},
    )


def test_serialized_patch_is_normalized_before_revision_export(tmp_path):
    store, session, pipeline = setup(tmp_path)
    base = generate(store, session, pipeline)
    pipeline.model.generate_json = lambda _: patch(SERIALIZED)
    job = pipeline.start_revision(session["id"], {
        "prompt": "补充氢气燃烧方程式", "base_version_id": base["id"],
    })
    pipeline.run(job["id"])
    assert store.get_job(job["id"])["status"] == "completed"
    latest = store.get_session(session["id"])["versions"][-1]
    runs = latest["content"]["sections"][0]["blocks"][0]["content"]
    assert isinstance(runs, list)
    assert any(r.get("condition") and r["text"] == "点燃" for r in runs)


@pytest.mark.parametrize("mode", ["patch", "full"])
def test_revision_uses_current_uploads_and_persists_matching_source_snapshot(tmp_path, mode):
    store, session, pipeline = setup(tmp_path)
    base = generate(store, session, pipeline)
    original = (Path(base["directory"]) / "source_input.json").read_bytes()
    uploaded = {"id": "new", "title": "补充材料", "category": "textbook",
                "locator": "上传原文件（页码见摘录，非印刷页码）", "verified": False,
                "text": "实验需要干燥氯气。", "evidence": "实验需要干燥氯气。",
                "file_path": "/private/upload", "pages": []}
    store.update_session(session["id"], lambda s: s["resources"].append(uploaded))
    seen = []

    def model(messages):
        seen.append(json.loads(messages[1]["content"]))
        if mode == "patch":
            return patch()
        raw = copy.deepcopy(SAMPLE)
        raw.update(mode="full")
        raw["outline"]["title"] = "修改后的标题"
        return raw

    pipeline.model.generate_json = model
    job = pipeline.start_revision(session["id"], {
        "prompt": "根据新上传资料修改", "base_version_id": base["id"],
    })
    pipeline.run(job["id"])
    assert store.get_job(job["id"])["status"] == "completed"
    assert {s["id"] for s in seen[0]["sources"]} == {"src", "new"}
    assert "干燥氯气" in json.dumps(seen[0], ensure_ascii=False)
    assert "/private/upload" not in json.dumps(seen[0])
    latest = store.get_session(session["id"])["versions"][-1]
    saved = json.loads((Path(latest["directory"]) / "source_input.json").read_text())
    assert latest["sources"] == saved["sources"]
    assert {s["id"] for s in saved["sources"]} == {"src", "new"}
    assert (Path(base["directory"]) / "source_input.json").read_bytes() == original


def test_revision_selects_relevant_text_beyond_source_prefix_without_losing_snapshot(tmp_path):
    store, session, pipeline = setup(tmp_path)
    evidence = "教材前言。" * 5000 + "氯气干燥实验：必须使用浓硫酸，不得使用碱石灰。" + "附录。" * 5000
    pipeline.retriever.search = lambda _: [{
        "id": "src", "title": "教材", "category": "textbook", "locator": "切片1",
        "verified": False, "evidence": evidence,
    }]
    base = generate(store, session, pipeline)
    contexts = []

    def model(messages):
        contexts.append(json.loads(messages[1]["content"]))
        return patch()

    pipeline.model.generate_json = model
    job = pipeline.start_revision(session["id"], {
        "prompt": "补充氯气干燥实验的试剂选择", "base_version_id": base["id"],
    })
    pipeline.run(job["id"])
    assert store.get_job(job["id"])["status"] == "completed"
    assert "必须使用浓硫酸，不得使用碱石灰" in json.dumps(contexts[0], ensure_ascii=False)
    assert len(json.dumps(contexts[0]["sources"], ensure_ascii=False)) < 16000
    assert store.get_session(session["id"])["versions"][-1]["sources"][0]["evidence"] == evidence


@pytest.mark.parametrize("bad_section", [None, 42, "错误章节"])
def test_invalid_sections_enter_content_repair_instead_of_aborting(tmp_path, bad_section):
    store, session, pipeline = setup(tmp_path)
    requests = []

    def model(messages):
        requests.append(copy.deepcopy(messages))
        raw = copy.deepcopy(SAMPLE)
        if len(requests) == 1:
            raw["outline"]["sections"] = [bad_section]
        return raw

    pipeline.model.generate_json = model
    generate(store, session, pipeline)
    assert len(requests) == 2
    assert "sections" in requests[1][-1]["content"]


def test_invalid_rich_runs_enter_repair_instead_of_aborting(tmp_path):
    store, session, pipeline = setup(tmp_path)
    requests = []

    def model(messages):
        requests.append(copy.deepcopy(messages))
        raw = copy.deepcopy(SAMPLE)
        if len(requests) == 1:
            raw["outline"]["goals"] = [[None]]
        return raw

    pipeline.model.generate_json = model
    generate(store, session, pipeline)
    assert len(requests) == 2


@pytest.mark.parametrize("legacy", [False, True])
def test_revision_does_not_restore_deleted_uploads_from_history(tmp_path, legacy):
    store, session, pipeline = setup(tmp_path)
    # Enable retrieval alongside uploads; Retriever is the local fixture above.
    pipeline.settings.fastgpt_url = "https://kb.test"
    upload = {"id": "upload", "title": "旧资料", "category": "textbook",
              "locator": "上传原文件（页码见摘录，非印刷页码）", "verified": False,
              "text": "已删除的参考内容", "evidence": "已删除的参考内容"}
    store.update_session(session["id"], lambda s: s["resources"].append(upload))
    base = generate(store, session, pipeline)
    if legacy:
        def strip_marker(s):
            for source in s["versions"][-1]["sources"]:
                source.pop("source_type", None)
        store.update_session(session["id"], strip_marker)
    store.delete_resource(session["id"], "upload")
    pipeline.model.generate_json = lambda _: patch()
    job = pipeline.start_revision(session["id"], {
        "prompt": "补充实验注意事项", "base_version_id": base["id"],
    })
    pipeline.run(job["id"])
    assert store.get_job(job["id"])["status"] == "completed"
    versions = store.get_session(session["id"])["versions"]
    assert {s["id"] for s in versions[-1]["sources"]} == {"src"}
    assert {s["id"] for s in versions[0]["sources"]} == {"src", "upload"}
    assert json.loads((Path(versions[-1]["directory"]) / "source_input.json").read_text())["sources"] == versions[-1]["sources"]


def test_revision_context_shares_budget_and_keeps_short_sources_whole():
    from backend.app.study_guide_context import revision_source_context

    sources = [
        {"id": "short", "evidence": "氯气干燥应使用浓硫酸。"},
        {"id": "long1", "evidence": "教材前言。" * 6000 + "氯气干燥：不得使用碱石灰。"},
        {"id": "long2", "evidence": "教材目录。" * 6000 + "氯气干燥：装置应保持气密。"},
    ]
    before = copy.deepcopy(sources)
    excerpts = revision_source_context(sources, "补充氯气干燥实验")
    assert excerpts[0]["evidence_excerpt"] == "氯气干燥应使用浓硫酸。"
    assert not excerpts[0]["excerpt_truncated"]
    assert "不得使用碱石灰" in excerpts[1]["evidence_excerpt"]
    assert "装置应保持气密" in excerpts[2]["evidence_excerpt"]
    assert sum(len(s["evidence_excerpt"]) for s in excerpts) <= 12000
    assert sources == before


def test_revision_context_uses_explicit_optimization_requirements():
    from backend.app.study_guide_context import revision_source_context

    evidence = "教材前言。" * 6000 + "氯气干燥：必须使用浓硫酸，不得使用碱石灰。" + "附录。" * 6000
    prompt = "优化导学案\n\n【优化提示】\n本课重点：氯气干燥\n补充要求：补充实验试剂选择\n【优化提示结束】"
    result = revision_source_context([{"id": "src", "evidence": evidence}], prompt)
    assert "必须使用浓硫酸，不得使用碱石灰" in result[0]["evidence_excerpt"]


def test_patch_revision_keeps_new_source_gaps_and_conflicts_in_saved_report(tmp_path):
    store, session, pipeline = setup(tmp_path)
    base = generate(store, session, pipeline)
    source_path = Path(base["directory"]) / "source_input.json"
    original = source_path.read_bytes()
    raw = patch()
    raw["source_gaps"] = ["新增材料未说明实验温度"]
    raw["source_conflicts"] = ["新旧资料反应温度不一致"]
    pipeline.model.generate_json = lambda _: copy.deepcopy(raw)
    job = pipeline.start_revision(session["id"], {
        "prompt": "补充实验注意事项", "base_version_id": base["id"],
    })
    pipeline.run(job["id"])
    assert store.get_job(job["id"])["status"] == "completed"
    latest = store.get_session(session["id"])["versions"][-1]
    saved = json.loads((Path(latest["directory"]) / "source_input.json").read_text())
    assert "新增材料未说明实验温度" in saved["source_gaps"]
    assert "新旧资料反应温度不一致" in saved["source_conflicts"]
    assert set(json.loads(original)["source_gaps"]) <= set(saved["source_gaps"])
    assert any("新增材料未说明实验温度" in x for x in latest["report"]["source_issues"])
    assert any("新旧资料反应温度不一致" in x for x in latest["report"]["source_issues"])
    assert source_path.read_bytes() == original
