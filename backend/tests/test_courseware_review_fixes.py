"""Review regressions through real storage, revision merging and PPT downloads."""

import copy
import io
import json
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from lxml import etree

from backend.tests.test_courseware import PREFIX, app_for, deck


def initial(client):
    sid = client.post(PREFIX + "/sessions", json={}).json()["id"]
    job = client.post(f"{PREFIX}/sessions/{sid}/generate", json={}).json()
    assert client.get(PREFIX + "/jobs/" + job["id"]).json()["status"] == "completed"
    return sid, client.get(f"{PREFIX}/sessions/{sid}").json()["versions"][-1]


def revise(client, sid, base, prompt, **extra):
    job = client.post(f"{PREFIX}/sessions/{sid}/revise", json={
        "prompt": prompt, "base_version_id": base["id"], **extra,
    }).json()
    return client.get(PREFIX + "/jobs/" + job["id"]).json()


@pytest.mark.parametrize("prompt", ["只修改第1页", "修改第1页", "只修改封面", "只修改第一页"])
def test_page_scope_is_enforced_without_special_preservation_phrase(tmp_path, prompt):
    changed = copy.deepcopy(deck()["slides"][1])
    changed["paragraphs"] = ["不应修改的第二页"]
    bad = {"mode": "patch", "changes": [{"page": 2, "slide": changed}]}
    app, requests = app_for(tmp_path, [deck(), bad, bad, bad])
    with TestClient(app) as client:
        sid, base = initial(client)
        done = revise(client, sid, base, prompt)
        assert done["status"] == "failed"
        assert "指定页面之外" in done["error"]
        assert client.get(f"{PREFIX}/sessions/{sid}").json()["versions"] == [base]
        assert sum("messages" in r for r in requests) == 4


@pytest.mark.parametrize("prompt", ["只修改第1、2页", "只修改第1至2页"])
def test_multi_page_scope_rejects_pages_outside_list_or_range(prompt):
    from backend.app.courseware.domain.revision import merge_revision

    previous = deck()
    previous["slides"].append(copy.deepcopy(previous["slides"][0]))
    raw = {"mode": "patch", "changes": [{"page": 3, "slide": previous["slides"][0]}]}
    with pytest.raises(ValueError, match="指定页面之外"):
        merge_revision(raw, previous, prompt)


@pytest.mark.parametrize("prompt", [
    "修改第1、2页", "修改第一至第二页", "修改第1页和第2页", "修改第1页到第3页",
])
def test_multi_page_scope_accepts_requested_pages_and_keeps_other_pages(prompt):
    from backend.app.courseware.domain.revision import merge_revision

    previous = deck()
    previous["slides"].append(copy.deepcopy(previous["slides"][0]))
    changed = copy.deepcopy(previous["slides"][1])
    changed["paragraphs"] = ["修改第二页内容"]
    raw = {"mode": "patch", "changes": [{"page": 2, "slide": changed}]}
    content = merge_revision(raw, previous, prompt)
    assert content["slides"][1]["paragraphs"] == ["修改第二页内容"]
    assert content["slides"][0] == previous["slides"][0]
    assert content["slides"][2] == previous["slides"][2]


@pytest.mark.parametrize("prompt", [
    "只修改第2页，封面保持不变", "只修改第2页，不改封面", "只修改第2页，保留第1页",
])
def test_preservation_mentions_do_not_authorize_extra_page_changes(prompt):
    from backend.app.courseware.domain.revision import merge_revision

    changed = copy.deepcopy(deck()["slides"][0])
    changed["paragraphs"] = ["误改封面"]
    raw = {"mode": "patch", "changes": [{"page": 1, "slide": changed}]}
    with pytest.raises(ValueError, match="指定页面之外"):
        merge_revision(raw, deck(), prompt)


@pytest.mark.parametrize("mode", ["patch", "full"])
def test_unchanged_revision_retries_then_fails_without_publishing(tmp_path, mode):
    raw = ({"mode": "full", "deck": deck()} if mode == "full" else {
        "mode": "patch", "changes": [{"page": 1, "slide": deck()["slides"][0]}],
    })
    app, requests = app_for(tmp_path, [deck(), raw, raw, raw])
    with TestClient(app) as client:
        sid, base = initial(client)
        done = revise(client, sid, base, "补充实验安全提醒", allow_full_revision=mode == "full")
        assert done["status"] == "failed"
        assert "没有实际内容变化" in done["error"]
        assert len(client.get(f"{PREFIX}/sessions/{sid}").json()["versions"]) == 1
        assert len(list((tmp_path / "courseware" / sid / "versions").iterdir())) == 1
        assert sum("messages" in r for r in requests) == 4


def test_noop_repair_can_publish_a_real_change(tmp_path):
    unchanged = {"mode": "patch", "changes": [{"page": 1, "slide": deck()["slides"][0]}]}
    changed = copy.deepcopy(unchanged)
    changed["changes"][0]["slide"]["paragraphs"] = ["实验时佩戴护目镜。"]
    app, requests = app_for(tmp_path, [deck(), unchanged, changed])
    with TestClient(app) as client:
        sid, base = initial(client)
        done = revise(client, sid, base, "给第1页补充实验安全提醒")
        assert done["status"] == "completed", done
        latest = client.get(f"{PREFIX}/sessions/{sid}").json()["versions"][-1]
        assert latest["content"]["slides"][0]["paragraphs"] == ["实验时佩戴护目镜。"]
        assert latest["content"]["slides"][1] == base["content"]["slides"][1]
        assert sum("messages" in r for r in requests) == 3


@pytest.mark.parametrize("mode", ["patch", "full"])
def test_total_title_revision_updates_downloaded_cover_and_preserves_history(tmp_path, mode):
    raw = ({"mode": "full", "deck": deck("氯气的性质")} if mode == "full" else {
        "mode": "patch", "title": "氯气的性质", "changes": [],
    })
    app, _ = app_for(tmp_path, [deck(), raw])
    with TestClient(app) as client:
        sid, base = initial(client)
        url = f"{PREFIX}/sessions/{sid}/versions/{base['id']}/files/pptx"
        original = client.get(url).content
        done = revise(client, sid, base, "将课件总标题改为氯气的性质", allow_full_revision=mode == "full")
        assert done["status"] == "completed", done
        latest = client.get(f"{PREFIX}/sessions/{sid}").json()["versions"][-1]
        assert latest["content"]["title"] == "氯气的性质"
        assert latest["content"]["slides"][0]["title"] == "氯气的性质"
        data = client.get(f"{PREFIX}/sessions/{sid}/versions/{latest['id']}/files/pptx").content
        with ZipFile(io.BytesIO(data)) as archive:
            root = etree.fromstring(archive.read("ppt/slides/slide1.xml"))
        ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
        assert "氯气的性质" in root.xpath("//a:t/text()", namespaces=ns)
        assert latest["content"]["slides"][1:] == base["content"]["slides"][1:]
        assert client.get(url).content == original


def test_total_title_cannot_bypass_scope_that_excludes_cover(tmp_path):
    raw = {"mode": "patch", "title": "越界改写封面", "changes": []}
    app, _ = app_for(tmp_path, [deck(), raw, raw, raw])
    with TestClient(app) as client:
        sid, base = initial(client)
        done = revise(client, sid, base, "只修改第2页")
        assert done["status"] == "failed"
        assert len(client.get(f"{PREFIX}/sessions/{sid}").json()["versions"]) == 1


def test_patch_source_warnings_are_merged_into_content_and_report(tmp_path):
    baseline = deck()
    baseline["source_gaps"] = ["原教材缺少装置图"]
    baseline["conflicts"] = ["原资料描述存在差异"]
    raw = {"mode": "patch", "changes": [],
           "source_gaps": ["新增材料未说明实验温度", "原教材缺少装置图"],
           "conflicts": ["新旧材料温度不一致"]}
    app, requests = app_for(tmp_path, [baseline, raw, raw, raw])
    with TestClient(app) as client:
        sid, base = initial(client)
        done = revise(client, sid, base, "补充实验温度；资料不足时如实记录")
        assert done["status"] == "completed", done
        versions = client.get(f"{PREFIX}/sessions/{sid}").json()["versions"]
        latest = versions[-1]
        assert latest["content"]["source_gaps"] == ["原教材缺少装置图", "新增材料未说明实验温度"]
        assert latest["report"]["conflicts"] == ["原资料描述存在差异", "新旧材料温度不一致"]
        assert "新增材料未说明实验温度" in latest["report"]["source_issues"]
        saved = json.loads((tmp_path / "courseware" / sid / "versions" / latest["id"] / "content.json").read_text())
        assert saved == latest["content"]
        assert latest["content"]["slides"] == base["content"]["slides"]
        assert versions[0] == base
        assert sum("messages" in r for r in requests) == 2


@pytest.mark.parametrize("field", ["source_gaps", "conflicts"])
def test_revision_can_accumulate_warnings_beyond_one_response_limit(tmp_path, field):
    baseline = deck()
    baseline[field] = [f"原资料说明{i}" for i in range(30)]
    raw = {"mode": "patch", "changes": [], field: ["新增资料说明"]}
    app, _ = app_for(tmp_path, [baseline, raw, raw, raw])
    with TestClient(app) as client:
        sid, base = initial(client)
        done = revise(client, sid, base, "结合新资料记录缺口与冲突")
        assert done["status"] == "completed", done
        latest = client.get(f"{PREFIX}/sessions/{sid}").json()["versions"][-1]
        assert latest["content"][field] == baseline[field] + ["新增资料说明"]
