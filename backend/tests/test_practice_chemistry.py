import copy
import io
from zipfile import ZipFile

from lxml import etree

from backend.app.timed_practice.tools.documents import (
    canonical_rich,
    render,
    validate_content,
)
from backend.app.timed_practice.domain.requirements import resolve_requirements
from backend.tests.test_timed_practice import app_for, paper, settings, source, PREFIX
from fastapi.testclient import TestClient
import pytest

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
}


@pytest.mark.parametrize(
    "value,expected,subscripts",
    [
        ("[Fe]+[CuSO_4]===[Cu]+[FeSO_4]", "Fe+CuSO4===Cu+FeSO4", ["4", "4"]),
        ("C+O_2===CO_2", "C+O2===CO2", ["2", "2"]),
        (
            "[Ca(OH)_{2}]+2[HCl]=[CaCl_2]+2[H_2O]",
            "Ca(OH)2+2HCl=CaCl2+2H2O",
            ["2", "2", "2"],
        ),
        (
            [
                {"text": "Fe+CuSO_", "bold": True},
                {"text": "4", "sub": True},
                {"text": "===Cu+FeSO_"},
                {"text": "4", "sub": True},
            ],
            "Fe+CuSO4===Cu+FeSO4",
            ["4", "4"],
        ),
    ],
)
def test_chemical_subscript_markers_are_removed_without_changing_numbers_or_styles(
    value, expected, subscripts
):
    before = copy.deepcopy(value)
    runs = canonical_rich(value)
    assert "".join(run["text"] for run in runs) == expected
    assert [run["text"] for run in runs if run.get("sub")] == subscripts
    assert value == before
    assert canonical_rich(runs) == runs
    if isinstance(value, list):
        assert runs[0]["bold"] is True


def test_chemical_marker_cleanup_preserves_answer_blanks_and_identifiers():
    value = "填空______；x_1、sample_2、ABC_3；[CO_2]______"
    runs = canonical_rich(value)
    assert (
        "".join(run["text"] for run in runs)
        == "填空______；x_1、sample_2、ABC_3；CO2______"
    )


def test_screenshot_equations_have_native_subscripts_and_stacked_conditions():
    examples = [
        ("2CO+O2点燃2CO2", "点燃"),
        ("2H2O通电2H2↑+O2↑", "通电"),
        ("CH4+2O2点燃CO2+2H2O", "点燃"),
        ("反应2KClO3(MnO2,△)2KCl+3O2↑中，每生成1 mol O2", "MnO2、△"),
        (
            [
                {"text": "①CO"},
                {"text": "2", "sub": True},
                {"text": "+C高温2CO\n②Cu"},
                {"text": "2", "sub": True},
                {"text": "(OH)2CO3△2CuO+H2O+CO2↑"},
            ],
            "高温",
        ),
    ]
    for value, label in examples:
        before = copy.deepcopy(value)
        runs = canonical_rich(value)
        assert value == before
        assert any(r.get("condition") and r["text"] == label for r in runs)
        assert any(r.get("sub") and r["text"] in ("2", "3", "4") for r in runs)
        assert canonical_rich(runs) == runs
    runs = canonical_rich("Na2O+H2O═2NaOH；3 mol、题号14、pH7、2026年")
    assert sum(bool(r.get("sub")) for r in runs) == 2
    assert "3 mol、题号14、pH7、2026年" in "".join(
        r["text"] for r in runs if not r.get("sub")
    )
    assert not any(
        r.get("condition") for r in canonical_rich("点燃镁条，观察△ABC；第2题")
    )


def test_word_options_stems_answers_use_same_equation_typography(tmp_path):
    raw = paper()
    raw["choice"][0]["options"] = [
        "2CO+O2点燃2CO2",
        "Na2O+H2O═2NaOH",
        "2H2O通电2H2↑+O2↑",
        "CH4+2O2点燃CO2+2H2O",
    ]
    raw["written"][0]["stem"] = "写出反应2KClO3(MnO2,△)2KCl+3O2↑的电子转移：________"
    raw["written"][0]["answer"] = "2CO+O2点燃2CO2"
    raw["written"][0]["explanation"] = "①CO2+C高温2CO\n②Cu2(OH)2CO3△2CuO+H2O+CO2↑"
    content = validate_content(raw, resolve_requirements(settings(), ""), [source()])
    render(content, [source()], tmp_path / "v1", False)
    for name in ("paper", "answers"):
        with ZipFile(tmp_path / "v1" / (name + ".docx")) as z:
            xml = etree.fromstring(z.read("word/document.xml"))
        assert xml.xpath(
            '//w:r[w:t="2"]/w:rPr/w:vertAlign[@w:val="subscript"]', namespaces=NS
        )
        assert xml.xpath('//m:limUpp/m:lim//m:t[text()="点燃"]', namespaces=NS)
        assert xml.xpath("//m:limUpp", namespaces=NS)
        assert not xml.xpath(
            '//w:t[contains(text(),"O2点燃") or contains(text(),"(MnO2,△)")]',
            namespaces=NS,
        )


def test_historical_preview_and_download_correct_typography_without_overwriting_version(
    tmp_path,
):
    raw = paper()
    raw["choice"][0]["options"][0] = "2CO+O2点燃2CO2"
    with TestClient(app_for(tmp_path, [raw])) as client:
        s = client.post(PREFIX + "/sessions", json=settings()).json()
        job = client.post(
            PREFIX + f"/sessions/{s['id']}/generate", json={"prompt": "生成"}
        ).json()
        j = client.get(PREFIX + f"/jobs/{job['id']}").json()
        path = PREFIX + f"/sessions/{s['id']}/versions/{j['version_id']}"
        # Emulate a pre-fix historical snapshot in the independent store/files.
        import sqlite3
        import json

        dbpath = tmp_path / "timed-practice" / "practice.sqlite"
        with sqlite3.connect(dbpath) as db:
            row = db.execute(
                "select data from sessions where id=?", (s["id"],)
            ).fetchone()
            stored = json.loads(row[0])
            v = stored["versions"][0]
            v["content"]["choice"][0]["options"][0] = [{"text": "2CO+O2点燃2CO2"}]
            v["content"]["choice"][0]["options"][1] = [
                {"text": "Fe+CuSO_"},
                {"text": "4", "sub": True},
                {"text": "===Cu+FeSO_"},
                {"text": "4", "sub": True},
            ]
            v["content"]["written"][0]["answer"] = "[C]+[O_2]=[CO_2]；填空______；x_1"
            v["content"]["choice"][0]["stem"] = [{"text": serialized_equation()}]
            db.execute(
                "update sessions set data=? where id=?", (json.dumps(stored), s["id"])
            )
        from pathlib import Path

        original = Path(v["directory"]) / "content.json"
        original.write_text(json.dumps(v["content"]), encoding="utf-8")
        before = original.read_bytes()
        for data in [
            client.get(path).json(),
            client.get(PREFIX + f"/sessions/{s['id']}").json()["versions"][0],
            client.get(path + "/files/content").json(),
        ]:
            c = data.get("content", data)
            assert any(r.get("condition") for r in c["choice"][0]["options"][0])
            assert not any('"text"' in r["text"] for r in c["choice"][0]["stem"])
            assert (
                "".join(r["text"] for r in c["choice"][0]["options"][1])
                == "Fe+CuSO4===Cu+FeSO4"
            )
        response = client.get(path + "/files/paper")
        assert response.status_code == 200
        with ZipFile(io.BytesIO(response.content)) as z:
            xml = etree.fromstring(z.read("word/document.xml"))
        assert xml.xpath('//m:limUpp/m:lim//m:t[text()="点燃"]', namespaces=NS)
        assert not any('"text"' in s for s in xml.xpath("//w:t/text()", namespaces=NS))
        assert original.read_bytes() == before
        for kind in ("paper", "answers"):
            response = client.get(path + "/files/" + kind)
            assert response.status_code == 200
            with ZipFile(io.BytesIO(response.content)) as z:
                root = etree.fromstring(z.read("word/document.xml"))
            visible = "".join(root.xpath("//w:t/text()", namespaces=NS))
            assert "SO_" not in visible and "O_2" not in visible
            if kind == "paper":
                assert root.xpath(
                    '//w:r[w:t="4"]/w:rPr/w:vertAlign[@w:val="subscript"]',
                    namespaces=NS,
                )
            else:
                assert "填空______；x_1" in visible
        assert original.read_bytes() == before


def test_catalyst_formula_is_subscripted_inside_condition_cache(tmp_path):
    raw = paper()
    raw["choice"][0]["options"][0] = "2KClO3(MnO2,△)2KCl+3O2↑"
    content = validate_content(raw, resolve_requirements(settings(), ""), [source()])
    render(content, [source()], tmp_path / "v1", False)
    with ZipFile(tmp_path / "v1" / "paper.docx") as z:
        xml = etree.fromstring(z.read("word/document.xml"))
    assert xml.xpath('//m:lim/m:sSub/m:sub//m:t[text()="2"]', namespaces=NS)


def test_catalyst_boundary_does_not_hide_reactant_subscripts_or_corrupt_ions():
    runs = canonical_rich("2H2O2(MnO2)2H2O+O2")
    boundary = next(i for i, r in enumerate(runs) if r.get("condition"))
    assert sum(r["text"].count("2") for r in runs[:boundary] if r.get("sub")) == 2
    runs = canonical_rich("Fe3+ + OH- = Fe(OH)3↓")
    assert not any(r.get("sub") for r in runs[:1])
    assert runs[0]["text"].startswith("Fe3+ + OH-")


def test_condition_has_one_visible_native_operator_without_duplicate_legacy_field(
    tmp_path,
):
    raw = paper()
    raw["choice"][0]["options"][0] = "2CO+O2点燃2CO2"
    content = validate_content(raw, resolve_requirements(settings(), ""), [source()])
    render(content, [source()], tmp_path / "v1", False)
    with ZipFile(tmp_path / "v1" / "paper.docx") as z:
        xml = etree.fromstring(z.read("word/document.xml"))
    assert not xml.xpath('//w:instrText[contains(text(),"\\up8")]', namespaces=NS)
    assert len(xml.xpath("//m:limUpp/m:e//m:t", namespaces=NS)) == 1


def test_explicit_condition_consumes_adjacent_duplicate_equals_in_styled_runs(tmp_path):
    raw = paper()
    raw["choice"][0]["stem"] = [
        {"text": "黑火药反应S+2KNO3+3C ==="},
        {"text": "点燃", "condition": True},
        {"text": " ==", "bold": True},
        {"text": "= K2S+3CO2↑+N2↑。"},
    ]
    content = validate_content(raw, resolve_requirements(settings(), ""), [source()])
    runs = content["choice"][0]["stem"]
    assert not any("=" in r["text"] for r in runs if not r.get("condition"))
    assert sum(bool(r.get("condition")) for r in runs) == 1
    assert canonical_rich(runs) == runs
    render(content, [source()], tmp_path / "v1", False)
    with ZipFile(tmp_path / "v1" / "paper.docx") as z:
        xml = etree.fromstring(z.read("word/document.xml"))
    assert not xml.xpath('//w:t[contains(text(),"=")]', namespaces=NS)
    assert len(xml.xpath("//m:limUpp", namespaces=NS)) == 1


def serialized_equation():
    import json

    runs = [
        {"text": "S+2KNO", "sub": False},
        {"text": "3", "sub": True},
        {"text": "+3C "},
        {"text": "点燃", "condition": True},
        {"text": " K", "sub": False},
        {"text": "2", "sub": True},
        {"text": "S+3CO", "sub": False},
        {"text": "2", "sub": True, "sup": False},
        {"text": "↑+N", "sub": False},
        {"text": "2", "sub": True},
        {"text": "↑"},
    ]
    return (
        "我国四大发明中，黑火药爆炸反应为 "
        + ",".join(json.dumps(r, ensure_ascii=False) for r in runs)
        + "。被还原的元素是（ ）"
    )


def test_serialized_inline_equation_is_recovered_before_typography_and_word(tmp_path):
    bad = serialized_equation()
    # Historical normalization had already split numeric JSON values into runs.
    import re

    damaged = [
        {"text": p, **({"sub": True} if p.isdigit() else {})}
        for p in re.split(r"(\d+)", bad)
        if p
    ]
    before = copy.deepcopy(damaged)
    runs = canonical_rich(damaged)
    assert damaged == before
    assert not any('"text"' in r["text"] or '"sub"' in r["text"] for r in runs)
    assert [r["text"] for r in runs if r.get("sub")] == ["3", "2", "2", "2"]
    assert any(r.get("condition") and r["text"] == "点燃" for r in runs)
    assert canonical_rich(runs) == runs
    raw = paper()
    raw["choice"][0]["stem"] = damaged
    raw["written"][0]["answer"] = bad
    content = validate_content(raw, resolve_requirements(settings(), ""), [source()])
    render(content, [source()], tmp_path / "fixed", False)
    for name in ("paper", "answers"):
        with ZipFile(tmp_path / "fixed" / (name + ".docx")) as z:
            xml = etree.fromstring(z.read("word/document.xml"))
        visible = "".join(xml.xpath("//w:t/text()|//m:t/text()", namespaces=NS))
        assert '"text"' not in visible and '"condition"' not in visible
        assert xml.xpath('//m:limUpp/m:lim//m:t[text()="点燃"]', namespaces=NS)


def test_serialized_run_arrays_recover_and_malformed_structures_do_not_publish():
    import json
    import pytest

    value = json.dumps(
        [
            {"text": "2[CuO]+[C]"},
            {"text": "高温", "condition": True},
            {"text": "2[Cu]+[CO2]↑"},
        ],
        ensure_ascii=False,
    )
    runs = canonical_rich(value)
    assert not any('"text"' in r["text"] or "[" in r["text"] for r in runs)
    assert any(r.get("condition") for r in runs)
    reordered = canonical_rich('{"bold":true,"text":"2[Cu]"},{"sub":true,"text":"2"}')
    assert reordered[0]["bold"] and reordered[0]["text"] == "2Cu"
    assert reordered[-1].get("sub")
    with pytest.raises(ValueError, match="结构化"):
        canonical_rich('反应为 {"text":"CuO", "condition":tr')


def test_known_historical_nested_text_markers_are_flattened_without_guessing_chemistry():
    bad = '{"text":"Na","sub":false},{"text":"2","sub":true},{"text":"O+H2O==={"text":"2NaOH"}'
    runs = canonical_rich(bad)
    assert '"text"' not in "".join(r["text"] for r in runs)
    assert "".join(r["text"] for r in runs) == "Na2O+H2O===2NaOH"
    assert [r["text"] for r in runs if r.get("sub")] == ["2", "2"]
    runs = canonical_rich(
        '2Fe3+,{"text"+3ClO","sub":false},-,{"text"+10OH","sub":false},-'
    )
    assert '"text"' not in "".join(r["text"] for r in runs)
    assert "+3ClO" in "".join(r["text"] for r in runs)
