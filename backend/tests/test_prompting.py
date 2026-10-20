from backend.app.models import SessionInput
from backend.app.prompting import compose_prompt, instruction_text


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
