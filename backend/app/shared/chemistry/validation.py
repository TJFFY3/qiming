"""【规则处理·化学】遍历正文并规范化富文本、校验方程式；不发送模型请求。"""

import copy
import re
from itertools import chain

from backend.app.courseware.domain.equations import normalize_paragraph
from backend.app.shared.chemistry.repair import EquationBalanceError, equation_details


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


def _plain(value):
    return value if isinstance(value, str) else ''.join(r.get('text', '') for r in value if isinstance(r, dict)) if isinstance(value, list) else ''


def _conversion_relation(value, header):
    if not re.search(r'转化|转变|转化关系', _plain(header)) or re.search(r'方程式|反应式', _plain(header)):
        return False
    if isinstance(value, list) and any(r.get('condition') for r in value if isinstance(r, dict)):
        return False
    parts = re.split(r'→|⟶', _plain(value))
    return len(parts) == 2 and all(re.fullmatch(r'\s*\[?[A-Z][A-Za-z0-9()]*\]?\s*', part) for part in parts)


def _block_fields(values, prefix, location, section_context=None):
    for bi, block in enumerate(_array(values, location + ".blocks")):
        if not isinstance(block, dict):
            continue
        path = prefix + [bi]
        context = dict(section_context or {})
        context['nearby_instructions'] = [_plain(b.get('content'))[:1000] for b in values[max(0, bi - 2):bi + 2]
                                           if isinstance(b, dict) and b.get('type') == 'paragraph']
        label = location + f"第{bi + 1}块"
        if block.get("type") == "paragraph":
            yield block, "content", path + ["content"], label, context
        elif block.get("type") == "table":
            headers = _array(block.get("headers", []), label + ".headers")
            for ci in range(len(headers)):
                yield headers, ci, path + ["headers", ci], label + f"表头{ci + 1}", context
            rows = _array(block.get("rows", []), label + ".rows")
            for ri, row in enumerate(rows):
                _array(row, label + f".rows[{ri}]")
                for ci in range(len(row)):
                    yield row, ci, path + ["rows", ri, ci], label + f"第{ri + 1}行第{ci + 1}列", {
                        **context, 'table_headers': copy.deepcopy(headers), 'table_row': copy.deepcopy(row),
                        'column': ci, 'conversion_relation': ci < len(headers) and _conversion_relation(row[ci], headers[ci]),
                    }


def _outline_fields(raw):
    if not isinstance(raw, dict):
        return
    outline = raw.get("outline", raw)
    prefix = ["outline"] if "outline" in raw else []
    if not isinstance(outline, dict):
        return
    for field in ("goals", "thinking"):
        values = _array(outline.get(field, []), f"$.outline.{field}")
        for index in range(len(values)):
            yield values, index, prefix + [field, index], f"导学案{field}第{index + 1}项", {}
    for si, section in enumerate(_array(outline.get("sections", []), "$.outline.sections")):
        if not isinstance(section, dict):
            raise ValueError(f"$.outline.sections[{si}]必须为对象")
        yield from _block_fields(section.get("blocks", []), prefix + ["sections", si, "blocks"], f"导学案第{si + 1}节", {"section_title": section.get("title", "")})


def _validate_fields(fields):
    targets = []
    for owner, key, path, location, context in fields:
        original = copy.deepcopy(owner.get(key) if isinstance(owner, dict) else owner[key])
        if context.get('conversion_relation'):
            owner[key] = normalize_paragraph(original, location, check_balance=False)
            continue
        caught = None
        try:
            owner[key] = _check(original, location)
        except ValueError as exc:
            if "原子数不守恒" not in str(exc):
                raise
            caught = exc
        try:
            detail = equation_details(original) if isinstance(original, (str, list)) else None
        except (ValueError, TypeError, KeyError):
            if caught is not None: raise caught
            continue  # Ordinary prose is not treated as a chemical-only equation.
        if detail and any(eq['left_atoms'] != eq['right_atoms'] or eq['left_charge'] != eq['right_charge']
                          for eq in detail['equations']):
            targets.append({'path': path, 'location': location, 'value': original, 'context': context, **detail})
    if targets:
        raise EquationBalanceError(targets)


def validate_outline(outline):
    """Normalize rich text and collect every unbalanced equation in the outline."""
    _validate_fields(_outline_fields(outline))


def validate_study_guide_result(result):
    """Return precise paths for full outlines and patch replacement cells alike."""
    def patches():
        if isinstance(result, dict):
            for ci, change in enumerate(_array(result.get("changes", []), "$.changes")):
                if isinstance(change, dict):
                    yield from _block_fields(change.get("replacement", []), ["changes", ci, "replacement"], f"导学案修改第{ci + 1}项")
    _validate_fields(chain(_outline_fields(result), patches()))


def validate_practice(content):
    """Validate rich text in all student and answer fields."""
    for group in ("choice", "written", "optional"):
        for qi, question in enumerate(content.get(group, []), 1):
            path = f"限时练习{group}第{qi}题"
            for field in ("stem", "answer", "explanation"):
                _check(question.get(field), f"{path}{field}")
            for oi, option in enumerate(question.get("options") or [], 1):
                _check(option, f"{path}选项{oi}")
