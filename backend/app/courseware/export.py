"""Thin adapter to the user-provided, shared chemistry artifact primitives."""

import sys
from pathlib import Path

from ..publication import clean_public
from .models import Deck
from .equations import normalize_deck
from .ppt_equations import native_equation_bars

VENDOR = Path(__file__).resolve().parents[3] / "vendor" / "chemistry"
if str(VENDOR / "scripts") not in sys.path:
    sys.path.insert(0, str(VENDOR / "scripts"))
from ppt_tools import generate_pptx
from validate_outputs import validate_paths


def export_deck(raw, destination, draft):
    content = Deck.model_validate(raw).model_dump(
        exclude_none=True, exclude_defaults=True
    )
    content = normalize_deck(clean_public(content))
    path = destination / "courseware.pptx"
    generate_pptx(content["slides"], path)
    native_equation_bars(path)
    validation = validate_paths([path])
    if not validation["passed"]:
        raise ValueError(
            "课件结构检查未通过：" + "；".join(i["code"] for i in validation["issues"])
        )
    # Reports must not reveal server paths.
    for item in validation["issues"] + validation["warnings"]:
        item["file"] = "courseware.pptx"
    return content, validation
