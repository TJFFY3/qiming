import copy
import io
from zipfile import ZipFile

from lxml import etree

from backend.app.timed_practice.documents import (
    canonical_rich,
    render,
    validate_content,
)
from backend.app.timed_practice.requirements import resolve_requirements
from backend.tests.test_timed_practice import app_for, paper, settings, source, PREFIX
from fastapi.testclient import TestClient

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
}


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
        response = client.get(path + "/files/paper")
        assert response.status_code == 200
        with ZipFile(io.BytesIO(response.content)) as z:
            xml = etree.fromstring(z.read("word/document.xml"))
        assert xml.xpath('//m:limUpp/m:lim//m:t[text()="点燃"]', namespaces=NS)
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
