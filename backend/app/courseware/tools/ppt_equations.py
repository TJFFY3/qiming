"""【文档工具·互动课件】将反应条件转换为可编辑 DrawingML 线条与文字，并适配历史下载。"""

from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"p": P, "a": A}


def node(parent, namespace, tag, **attrs):
    return E.SubElement(
        parent, "{" + namespace + "}" + tag, {k: str(v) for k, v in attrs.items()}
    )


def native_equation_bars(path):
    with ZipFile(path) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    for name in parts:
        if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
            continue
        root = E.fromstring(parts[name])
        tree = root.find("p:cSld/p:spTree", NS)
        ident = (
            max(int(n.get("id")) for n in root.xpath("//p:cNvPr", namespaces=NS)) + 1
        )
        labels = iter(
            root.xpath('//p:sp[p:nvSpPr/p:cNvPr[@name="反应条件"]]', namespaces=NS)
        )
        for shape in root.xpath(
            '//p:sp[p:nvSpPr/p:cNvPr[@name="反应方程式"]]', namespaces=NS
        ):
            position = shape.find("p:spPr/a:xfrm/a:off", NS)
            y = int(position.get("y"))
            for run in shape.xpath(".//a:r", namespaces=NS):
                text = run.find("a:t", NS)
                if not text.text or set(text.text) != {"="} or len(text.text) < 3:
                    continue
                label = next(labels)
                for properties in label.findall(".//a:rPr", NS) + label.findall(".//a:endParaRPr", NS):
                    properties.set("sz", "1560")
                off = label.find("p:spPr/a:xfrm/a:off", NS)
                ext = label.find("p:spPr/a:xfrm/a:ext", NS)
                # Move the label closer to its operator while preserving the
                # vendor's reserved equation row and all surrounding content.
                off.set("y", str(y - 200000))
                width = round(len(text.text) * 0.6 * 24 * 12700)
                center = int(off.get("x")) + int(ext.get("cx")) / 2
                # Keep the measured advance of the original equation run, but
                # draw continuous equal bars, rather than repeating '=' glyphs.
                text.text = " " * len(text.text)
                text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                for offset in (0, 65000):
                    bar = node(tree, P, "cxnSp")
                    nv = node(bar, P, "nvCxnSpPr")
                    node(nv, P, "cNvPr", id=ident, name=f"反应等号 {ident}")
                    ident += 1
                    node(nv, P, "cNvCxnSpPr")
                    node(nv, P, "nvPr")
                    props = node(bar, P, "spPr")
                    xf = node(props, A, "xfrm")
                    node(
                        xf, A, "off", x=round(center - width / 2), y=y + 260000 + offset
                    )
                    node(xf, A, "ext", cx=width, cy=0)
                    geom = node(props, A, "prstGeom", prst="line")
                    node(geom, A, "avLst")
                    line = node(props, A, "ln", w=14000)
                    node(node(line, A, "solidFill"), A, "srgbClr", val="000000")
                    node(line, A, "prstDash", val="solid")
        parts[name] = E.tostring(
            root, xml_declaration=True, encoding="UTF-8", standalone=True
        )
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


def coefficient_download(path):
    """Repair old native PPT runs in a cached copy, preserving saved versions."""
    import hashlib
    import os
    import re
    import tempfile
    from pathlib import Path

    path = Path(path)
    stamp = path.stat()
    key = hashlib.sha256(
        f"{path.name}:{stamp.st_mtime_ns}:{stamp.st_size}:coefficients-v1".encode()
    ).hexdigest()
    directory = path.parent / ".public"
    directory.mkdir(exist_ok=True)
    target = directory / (key + ".pptx")
    if target.is_file():
        return target
    with tempfile.NamedTemporaryFile(dir=directory, suffix=".pptx", delete=False) as f:
        temporary = Path(f.name)
    try:
        with ZipFile(path) as source, ZipFile(temporary, "w", ZIP_DEFLATED) as output:
            for info in source.infolist():
                data = source.read(info.filename)
                changed = False
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", info.filename):
                    root = E.fromstring(data)
                    for paragraph in root.findall(".//a:p", NS):
                        runs = paragraph.findall("a:r", NS)
                        texts = [r.findtext("a:t", default="", namespaces=NS) for r in runs]
                        if not re.search(r"[=→⟶⇌↔]", "".join(texts)):
                            continue
                        for i, run in enumerate(runs):
                            props = run.find("a:rPr", NS)
                            if props is None or props.get("baseline") != "-25000":
                                continue
                            left, right = "".join(texts[:i]).rstrip(), "".join(texts[i + 1:]).lstrip()
                            if (re.fullmatch(r"[0-9]+", texts[i])
                                and not re.search(r"[A-Za-z0-9)\]]$", left)
                                and re.match(r"[A-Z][a-z]?", right)):
                                props.attrib.pop("baseline")
                                # Normal neighboring formula text defines body size.
                                following = runs[i + 1].find("a:rPr", NS)
                                if following is not None and following.get("sz"):
                                    props.set("sz", following.get("sz"))
                                changed = True
                    if changed:
                        data = E.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                output.writestr(info, data)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
