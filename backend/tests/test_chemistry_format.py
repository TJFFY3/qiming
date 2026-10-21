import copy

from backend.app.chemistry_format import normalize_chemistry


def test_legacy_equation_becomes_semantic_runs_without_changing_evidence():
    value = {
        "outline": {
            "sections": [
                {
                    "blocks": [
                        {
                            "type": "table",
                            "headers": ["反应"],
                            "rows": [["<br>CaCO3 ===高温=== CaO + CO2↑"]],
                        }
                    ]
                }
            ]
        },
        "sources": [{"evidence": "CaCO3 ===高温=== CaO + CO2↑"}],
    }
    before = copy.deepcopy(value)
    result, notes = normalize_chemistry(value)
    assert result["outline"]["sections"][0]["blocks"][0]["rows"][0][0] == [
        {"text": "\n[CaCO3] "},
        {"text": "高温", "condition": True},
        {"text": " [CaO] + [CO2]↑"},
    ]
    assert result["sources"] == before["sources"]
    assert value == before
    assert notes
    assert normalize_chemistry(result) == (result, [])


def test_patch_runs_keep_styles_coefficients_and_existing_formula_markers():
    value = {
        "mode": "patch",
        "changes": [
            {
                "block_id": "x",
                "replacement": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"text": "2[H2O] ===通电=== 2H2 + O2↑", "bold": True}
                        ],
                    }
                ],
            }
        ],
    }
    result, _ = normalize_chemistry(value)
    assert result["changes"][0]["replacement"][0]["content"] == [
        {"text": "2[H2O] ", "bold": True},
        {"text": "通电", "bold": True, "condition": True},
        {"text": " 2[H2] + [O2]↑", "bold": True},
    ]


def test_non_equations_and_explicit_special_runs_are_preserved():
    values = [
        "===重点===",
        "任务1 ===说明=== 任务2",
        [{"text": "高温", "condition": True}],
        [{"text": "CaCO3", "sub": True}],
    ]
    for text in values:
        value = {"sections": [{"blocks": [{"type": "paragraph", "content": text}]}]}
        assert normalize_chemistry(value) == (value, [])


def test_equation_split_across_styled_runs_preserves_the_condition_style():
    value = {
        "sections": [
            {
                "blocks": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"text": "CaCO3 "},
                            {"text": "===高", "bold": True},
                            {"text": "温==="},
                            {"text": " CaO + CO2↑", "italic": True},
                        ],
                    }
                ]
            }
        ]
    }
    result, _ = normalize_chemistry(value)
    assert result["sections"][0]["blocks"][0]["content"] == [
        {"text": "[CaCO3] "},
        {"text": "高温", "bold": True, "condition": True},
        {"text": " [CaO] + [CO2]↑", "italic": True},
    ]


def test_formula_split_across_styles_keeps_coefficient_and_atom_count_distinct():
    value = {
        "sections": [
            {
                "blocks": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"text": "2H", "bold": True},
                            {"text": "2O ===通电=== 2H2 + O2↑"},
                        ],
                    }
                ]
            }
        ]
    }
    result, _ = normalize_chemistry(value)
    runs = result["sections"][0]["blocks"][0]["content"]
    assert runs[:3] == [
        {"text": "2H", "bold": True},
        {"text": "2", "sub": True},
        {"text": "O "},
    ]
    assert {"text": "通电", "condition": True} in runs


def test_heating_arrow_and_bracketed_coefficient_become_correct_runs():
    for value in (
        "2KMnO4 △→ K2MnO4 + MnO2 + O2↑",
        "2KMnO4 Δ→ K2MnO4 + MnO2 + O2↑",
        "[2KMnO4] △→ [K2MnO4] + [MnO2] + [O2]↑",
    ):
        raw = {"sections": [{"blocks": [{"type": "paragraph", "content": value}]}]}
        normalized, _ = normalize_chemistry(raw)
        assert normalized["sections"][0]["blocks"][0]["content"] == [
            {"text": "2[KMnO4] "},
            {"text": "△", "condition": True},
            {"text": " [K2MnO4] + [MnO2] + [O2]↑"},
        ]
        assert normalize_chemistry(normalized) == (normalized, [])


def test_triangle_geometry_is_not_a_reaction_and_bracketed_charge_is_preserved():
    raw = {
        "sections": [
            {
                "blocks": [
                    {"type": "paragraph", "content": "观察△ABC → 写出结论；[SO4^2-]"}
                ]
            }
        ]
    }
    assert normalize_chemistry(raw) == (raw, [])


def test_three_line_equations_rejoin_without_removing_prose_or_equation_breaks():
    text = "观察下列反应：\nC + 2[CuO]\n高温\n= 2[Cu] + [CO2]↑\n3[CO] + [Fe2O3]\n高温\n= 2[Fe] + 3[CO2]\n思考：得失氧的关系。"
    raw = {"sections": [{"blocks": [{"type": "paragraph", "content": text}]}]}
    result, _ = normalize_chemistry(raw)
    runs = result["sections"][0]["blocks"][0]["content"]
    assert [r["text"] for r in runs if r.get("condition")] == ["高温", "高温"]
    assert (
        "".join(r["text"] for r in runs)
        == "观察下列反应：\n[C] + 2[CuO] 高温 2[Cu] + [CO2]↑\n3[CO] + [Fe2O3] 高温 2[Fe] + 3[CO2]\n思考：得失氧的关系。"
    )
    assert normalize_chemistry(result) == (result, [])


def test_three_line_condition_keeps_style_and_source_evidence():
    raw = {
        "sections": [
            {
                "blocks": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"text": "[H2] + [Cl2]\n"},
                            {"text": "点燃", "bold": True},
                            {"text": "\n= 2[HCl]"},
                        ],
                    }
                ]
            }
        ],
        "sources": [{"evidence": "[H2] + [Cl2]\n点燃\n= 2[HCl]"}],
    }
    result, _ = normalize_chemistry(raw)
    assert {"text": "点燃", "bold": True, "condition": True} in result["sections"][0][
        "blocks"
    ][0]["content"]
    assert result["sources"] == raw["sources"]


def test_three_line_prose_is_not_rejoined_as_chemistry():
    raw = {
        "sections": [
            {
                "blocks": [
                    {
                        "type": "paragraph",
                        "content": "观察实验\n高温\n= 观察结果\n任务1\n点燃\n= 任务2",
                    }
                ]
            }
        ]
    }
    assert normalize_chemistry(raw) == (raw, [])


def test_crlf_and_semantic_condition_lines_are_rejoined():
    for content in [
        "C + 2[CuO]\r\n高温\r\n= 2[Cu] + [CO2]↑\r\n思考",
        [
            {"text": "[H2] + [Cl2]\n"},
            {"text": "光照", "condition": True},
            {"text": "\n= 2[HCl]"},
        ],
    ]:
        raw = {"sections": [{"blocks": [{"type": "paragraph", "content": content}]}]}
        result, _ = normalize_chemistry(raw)
        runs = result["sections"][0]["blocks"][0]["content"]
        assert any(run.get("condition") for run in runs)
        assert sum(run["text"].count("\n") for run in runs) <= 1
