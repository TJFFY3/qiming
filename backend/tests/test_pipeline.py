import copy
import json
from pathlib import Path
import pytest
from backend.app.config import Settings
from backend.app.store import Store, Conflict
from backend.app.pipeline import Pipeline
from backend.app.documents import DocumentEngine

SAMPLE = json.loads(Path("vendor/chemistry/examples/outline.json").read_text())


class Retriever:
    def search(self, query):
        return [
            {
                "id": "src",
                "title": "教材",
                "category": "textbook",
                "evidence": "元素化合价变化",
                "locator": "切片1",
                "verified": False,
            }
        ]


class Model:
    def __init__(self):
        self.count = 0

    def generate_json(self, messages):
        self.count += 1
        return copy.deepcopy(SAMPLE)


def setup(tmp_path, model=None):
    s = Settings(data_dir=tmp_path)
    store = Store(tmp_path / "db")
    session = store.create_session({"chapter": "氧化还原反应", "period": "第一课时"})
    return (
        store,
        session,
        Pipeline(s, store, Retriever(), model or Model(), DocumentEngine()),
    )


@pytest.mark.parametrize("allow_draft", [False, True])
def test_unverified_sources_do_not_block_generation(tmp_path, allow_draft):
    store, s, p = setup(tmp_path)
    job = p.start_generation(s["id"], {"prompt": "生成", "allow_draft": allow_draft})
    p.run(job["id"])
    done = store.get_job(job["id"])
    assert done["status"] == "completed", done
    version = store.get_session(s["id"])["versions"][-1]
    assert Path(version["directory"], "outline.docx").is_file()
    # Removing the gate must not fabricate verification of the underlying evidence.
    assert version["report"]["draft"]
    assert version["sources"][0]["verified"] is False


def test_source_gaps_and_conflicts_are_recorded_without_blocking_export(tmp_path):
    class WithGaps(Model):
        def generate_json(self, messages):
            value = super().generate_json(messages)
            value["source_gaps"] = ["教材实验细节未覆盖"]
            value["source_conflicts"] = ["参考资料描述有差异"]
            return value

    store, s, p = setup(tmp_path, WithGaps())
    job = p.start_generation(s["id"], {"prompt": "生成"})
    p.run(job["id"])
    done = store.get_job(job["id"])
    assert done["status"] == "completed", done
    version = store.get_session(s["id"])["versions"][-1]
    assert Path(version["directory"], "outline.docx").is_file()
    assert any(
        "教材实验细节未覆盖" in issue for issue in version["report"]["source_issues"]
    )


def test_repair_limit(tmp_path):
    class Bad(Model):
        def generate_json(self, messages):
            self.count += 1
            return {"outline": {"title": "bad"}}

    model = Bad()
    store, s, p = setup(tmp_path, model)
    job = p.start_generation(s["id"], {"prompt": "生成", "allow_draft": True})
    p.run(job["id"])
    assert model.count == 3
    assert store.get_job(job["id"])["status"] == "failed"
    assert not store.get_session(s["id"])["versions"]


def test_revision_and_stale_guard(tmp_path):
    model = Model()
    store, s, p = setup(tmp_path, model)
    j = p.start_generation(s["id"], {"prompt": "生成", "allow_draft": True})
    p.run(j["id"])
    v = store.get_session(s["id"])["versions"][-1]
    model.generate_json = lambda _: {
        "mode": "patch",
        "changes": [
            {
                "block_id": "question-1",
                "replacement": [{"type": "paragraph", "content": "请增加判断步骤。"}],
            }
        ],
    }
    j = p.start_revision(s["id"], {"prompt": "增加提示", "base_version_id": v["id"]})
    p.run(j["id"])
    assert store.get_job(j["id"])["status"] == "completed"
    latest = store.get_session(s["id"])["versions"][-1]
    assert latest["content"]["sections"][1:] == v["content"]["sections"][1:]
    with pytest.raises(Conflict):
        p.start_revision(s["id"], {"prompt": "stale", "base_version_id": v["id"]})


def test_full_revision_inherits_draft_even_if_title_marker_removed(tmp_path):
    model = Model()
    store, s, p = setup(tmp_path, model)
    raw = copy.deepcopy(SAMPLE)
    raw["source_gaps"] = []
    raw["outline"]["title"] = "待核验 原课时"
    source = Retriever().search("")[0]
    source["verified"] = True
    p.retriever.search = lambda _: [source]
    model.generate_json = lambda _: copy.deepcopy(raw)
    j = p.start_generation(s["id"], {"prompt": "生成", "allow_draft": True})
    p.run(j["id"])
    base = store.get_session(s["id"])["versions"][-1]
    assert base["report"]["draft"]
    changed = copy.deepcopy(raw)
    changed["mode"] = "full"
    changed["outline"]["title"] = "新课时"
    model.generate_json = lambda _: changed
    j = p.start_revision(s["id"], {"prompt": "更改标题", "base_version_id": base["id"]})
    p.run(j["id"])
    latest = store.get_session(s["id"])["versions"][-1]
    assert latest["id"] != base["id"]
    assert latest["report"]["draft"] is True


def test_completion_does_not_delete_published_artifacts(tmp_path):
    store, s, p = setup(tmp_path)
    original = store.update_job

    def fail_after_publish(job_id, **values):
        if store.get_job(job_id)["status"] == "completed":
            raise OSError("simulate DB failure")
        return original(job_id, **values)

    store.update_job = fail_after_publish
    j = p.start_generation(s["id"], {"prompt": "生成", "allow_draft": True})
    try:
        p.run(j["id"])
    except OSError:
        pass
    versions = store.get_session(s["id"])["versions"]
    assert len(versions) == 1
    assert Path(versions[0]["directory"], "outline.docx").exists()
    assert all(
        step["status"] == "completed" for step in store.get_job(j["id"])["stages"]
    )


def test_noop_revision_retries_and_does_not_publish_version(tmp_path):
    model = Model()
    store, s, p = setup(tmp_path, model)
    j = p.start_generation(s["id"], {"prompt": "生成", "allow_draft": True})
    p.run(j["id"])
    base = store.get_session(s["id"])["versions"][-1]
    first = base["content"]["sections"][0]["blocks"][0]
    calls = []

    def no_change(messages):
        calls.append(messages)
        return {
            "mode": "patch",
            "changes": [{"block_id": first["id"], "replacement": [first]}],
        }

    model.generate_json = no_change
    j = p.start_revision(s["id"], {"prompt": "增加提示", "base_version_id": base["id"]})
    p.run(j["id"])
    assert store.get_job(j["id"])["status"] == "failed"
    assert len(store.get_session(s["id"])["versions"]) == 1
    assert len(calls) == 3
    assert "实际" in store.get_job(j["id"])["error"]


def test_optimization_is_visible_in_stored_conversation_and_model_prompt(tmp_path):
    store, session, pipeline = setup(tmp_path)
    options = {
        "scope": "仅第一课时",
        "duration": "15 分钟",
        "tasks": "3 个任务",
        "difficulty": "基础为主",
        "hints": "详细提示",
        "focus": ["概念理解", "化学方程式"],
        "extra": "学生基础较弱",
    }
    store.update_session(session["id"], lambda s: s["settings"].update(options=options))
    captured = []

    def model(messages):
        captured.append(messages)
        return copy.deepcopy(SAMPLE)

    pipeline.model.generate_json = model
    job = pipeline.start_generation(session["id"], {"prompt": "以生活情境导入"})
    pipeline.run(job["id"])
    assert store.get_job(job["id"])["status"] == "completed"
    text = store.get_session(session["id"])["messages"][0]["content"]
    for line in [
        "学习范围：仅第一课时",
        "自学用时：15 分钟",
        "任务数量：3 个任务",
        "内容难度：基础为主",
        "提示详略：详细提示",
        "本课重点：概念理解、化学方程式",
        "补充要求：学生基础较弱",
    ]:
        assert line in text
        assert line in captured[0][1]["content"]
    assert text.count("【优化提示】") == 1


def test_fastgpt_wire_prompt_contains_optimization_exactly_once(tmp_path):
    import httpx
    from backend.app.model_client import ModelClient

    store, session, pipeline = setup(tmp_path)
    settings = pipeline.settings
    settings.model_provider = "fastgpt"
    settings.fastgpt_app_id = "test-app"
    settings.fastgpt_url = "https://fastgpt.test/api"
    settings.fastgpt_key = "test-only-key"
    store.update_session(
        session["id"],
        lambda s: s["settings"].update(
            options={"duration": "20 分钟", "focus": ["化学方程式"]}
        ),
    )
    sent = []

    def transport(request):
        body = json.loads(request.content)
        sent.append(body["messages"][0]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(SAMPLE, ensure_ascii=False)}}
                ]
            },
        )

    pipeline.model = ModelClient(settings, httpx.MockTransport(transport))
    job = pipeline.start_generation(session["id"], {"prompt": "请生成导学案"})
    pipeline.run(job["id"])
    assert store.get_job(job["id"])["status"] == "completed"
    assert len(sent) == 1
    assert "自学用时：20 分钟" in sent[0]
    assert "本课重点：化学方程式" in sent[0]
    assert sent[0].count("【优化提示】") == 1
