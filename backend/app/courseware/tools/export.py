"""【文档工具·互动课件】适配 vendor 的原生 PPTX 生成与检查，并应用分页、图片和方程式排版。"""

import sys
from pathlib import Path
from zipfile import ZipFile
from lxml import etree

from backend.app.shared.tools.publication import clean_public
from backend.app.courseware.domain.models import Deck
from backend.app.courseware.domain.equations import normalize_deck
from backend.app.courseware.tools.ppt_equations import native_equation_bars
from backend.app.courseware.domain.pagination import paginate_slides
from backend.app.courseware.tools.images import prepare_slides, add_image_captions

from backend.app.paths import VENDOR
if str(VENDOR / "scripts") not in sys.path:
    sys.path.insert(0, str(VENDOR / "scripts"))
from ppt_tools import generate_pptx
from validate_outputs import validate_paths


def validate_courseware(path):
    report = validate_paths([path])
    retained = []
    with ZipFile(path) as package:
        for issue in report["issues"]:
            # The teacher explicitly requests smaller reaction labels. This
            # exception applies only to native condition text, never body text.
            allowed_label = False
            if issue["code"] == "PPT_FONT_SMALL":
                part, xpath = issue["location"].split(":", 1)
                root = etree.fromstring(package.read(part))
                ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main", "p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
                for node in root.xpath(xpath, namespaces=ns):
                    properties = node.getparent().find("a:rPr", ns)
                    allowed_label = (
                        bool(node.xpath('ancestor::p:sp[p:nvSpPr/p:cNvPr[starts-with(@name,"反应条件")]]', namespaces=ns))
                        and properties is not None and properties.get("sz") == "1560"
                    )
            if not allowed_label:
                retained.append(issue)
    report["issues"] = retained
    report["passed"] = not retained
    return report


def export_deck(raw, destination, draft, paginate=True, check_balance=True, sources=None, image_transport=None, image_origin=None, previous_images=None):
    content = Deck.model_validate(raw).model_dump(
        exclude_none=True, exclude_defaults=True
    )
    content = normalize_deck(clean_public(content), check_balance=check_balance)
    content["slides"] = paginate_slides(content["slides"], allow_split=paginate)
    path = destination / "courseware.pptx"
    slides = prepare_slides(content, sources or [], destination, previous=previous_images, transport=image_transport, origin=image_origin)
    generate_pptx(slides, path)
    native_equation_bars(path)
    if any(s.get("image_id") for s in slides):
        add_image_captions(path, slides)
    validation = validate_courseware(path)
    if not validation["passed"]:
        raise ValueError(
            "课件结构检查未通过：" + "；".join(i["code"] for i in validation["issues"])
        )
    # Reports must not reveal server paths.
    for item in validation["issues"] + validation["warnings"]:
        item["file"] = "courseware.pptx"
    return content, validation
