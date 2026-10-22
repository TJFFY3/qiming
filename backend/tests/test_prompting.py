from backend.app.study_guide.domain.models import SessionInput
from backend.app.study_guide.llm.prompts import compose_prompt, instruction_text
from backend.app.courseware.domain.models import CoursewareSettings
from backend.app.courseware.storage.store import CoursewareStore
from backend.app.timed_practice.domain.models import LessonSettings
from backend.app.timed_practice.storage.store import PracticeStore
import pytest


def test_requested_lesson_order_is_used_without_duplication():
    settings = SessionInput(chapter="钠及其化合物").model_dump()
    settings["options"]["duration"] = "20 分钟"
    text = compose_prompt("请根据本课内容生成一份导学案。", settings)
    assert text.startswith(
        "请根据本课内容生成一份导学案。\n\n学科：化学\n教材版本：人教版 必修第一册\n年级：高一\n章节 / 知识点：钠及其化合物\n课时：第一课时\n【优化提示】"
    )
    assert "自学用时：20 分钟" in text
    assert compose_prompt(text, settings) == text
    assert instruction_text(text) == "请根据本课内容生成一份导学案。"


@pytest.mark.parametrize("agent", ["courseware", "practice"])
def test_agent_submission_stores_the_same_complete_prompt_for_history_and_execution(
    tmp_path, agent
):
    if agent == "courseware":
        store = CoursewareStore(tmp_path / "courseware.sqlite")
        settings = CoursewareSettings().model_dump()
        marker, end, label = "【课件优化提示】", "【课件优化结束】", "课堂时长"
    else:
        store = PracticeStore(tmp_path / "practice.sqlite")
        settings = LessonSettings().model_dump()
        marker, end, label = "【限时练习优化设置】", "【限时练习优化设置结束】", "用时"
    session = store.create_session(settings)
    prompt = f"请增加分层任务。\n\n{marker}\n{label}：25 分钟\n{end}"
    payload = {"prompt": prompt, "kind": "generation"}
    job = (
        store.reserve(session["id"], payload, "generation")
        if agent == "courseware"
        else store.create_job(session["id"], payload)
    )
    stored = job["request"]["prompt"]
    assert stored.startswith(
        "请增加分层任务。\n\n学科：化学\n教材版本：人教版 必修第一册\n年级：高一\n章节 / 知识点：第三节 氧化还原反应\n课时：第一课时\n"
        + marker
    )
    assert f"{label}：25 分钟" in stored
    assert store.get_session(session["id"])["messages"][-1]["content"] == stored
    store.recover_jobs()
    repeated = {"prompt": stored, "kind": "generation"}
    retry = (
        store.reserve(session["id"], repeated, "generation")
        if agent == "courseware"
        else store.create_job(session["id"], repeated)
    )
    assert retry["request"]["prompt"] == stored
