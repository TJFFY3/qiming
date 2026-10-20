"""Replace legacy repeated equals glyphs with editable DrawingML double lines."""

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
