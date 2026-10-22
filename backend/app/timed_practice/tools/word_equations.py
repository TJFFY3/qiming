"""【文档工具·限时练习】生成可编辑原生 Word 反应条件，避免重复渲染等号。"""

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from backend.app.timed_practice.domain.equations import format_runs


def _math_run(text):
    run = OxmlElement("m:r")
    properties = OxmlElement("m:rPr")
    style = OxmlElement("m:sty")
    style.set(qn("m:val"), "p")
    properties.append(style)
    run.append(properties)
    node = OxmlElement("m:t")
    node.text = text
    run.append(node)
    return run


def format_word_conditions(document):
    for paragraph in document._element.xpath("//w:p"):
        field = []
        condition_field = False
        for node in list(paragraph):
            markers = list(node.iter(qn("w:fldChar")))
            if any(m.get(qn("w:fldCharType")) == "begin" for m in markers):
                field = [node]
                condition_field = False
                continue
            if not field:
                continue
            field.append(node)
            if any("\\up8(" in (t.text or "") for t in node.iter(qn("w:instrText"))):
                condition_field = True
            if any(m.get(qn("w:fldCharType")) == "end" for m in markers):
                if condition_field:
                    # OMML already carries the complete editable upper condition.
                    # Some Office readers independently render both field and cache.
                    for child in field:
                        if child.tag != qn("m:oMath"):
                            paragraph.remove(child)
                field = []
    for limit in document._element.xpath("//m:lim"):
        label = "".join(node.text or "" for node in limit.iter(qn("m:t")))
        runs = format_runs([{"text": label}])
        if not any(r.get("sub") for r in runs):
            continue
        for child in list(limit):
            limit.remove(child)
        for run in runs:
            if run.get("sub") and len(limit):
                base = limit[-1]
                limit.remove(base)
                script = OxmlElement("m:sSub")
                main = OxmlElement("m:e")
                main.append(base)
                sub = OxmlElement("m:sub")
                sub.append(_math_run(run["text"]))
                script.extend([main, sub])
                limit.append(script)
            else:
                limit.append(_math_run(run["text"]))
