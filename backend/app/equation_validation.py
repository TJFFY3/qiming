"""Final-pass validation for equation typography and atom balance."""

from .courseware.equations import normalize_paragraph


def _check(value, location):
    if isinstance(value, list) and any(
        not isinstance(run, dict) or not isinstance(run.get("text"), str)
        for run in value
    ):
        raise ValueError(f"{location}必须为包含 text 字符串的扁平 run 数组")
    if isinstance(value, (str, list)):
        return normalize_paragraph(value, location)
    return value


def _array(value, location):
    if not isinstance(value, list):
        raise ValueError(f"{location}必须为数组")
    return value


def validate_outline(outline):
    """Validate and normalize student-facing rich text in place."""
    if not isinstance(outline, dict):
        return
    outline = outline.get("outline", outline)
    if not isinstance(outline, dict):
        return
    for field in ("goals", "thinking"):
        values = _array(outline.get(field, []), f"$.outline.{field}")
        for index, value in enumerate(values):
            values[index] = _check(value, f"导学案{field}第{index + 1}项")
    sections = _array(outline.get("sections", []), "$.outline.sections")
    for si, section in enumerate(sections):
        section_path = f"$.outline.sections[{si}]"
        if not isinstance(section, dict):
            raise ValueError(f"{section_path}必须为对象")
        for bi, block in enumerate(_array(section.get("blocks", []), section_path + ".blocks")):
            if not isinstance(block, dict):
                continue
            path = f"导学案第{si + 1}节第{bi + 1}块"
            if block.get("type") == "paragraph":
                block["content"] = _check(block.get("content"), path)
            elif block.get("type") == "table":
                headers = _array(block.get("headers", []), f"{path}.headers")
                for ci, header in enumerate(headers):
                    headers[ci] = _check(header, f"{path}表头{ci + 1}")
                rows = _array(block.get("rows", []), f"{path}.rows")
                for ri, row in enumerate(rows):
                    _array(row, f"{path}.rows[{ri}]")
                    for ci, cell in enumerate(row):
                        row[ci] = _check(cell, f"{path}第{ri + 1}行第{ci + 1}列")


def validate_study_guide_result(result):
    """Handle both full outlines and patch responses before merging."""
    validate_outline(result)
    if isinstance(result, dict):
        for ci, change in enumerate(_array(result.get("changes", []), "$.changes"), 1):
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
