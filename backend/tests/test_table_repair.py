import copy
import pytest
from backend.app.study_guide.domain.table_repair import (
    repair_empty_headers,
    header_target,
    apply_header_repair,
)


def document(headers, rows):
    return {
        "outline": {
            "sections": [
                {
                    "blocks": [
                        {
                            "id": "table",
                            "type": "table",
                            "headers": headers,
                            "rows": rows,
                        }
                    ]
                }
            ]
        }
    }


@pytest.mark.parametrize("blank", ["", None, " \n ", [], [{"text": " "}]])
def test_empty_answer_column_gets_safe_label_without_changing_cells(blank):
    raw = document(["项目", blank], [["判断反应类型", None]])
    before = copy.deepcopy(raw)
    repaired, notes = repair_empty_headers(raw)
    assert repaired["outline"]["sections"][0]["blocks"][0]["headers"] == [
        "项目",
        "填写内容",
    ]
    assert (
        repaired["outline"]["sections"][0]["blocks"][0]["rows"]
        == before["outline"]["sections"][0]["blocks"][0]["rows"]
    )
    assert raw == before and notes[0]["method"] == "automatic"


def test_ambiguous_nonempty_column_is_left_for_targeted_model_repair():
    raw = document(["", "变化"], [["钠", "0→+1"]])
    repaired, notes = repair_empty_headers(raw)
    assert repaired == raw and notes == []
    target = header_target(raw)
    fixed, note = apply_header_repair(raw, target, {"headers": ["元素", "变化"]})
    assert fixed["outline"]["sections"][0]["blocks"][0]["headers"] == ["元素", "变化"]
    assert note["method"] == "model"
    assert (
        fixed["outline"]["sections"][0]["blocks"][0]["rows"]
        == raw["outline"]["sections"][0]["blocks"][0]["rows"]
    )


def test_local_repair_cannot_change_existing_labels_or_column_count():
    raw = document(["", "变化"], [["钠", "0→+1"]])
    for response in [
        {"headers": ["元素"]},
        {"headers": ["元素", "答案"]},
        {"headers": ["元素", "变化"], "rows": []},
        {"headers": ["", "变化"]},
    ]:
        with pytest.raises(ValueError):
            apply_header_repair(raw, header_target(raw), response)


def test_patch_table_can_be_repaired_without_modifying_other_changes():
    raw = {
        "mode": "patch",
        "changes": [
            {
                "block_id": "t",
                "replacement": [
                    {
                        "type": "table",
                        "headers": ["项目", None],
                        "rows": [["任务", None]],
                    }
                ],
            },
            {
                "block_id": "p",
                "replacement": [{"type": "paragraph", "content": "保留此修改"}],
            },
        ],
    }
    fixed, notes = repair_empty_headers(raw)
    assert fixed["changes"][0]["replacement"][0]["headers"] == ["项目", "填写内容"]
    assert fixed["changes"][1] == raw["changes"][1] and len(notes) == 1


def test_bad_row_width_is_never_silently_repaired():
    raw = document(["项目", ""], [["任务"]])
    fixed, notes = repair_empty_headers(raw)
    assert fixed == raw and notes == []


@pytest.mark.parametrize(
    "existing",
    [
        [{"text": "变化的元素", "bold": True, "charge": False}],
        [{"text": "反应条件", "condition": True}],
        [{"text": "Na", "isotope": {"mass": 23, "atomic": 11}}],
    ],
)
def test_targeted_repair_preserves_existing_rich_text_headers(existing):
    raw = document(["", existing], [["钠", "0→+1"]])
    fixed, _ = apply_header_repair(
        raw, header_target(raw), {"headers": ["元素", copy.deepcopy(existing)]}
    )
    assert fixed["outline"]["sections"][0]["blocks"][0]["headers"][1] == existing
