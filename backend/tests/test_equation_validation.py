import pytest

from backend.app.equation_validation import (
    validate_outline,
    validate_practice,
    validate_study_guide_result,
)


def test_final_validation_rejects_unbalanced_equations_and_accepts_balanced_ones():
    with pytest.raises(ValueError, match="原子数不守恒"):
        validate_outline(
            {
                "sections": [
                    {"blocks": [{"type": "paragraph", "content": "H2 + O2 = H2O"}]}
                ]
            }
        )

    validate_outline(
        {
            "sections": [
                {"blocks": [{"type": "paragraph", "content": "2H2 + O2 = 2H2O"}]}
            ]
        }
    )


def test_latex_subscript_markers_do_not_bypass_atom_balance_validation():
    with pytest.raises(ValueError, match="原子数不守恒"):
        validate_outline(
            {
                "sections": [
                    {"blocks": [{"type": "paragraph", "content": "[H_2]+[O_2]=[H_2O]"}]}
                ]
            }
        )


def test_final_validation_checks_study_guide_patch_replacements():
    with pytest.raises(ValueError, match="原子数不守恒"):
        validate_study_guide_result(
            {
                "mode": "patch",
                "changes": [
                    {
                        "block_id": "reaction",
                        "replacement": [
                            {"type": "paragraph", "content": "Cu + O2 = CuO"}
                        ],
                    }
                ],
            }
        )


def test_final_validation_checks_practice_stems_answers_and_options():
    with pytest.raises(ValueError, match="限时练习choice第1题stem"):
        validate_practice(
            {
                "choice": [
                    {
                        "stem": "H2 + O2 = H2O",
                        "answer": "A",
                        "explanation": "检查配平。",
                        "options": ["2H2 + O2 = 2H2O"],
                    }
                ]
            }
        )
