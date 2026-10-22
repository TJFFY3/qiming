import pytest
from backend.app.shared.rules.content_quality import check_student_content


def test_keeps_student_questions_and_ignores_unpublished_source_diagnostics():
    check_student_content(
        {
            "outline": {
                "goals": ["通过比较化合价，能够判断氧化还原反应。"],
                "thinking": ["改变反应条件是否影响实验现象？为什么要用空白对照？"],
                "sections": [],
            },
            "sources": [{"evidence": "反应条件采用指定condition对象，留白使用null。"}],
            "source_gaps": ["资料包含格式说明：condition对象"],
        }
    )


def test_rich_text_patch_compliance_report_is_rejected():
    with pytest.raises(
        ValueError, match=r"PROMPT_LEAK.*changes\[0\].replacement\[0\].content"
    ):
        check_student_content(
            {
                "mode": "patch",
                "changes": [
                    {
                        "replacement": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"text": "反应条件采用指定cond"},
                                    {"text": "ition对象"},
                                ],
                            }
                        ]
                    }
                ],
            }
        )


@pytest.mark.parametrize("field", ["goals", "thinking", "table"])
def test_prompt_block_is_blocked_in_all_student_content(field):
    value = "【优化提示】自学用时：20分钟【优化提示结束】"
    outline = (
        {field: [value]}
        if field != "table"
        else {
            "sections": [
                {"blocks": [{"type": "table", "headers": ["说明"], "rows": [[value]]}]}
            ]
        }
    )
    with pytest.raises(ValueError, match="PROMPT_LEAK"):
        check_student_content({"outline": outline})
