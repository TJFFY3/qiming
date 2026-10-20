"""Final-pass validation for equation typography and atom balance."""

from .courseware.equations import normalize_paragraph


def _check(value, location):
    if isinstance(value, (str, list)):
        normalize_paragraph(value, location)


def validate_outline(outline):
    """Validate student-facing rich text in a study guide."""
    if not isinstance(outline, dict):
        return
    outline = outline.get("outline", outline)
    if not isinstance(outline, dict):
        return
    for field in ("goals", "thinking"):
        for index, value in enumerate(outline.get(field, []), 1):
            _check(value, f"导学案{field}第{index}项")
    sections = outline.get("sections", [])
    for si, section in enumerate(sections):
        for bi, block in enumerate(section.get("blocks", [])):
            if not isinstance(block, dict):
                continue
            path = f"导学案第{si + 1}节第{bi + 1}块"
            if block.get("type") == "paragraph":
                _check(block.get("content"), path)
            elif block.get("type") == "table":
                for ci, header in enumerate(block.get("headers", [])):
                    _check(header, f"{path}表头{ci + 1}")
                for ri, row in enumerate(block.get("rows", [])):
                    for ci, cell in enumerate(row):
                        _check(cell, f"{path}第{ri + 1}行第{ci + 1}列")


def validate_study_guide_result(result):
    """Handle both full outlines and patch responses before merging."""
    validate_outline(result)
    if isinstance(result, dict):
        for ci, change in enumerate(result.get("changes", []), 1):
            if isinstance(change, dict):
                validate_outline({"sections": [{"blocks": change.get("replacement", [])}]})


def validate_practice(content):
    """Validate rich text in all student and answer fields."""
    for group in ("choice", "written", "optional"):
        for qi, question in enumerate(content.get(group, []), 1):
            path = f"限时练习{group}第{qi}题"
            for field in ("stem", "answer", "explanation"):
                _check(question.get(field), f"{path}{field}")
            for oi, option in enumerate(question.get("options") or [], 1):
                _check(option, f"{path}选项{oi}")
