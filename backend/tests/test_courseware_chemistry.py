import copy
from pathlib import Path
from zipfile import ZipFile
import pytest
from lxml import etree
from backend.app.courseware.export import export_deck

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
