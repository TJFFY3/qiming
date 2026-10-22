import copy
from pathlib import Path
from zipfile import ZipFile
import pytest
from lxml import etree
from backend.app.courseware.tools.export import export_deck

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


def deck(paragraphs):
    return {
        "title": "格式回归",
        "slides": [{"title": "化学方程式", "stage": "探", "paragraphs": paragraphs}],
    }


def test_bare_formulas_around_semantic_conditions_export_native_subscripts(tmp_path):
    raw = deck(
        [
            [
                {"text": "2CuO + C "},
                {"text": "高温", "condition": True},
                {"text": " 2Cu + CO2↑"},
            ],
            "Zn + H2SO4 = ZnSO4 + H2↑",
        ]
    )
    before = copy.deepcopy(raw)
    content, report = export_deck(raw, tmp_path, True)
    assert raw == before and report["passed"]
    assert content["slides"][0]["paragraphs"][0] == [
        {"text": "2[CuO] + [C] "},
        {"text": "高温", "condition": True},
        {"text": " 2[Cu] + [CO2]↑"},
    ]
    with ZipFile(tmp_path / "courseware.pptx") as z:
        xml = etree.fromstring(z.read("ppt/slides/slide1.xml"))
        assert xml.xpath('//a:r[a:t="2"]/a:rPr[@baseline="-25000"]', namespaces=NS)
        assert not any("===" in s for s in xml.xpath("//a:t/text()", namespaces=NS))
        bars = xml.xpath(
            '//p:cxnSp[p:nvCxnSpPr/p:cNvPr[starts-with(@name,"反应等号")]]',
            namespaces=NS,
        )
        assert len(bars) == 2
        label = xml.xpath(
            '//p:sp[p:nvSpPr/p:cNvPr[starts-with(@name,"反应条件")]]', namespaces=NS
        )[0]
        lx = label.find("p:spPr/a:xfrm/a:off", NS)
        le = label.find("p:spPr/a:xfrm/a:ext", NS)
        for bar in bars:
            off = bar.find("p:spPr/a:xfrm/a:off", NS)
            ext = bar.find("p:spPr/a:xfrm/a:ext", NS)
            assert (
                abs(
                    int(lx.get("x"))
                    + int(le.get("cx")) / 2
                    - int(off.get("x"))
                    - int(ext.get("cx")) / 2
                )
                < 4
            )
            assert int(lx.get("y")) < int(off.get("y"))
        assert z.read("ppt/slideMasters/slideMaster1.xml") == ZipFile(
            Path("vendor/chemistry/assets/templates/课件模板.pptx")
        ).read("ppt/slideMasters/slideMaster1.xml")


@pytest.mark.parametrize(
    "paragraphs,reason",
    [
        ([[{"text": "Zn + H2SO4"}, {"text": "ZnSO4 + H2↑"}]], "缺少连接符"),
        (
            [[{"text": "Cu + O2"}, {"text": "△", "condition": True}, {"text": "CuO"}]],
            "原子数不守恒",
        ),
    ],
)
def test_incomplete_or_unbalanced_equations_are_not_exported(
    tmp_path, paragraphs, reason
):
    with pytest.raises(ValueError, match=reason):
        export_deck(deck(paragraphs), tmp_path, True)
    assert not (tmp_path / "courseware.pptx").exists()


def test_teacher_prose_is_not_globally_rewritten_or_treated_as_an_equation(tmp_path):
    raw = deck(
        ["第2组在3分钟内讨论：Zn 与 H2SO4 反应的共同特点。", "[Fe^3+] 与 [SO4^2-]"]
    )
    content, _ = export_deck(raw, tmp_path, True)
    assert content["slides"][0]["paragraphs"] == raw["slides"][0]["paragraphs"]


@pytest.mark.parametrize(
    "paragraph",
    [
        "NaCl + H2O",
        "[NaCl] + [H2O]",
        "Zn + H2SO4",
        [{"text": "Zn + "}, {"text": "H2SO4"}],
    ],
)
def test_reactant_only_lists_do_not_require_a_reaction_connector(tmp_path, paragraph):
    content, _ = export_deck(deck([paragraph]), tmp_path, True)
    assert content["slides"]


def test_formula_split_across_styled_runs_keeps_subscript_and_style(tmp_path):
    raw = deck(
        [[{"text": "2Cu + O"}, {"text": "2", "bold": True}, {"text": " = 2CuO"}]]
    )
    export_deck(raw, tmp_path, True)
    with ZipFile(tmp_path / "courseware.pptx") as archive:
        xml = etree.fromstring(archive.read("ppt/slides/slide1.xml"))
        assert xml.xpath(
            '//a:r[a:t="2"]/a:rPr[@baseline="-25000"][@b="1"]', namespaces=NS
        )


@pytest.mark.parametrize("equation,subscripts", [
    ("[2CuO+C=高温=2Cu+CO2↑]", ["2"]),
    ("[Fe2O3+3CO=高温=2Fe+3CO2]", ["2", "3", "2"]),
    ("[2CuO]+[C]=高温=[2Cu]+[CO2]↑", ["2"]),
])
def test_bracketed_equation_coefficients_keep_normal_baseline(tmp_path, equation, subscripts):
    export_deck(deck([equation]), tmp_path, True)
    with ZipFile(tmp_path / "courseware.pptx") as archive:
        xml = etree.fromstring(archive.read("ppt/slides/slide1.xml"))
    assert xml.xpath('//a:r[a:rPr/@baseline="-25000"]/a:t/text()', namespaces=NS) == subscripts
    assert xml.xpath('//a:r[a:rPr/@baseline="0"]/a:t/text()', namespaces=NS) or xml.xpath('//a:r[not(a:rPr/@baseline)]/a:t/text()', namespaces=NS)
    assert xml.xpath('//a:t[text()="高温"]', namespaces=NS)


def test_existing_download_repairs_coefficients_without_overwriting_original(tmp_path):
    from backend.app.courseware.tools.export import generate_pptx
    from backend.app.courseware.tools.ppt_equations import coefficient_download

    original = tmp_path / "old.pptx"
    generate_pptx(deck(["[2CuO+C=高温=2Cu+CO2↑]"])["slides"], original)
    before = original.read_bytes()
    fixed = coefficient_download(original)
    assert original.read_bytes() == before
    assert coefficient_download(original) == fixed
    with ZipFile(fixed) as z, ZipFile(original) as old:
        xml = etree.fromstring(z.read("ppt/slides/slide1.xml"))
        assert xml.xpath('//a:r[a:rPr/@baseline="-25000"]/a:t/text()', namespaces=NS) == ["2"]
        coefficients = xml.xpath('//a:r[a:t="2" and not(a:rPr/@baseline)]', namespaces=NS)
        assert len(coefficients) == 2
        assert all(int(r.find("a:rPr", NS).get("sz")) >= 2400 for r in coefficients)
        assert z.read("ppt/slideMasters/slideMaster1.xml") == old.read("ppt/slideMasters/slideMaster1.xml")
