"""【规则处理·互动课件】解析化学富文本、核验元素守恒并规范化逐页内容。"""

import copy
import re
from collections import Counter

from backend.app.shared.chemistry.formatting import FORMULA, _group, _rich
from backend.app.shared.chemistry.serialized_rich import decode_rich
from backend.app.courseware.domain.models import Run

OPERATOR = re.compile(r"=+|→|⟶|⇌|↔")


def atoms(side):
    total = Counter()
    for term in side.strip().split("+"):
        term = re.sub(r"[\s\[\]↑↓]", "", term)
        match = re.fullmatch(r"(\d*)([A-Z][A-Za-z0-9()]*)", term)
        if not match or not FORMULA.fullmatch(match[2]):
            return None
        coefficient = int(match[1] or 1)
        stack = [Counter()]
        for token in re.findall(r"[A-Z][a-z]?\d*|\(|\)\d*", match[2]):
            if token == "(":
                stack.append(Counter())
            elif token.startswith(")"):
                if len(stack) == 1:
                    return None
                group = stack.pop()
                stack[-1].update({k: v * int(token[1:] or 1) for k, v in group.items()})
            else:
                element, count = re.fullmatch(r"([A-Z][a-z]?)(\d*)", token).groups()
                stack[-1][element] += int(count or 1)
        if len(stack) != 1:
            return None
        total.update({k: v * coefficient for k, v in stack[0].items()})
    return total or None


def normalize_paragraph(value, location, check_balance=True):
    value = decode_rich(value, Run)
    boundaries = []
    if isinstance(value, list) and not any(r.get("condition") for r in value):
        position = 0
        for run in value[:-1]:
            position += len(run["text"])
            boundaries.append(position)
    original_text = (
        value if isinstance(value, str) else "".join(r["text"] for r in value)
    )
    value = _rich(value)
    runs = [{"text": value}] if isinstance(value, str) else value
    # Only chemical-only paragraphs are treated as equations. Prose, ions and
    # explicit sub/sup/isotope notation are not guessed by the balance checker.
    text = "".join("=" if r.get("condition") else r["text"] for r in runs)
    parts = OPERATOR.split(text)
    counts = [atoms(p) for p in parts]
    equation = len(parts) == 2 and all(counts)
    if check_balance and equation and counts[0] != counts[1]:
        raise ValueError(
            f"{location}原子数不守恒，请核对反应物、生成物和化学计量数，返回修正后的完整方程式"
        )
    if not OPERATOR.search(text) and "+" in text:
        # Do not infer a reaction boundary inside a molecule or a plain mixture.
        # Only the model's explicit adjoining runs provide boundary evidence.
        if any(
            atoms(original_text[:p])
            and atoms(original_text[p:])
            and not original_text[:p].rstrip().endswith("+")
            and not original_text[p:].lstrip().startswith("+")
            for p in boundaries
        ):
            raise ValueError(
                f"{location}反应式缺少连接符，请补齐完整反应式，不能直接拼接反应物和生成物"
            )
    if equation:
        result, group = [], []
        for run in runs:
            if any(
                run.get(k) for k in ("condition", "sub", "sup", "charge", "isotope")
            ):
                result.extend(_group(group, equation_context=True))
                group = []
                result.append(run)
            else:
                group.append(run)
        result.extend(_group(group, equation_context=True))
        return result if not isinstance(value, str) else result[0]["text"]
    return value


def normalize_deck(content, check_balance=True):
    content = copy.deepcopy(content)
    for i, slide in enumerate(content["slides"]):
        slide["paragraphs"] = [
            normalize_paragraph(p, f"第{i + 1}页第{j + 1}段：", check_balance=check_balance)
            for j, p in enumerate(slide["paragraphs"])
        ]
    return content
