"""Regression coverage for requirement parsing and immutable question revisions."""

import copy
import json

import pytest
from fastapi.testclient import TestClient

from backend.app.timed_practice.tools.documents import validate_content
from backend.app.timed_practice.domain.requirements import resolve_requirements
from backend.tests.test_timed_practice import PREFIX, app_for, paper, settings, source


@pytest.mark.parametrize("instruction, expected", [
    ("增加1道选择题，其他题目保留", 6),
    ("减少2道选择题，其他题目保留", 3),
    ("改为3道选择题", 3),
    ("增加1道选择题，最后改为3道选择题", 3),
])
def test_quantity_changes_use_current_count_and_respect_later_absolute_count(instruction, expected):
    config = settings()
    prior = resolve_requirements(config, "")
    result = resolve_requirements(config, instruction, paper(), prior)
    assert result["choice_count"] == expected
    assert result["written_count"] == 2


@pytest.mark.parametrize("instruction", [
    "保持总用时20分钟，选择题每题1分钟，解答题每题5分钟",
    "每道题1分钟，总用时20分钟",
    "选择题按1分钟/题安排",
    "每题用时1分钟",
    "每道题限时1分钟",
])
def test_question_estimates_do_not_override_total_duration(instruction):
    result = resolve_requirements(settings(), instruction)
    assert result["duration"] == 20


def test_explicit_total_after_question_estimate_in_same_clause_is_respected():
    result = resolve_requirements(settings(), "每题1分钟但总用时改为30分钟")
    assert result["duration"] == 30


def test_repeated_relative_changes_and_followup_keep_the_latest_count():
    config = settings()
    prior = resolve_requirements(config, "")
    current = paper()
    first = resolve_requirements(config, "增加1道选择题", current, prior)
    current["choice"].append(copy.deepcopy(current["choice"][0]))
    second = resolve_requirements(config, "再增加1道选择题", current, first)
    assert second["choice_count"] == 7
    current["choice"].append(copy.deepcopy(current["choice"][0]))
    followup = resolve_requirements(config, "只修改第1题解析", current, second)
    assert followup["choice_count"] == 7


def test_legacy_requirements_without_setting_marker_use_actual_question_count():
    config = settings()
    prior = resolve_requirements(config, "")
    prior.pop("question_setting", None)
    prior["choice_count"] = 6
    current = paper()
    current["choice"].append(copy.deepcopy(current["choice"][0]))
    assert resolve_requirements(config, "增加1道选择题", current, prior)["choice_count"] == 7
    assert resolve_requirements(config, "只修改第1题解析", current, prior)["choice_count"] == 6


@pytest.mark.parametrize("wrapped", [False, True])
def test_duplicate_questions_are_rejected_after_serialized_run_decoding(wrapped):
    raw = paper()
    serialized = json.dumps([{"text": raw["choice"][0]["stem"]}], ensure_ascii=False)
    raw["choice"][1]["stem"] = [{"text": serialized}] if wrapped else serialized
    with pytest.raises(ValueError, match="题干重复"):
        validate_content(raw, resolve_requirements(settings(), ""), [source()])


def initial(client):
    sid = client.post(PREFIX + "/sessions", json=settings()).json()["id"]
    job = client.post(f"{PREFIX}/sessions/{sid}/generate", json={}).json()
    assert client.get(PREFIX + "/jobs/" + job["id"]).json()["status"] == "completed"
    return sid, client.get(f"{PREFIX}/sessions/{sid}").json()["versions"][-1]


@pytest.mark.parametrize("prompt", [
    "只修改第1题解析，其他题目保持不变", "只修改第一题解析", "修改第1题解析",
])
def test_targeted_revision_rejects_unrelated_question_edits(tmp_path, prompt):
    bad = paper()
    bad["choice"][0]["explanation"] = "第一题的新解析。"
    bad["choice"][1]["stem"] = "第二题被意外重写。"
    with TestClient(app_for(tmp_path, [paper(), bad, bad, bad])) as client:
        sid, base = initial(client)
        job = client.post(f"{PREFIX}/sessions/{sid}/revise", json={
            "prompt": prompt, "base_version_id": base["id"],
        }).json()
        done = client.get(PREFIX + "/jobs/" + job["id"]).json()
        assert done["status"] == "failed"
        assert "指定" in done["error"]
        assert client.get(f"{PREFIX}/sessions/{sid}").json()["versions"] == [base]
        assert len(list((tmp_path / "timed-practice" / sid / "versions").iterdir())) == 1


def test_targeted_revision_repairs_scope_and_preserves_other_groups(tmp_path):
    bad = paper()
    bad["choice"][0]["explanation"] = "不应修改的第一题。"
    bad["written"][0]["explanation"] = "修订后的第六题解析。"
    fixed = paper()
    fixed["written"][0]["explanation"] = "修订后的第六题解析。"
    with TestClient(app_for(tmp_path, [paper(), bad, fixed])) as client:
        sid, base = initial(client)
        job = client.post(f"{PREFIX}/sessions/{sid}/revise", json={
            "prompt": "只修改第6题解析", "base_version_id": base["id"],
        }).json()
        done = client.get(PREFIX + "/jobs/" + job["id"]).json()
        assert done["status"] == "completed", done
        versions = client.get(f"{PREFIX}/sessions/{sid}").json()["versions"]
        assert versions[0] == base
        assert versions[-1]["content"]["choice"] == base["content"]["choice"]
        assert versions[-1]["content"]["written"][1] == base["content"]["written"][1]
        assert versions[-1]["content"]["written"][0]["explanation"] != base["content"]["written"][0]["explanation"]


def test_adding_one_question_can_publish_six_choices(tmp_path):
    revised = paper()
    extra = copy.deepcopy(revised["choice"][0])
    extra["stem"] = "新增的第六道选择题。"
    revised["choice"].append(extra)
    for question in revised["written"]:
        question["score"] = 13
    with TestClient(app_for(tmp_path, [paper(), revised, revised, revised])) as client:
        sid, base = initial(client)
        job = client.post(f"{PREFIX}/sessions/{sid}/revise", json={
            "prompt": "增加1道选择题，满分仍为50分，调整解答题分值", "base_version_id": base["id"],
        }).json()
        done = client.get(PREFIX + "/jobs/" + job["id"]).json()
        assert done["status"] == "completed", done
        assert done["effective_requirements"]["choice_count"] == 6
        assert len(client.get(f"{PREFIX}/sessions/{sid}").json()["versions"][-1]["content"]["choice"]) == 6


@pytest.mark.parametrize("prompt", [
    "第2题不要修改，只修改第1题解析", "第1、2题不改，只修改第3题",
])
def test_suffix_preservation_blocks_unrelated_edits(prompt):
    from backend.app.timed_practice.domain.revision import validate_revision_scope

    before = paper()
    after = copy.deepcopy(before)
    after["choice"][1]["stem"] = "不应修改的第二题"
    with pytest.raises(ValueError, match="指定"):
        validate_revision_scope(after, before, prompt)


def test_preservation_before_another_edit_does_not_block_the_requested_question():
    from backend.app.timed_practice.domain.revision import validate_revision_scope

    before = paper()
    after = copy.deepcopy(before)
    after["choice"][0]["explanation"] = "新解析"
    validate_revision_scope(after, before, "保留第2题并修改第1题解析")


def test_legacy_session_can_still_explicitly_change_dialog_question_setting(tmp_path):
    revised = paper()
    revised["choice"].pop()
    for question in revised["written"]:
        question["score"] = 17
    app = app_for(tmp_path, [paper(), revised, revised, revised])
    with TestClient(app) as client:
        sid, base = initial(client)
        def legacy(session):
            session["versions"][-1]["requirements"].pop("question_setting", None)
        app.state.practice_store.change_idle(sid, legacy)
        config = settings()
        config["options"]["questions"] = "4道选择题和2道解答题"
        assert client.patch(f"{PREFIX}/sessions/{sid}", json=config).status_code == 200
        job = client.post(f"{PREFIX}/sessions/{sid}/revise", json={
            "prompt": "按当前题量设置调整练习", "base_version_id": base["id"],
        }).json()
        done = client.get(PREFIX + "/jobs/" + job["id"]).json()
        assert done["status"] == "completed", done
        assert done["effective_requirements"]["choice_count"] == 4
