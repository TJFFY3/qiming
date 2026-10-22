"""【图片工具·互动课件】准备课件原图快照与原生 PPT 图注，复用共享下载工具。"""

import copy
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from lxml import etree
from backend.app.shared.tools.images import prepare_image_assets


def prepare_slides(content, sources, directory, previous=None, transport=None, origin=None):
    blocks = [{"type": "image", "image_id": s["image_id"]} for s in content["slides"] if s.get("image_id")]
    if not blocks:
        return copy.deepcopy(content["slides"])
    cache = Path(directory) / "images"
    cache.mkdir(exist_ok=True)
    if previous:
        for block in blocks:
            name = block["image_id"] + ".bin"
            old = Path(previous) / name
            if old.is_file() and not (cache / name).exists():
                shutil.copyfile(old, cache / name)
    assets = prepare_image_assets(blocks, sources, cache, transport=transport, allowed_origin=origin)
    slides = copy.deepcopy(content["slides"])
    for slide in slides:
        if slide.get("image_id"):
            slide["image"] = str(assets[slide["image_id"]])
    return slides


def add_image_captions(path, slides):
    from ppt_tools import _textbox

    p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    ns = {"p": p, "a": a}
    with ZipFile(path) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    canvas = etree.fromstring(parts["ppt/presentation.xml"]).find("p:sldSz", ns)
    width, height = int(canvas.get("cx"))/360000, int(canvas.get("cy"))/360000
    for number, slide in enumerate(slides, 1):
        if not slide.get("image_id") or not slide.get("image_caption"):
            continue
        name = f"ppt/slides/slide{number}.xml"
        root = etree.fromstring(parts[name])
        tree = root.find("p:cSld/p:spTree", ns)
        for picture in tree.findall("p:pic", ns):
            transform = picture.find("p:spPr/a:xfrm", ns)
            off, ext = transform.find("a:off", ns), transform.find("a:ext", ns)
            old_w, old_h = int(ext.get("cx")), int(ext.get("cy"))
            box_w, box_h = (width-18)*360000, (height-6.2)*360000
            scale = min(box_w/old_w, box_h/old_h, 1)
            w, h = old_w*scale, old_h*scale
            ext.set("cx", str(round(w))); ext.set("cy", str(round(h)))
            off.set("x", str(round(17.2*360000+(box_w-w)/2)))
            off.set("y", str(round(4.2*360000+(box_h-h)/2)))
            picture.find("p:nvPicPr/p:cNvPr", ns).set("descr", slide["image_caption"])
        ident = max(int(n.get("id")) for n in root.findall(".//p:cNvPr", ns))+1
        _textbox(tree, ident, "图片图注", [[{"text": slide["image_caption"]}]], 17.2, height-1.65, width-18, 1.35, size=2400, align="ctr", font="黑体")
        parts[name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    with ZipFile(path, "w", ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data)
