"""【规则处理·化学排版】将化学标记转换为富文本，保留正文语义。"""

import copy
import re

ELEMENTS = "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og".split()
ATOM = "(?:" + "|".join(sorted(ELEMENTS, key=len, reverse=True)) + r")\d*"
FORMULA = re.compile(rf"(?:{ATOM}|\((?:{ATOM})+\)\d*)+")
TOKEN = re.compile(
    r"\[[^\[\]]+\]|(?<![A-Za-z_\[])([A-Z][A-Za-z0-9()]*)(?![A-Za-z0-9_\]^]|[+-](?:\s|$))"
)
CONDITION = re.compile(r"=+[ \t]*([^=\r\n\\(),]{1,30}?)[ \t]*=+|([△Δ])[ \t]*(?:→|⟶|=+)")
BREAK = re.compile(r"<br\s*/?>", re.I)
SPECIAL = ("condition", "sub", "sup", "charge", "isotope")
SUBSCRIPT_MARKER = re.compile(r"_(?:\{(\d+)\}|(\d+))")
MARKED_FORMULA = re.compile(
    r"(?<![A-Za-z0-9_])\d*(?P<body>[A-Z][A-Za-z0-9()]*"
    r"(?:_(?:\{\d+\}|\d+)[A-Za-z0-9()]*)+)(?=$|[^A-Za-z0-9_{}]|_{2,})"
)


def normalize_subscript_markers(value):
    """Remove only numeric subscript syntax inside recognized chemical formulas."""
    if isinstance(value, str):
        runs = [{"text": value}]
    elif isinstance(value, list) and all(
        isinstance(run, dict) and isinstance(run.get("text"), str) for run in value
    ):
        runs = value
    else:
        return value
    text = "".join(run["text"] for run in runs)
    removed = set()
    for match in MARKED_FORMULA.finditer(text):
        body = match["body"]
        plain = SUBSCRIPT_MARKER.sub(lambda m: m[1] or m[2], body)
        if not FORMULA.fullmatch(plain):
            continue
        for marker in SUBSCRIPT_MARKER.finditer(body):
            removed.update(
                match.start("body") + index
                for index in range(marker.start(), marker.end())
                if body[index] in "_{}"
            )
    if not removed:
        return value
    result, offset = [], 0
    for run in runs:
        fragment = "".join(
            char
            for index, char in enumerate(run["text"], offset)
            if index not in removed
        )
        offset += len(run["text"])
        if fragment:
            result.append({**run, "text": fragment})
    return "".join(run["text"] for run in result) if isinstance(value, str) else result


def _has_formula(text):
    return any(
        FORMULA.fullmatch(m.group(1) or m.group()[1:-1]) for m in TOKEN.finditer(text)
    )


def _mark_formulas(text):
    return TOKEN.sub(
        lambda m: (
            "[" + m.group(1) + "]"
            if m.group(1) and FORMULA.fullmatch(m.group(1))
            else m.group()
        ),
        text,
    )


def _coefficient(text):
    # Brackets mark a molecule, not an entire reaction. Older model outputs
    # wrapped the whole equation, causing every coefficient to become subscript.
    text = re.sub(
        r"\[([^\[\]]+)\]",
        lambda m: (
            m[1] if re.search(r"=|→|⟶|⇌|↔", m[1]) and _has_formula(m[1]) else m[0]
        ),
        text,
    )
    # A stoichiometric coefficient must stay outside formula subscript markup.
    return re.sub(
        r"\[(\d+)([A-Z][A-Za-z0-9()]*)\]",
        lambda m: m[1] + "[" + m[2] + "]" if FORMULA.fullmatch(m[2]) else m[0],
        text,
    )


def _label(match):
    return match.group(1) or "△"


def legacy_runs(text):
    """Only promote condition markers with recognizable formulas on both sides."""
    runs = _group([{"text": text}])
    return (
        runs
        if any(r.get("condition") for r in runs)
        else _coefficient(BREAK.sub("\n", text))
    )


def _equation_side(text):
    """Recognize a complete neutral formula side; never join prose lines."""
    for term in text.strip().split("+"):
        term = re.sub(r"[\s↑↓]", "", term)
        term = re.sub(r"^\d+", "", term)
        if term.startswith("[") and term.endswith("]"):
            term = term[1:-1]
        if not FORMULA.fullmatch(term):
            return False
    return True


SPLIT_CONDITION = re.compile(
    r"^([^\r\n]+?)([ \t]*\r?\n[ \t]*)"
    r"(高温|加热|点燃|通电|光照|△|Δ|催化剂)"
    r"([ \t]*\r?\n[ \t]*(?:=+|→|⟶)[ \t]*)([^\r\n]+)(?=\r?$)",
    re.M,
)


def _join_equation_lines(runs):
    text = "".join(r["text"] for r in runs)
    edits = []
    for match in SPLIT_CONDITION.finditer(text):
        if _equation_side(match[1]) and _equation_side(match[5]):
            edits.extend(
                [
                    (match.start(2), match.end(2), " ==="),
                    (match.start(4), match.end(4), "=== "),
                ]
            )
    if not edits:
        return runs
    spans, offset = [], 0
    for run in runs:
        spans.append((offset, offset + len(run["text"]), run))
        offset += len(run["text"])
    result = []

    def keep(start, end):
        for left, right, run in spans:
            lo, hi = max(start, left), min(end, right)
            if lo < hi:
                result.append({**run, "text": text[lo:hi]})

    position = 0
    for start, end, replacement in edits:
        keep(position, start)
        style = next(run for left, right, run in spans if left <= start < right)
        result.append({**style, "text": replacement})
        position = end
    keep(position, len(text))
    return result


def _group(runs, equation_context=False):
    runs = [{**r, "text": _coefficient(BREAK.sub("\n", r["text"]))} for r in runs]
    runs = _join_equation_lines(runs)
    text = "".join(r["text"] for r in runs)
    matches, lines, offset = [], ([(0, len(text))] if equation_context else []), 0
    for line in text.split("\n"):
        found = [
            m
            for m in CONDITION.finditer(line)
            if _label(m).strip()
            and _has_formula(line[: m.start()])
            and _has_formula(line[m.end() :])
        ]
        if found:
            lines.append((offset, offset + len(line)))
            matches.extend(
                (
                    offset + m.start(),
                    offset + m.end(),
                    offset + m.start(1 if m.group(1) is not None else 2),
                    _label(m).strip(),
                )
                for m in found
            )
        offset += len(line) + 1
    if not lines:
        return runs
    spans, offset = [], 0
    for run in runs:
        spans.append((offset, offset + len(run["text"]), run))
        offset += len(run["text"])
    result = []
    crossing = [
        m
        for m in TOKEN.finditer(text)
        if m.group(1)
        and FORMULA.fullmatch(m.group(1))
        and any(m.start() < right < m.end() for _, right, _ in spans)
    ]

    def piece(run, lo, hi, active):
        cuts = {lo, hi}
        overlapping = [
            m for m in crossing if active and m.start() < hi and m.end() > lo
        ]
        for m in overlapping:
            cuts.update(range(max(lo, m.start()), min(hi, m.end()) + 1))
        points = sorted(cuts)
        for start, end in zip(points, points[1:]):
            fragment = text[start:end]
            inside = any(m.start() <= start < m.end() for m in overlapping)
            if inside:
                result.append(
                    {
                        **run,
                        "text": fragment,
                        **(
                            {"sub": True}
                            if fragment.isascii() and fragment.isdigit()
                            else {}
                        ),
                    }
                )
            else:
                result.append(
                    {**run, "text": _mark_formulas(fragment) if active else fragment}
                )

    def gap(start, end):
        for left, right, run in spans:
            lo, hi = max(start, left), min(end, right)
            if lo >= hi:
                continue
            # Keep ordinary runs intact unless a line boundary changes formatting context.
            cuts = sorted(
                {lo, hi} | {p for a, b in lines for p in (a, b) if lo < p < hi}
            )
            for first, last in zip(cuts, cuts[1:]):
                active = any(a <= first < b for a, b in lines)
                piece(run, first, last, active)

    position = 0
    for start, end, label_start, label in matches:
        gap(position, start)
        style = next(run for left, right, run in spans if left <= label_start < right)
        result.append({**style, "text": label, "condition": True})
        position = end
    gap(position, len(text))
    merged = []
    for run in result:
        if (
            merged
            and not run.get("condition")
            and {k: v for k, v in run.items() if k != "text"}
            == {k: v for k, v in merged[-1].items() if k != "text"}
        ):
            merged[-1]["text"] += run["text"]
        else:
            merged.append(run)
    return merged


def _join_semantic_condition_lines(value):
    value = [dict(run) if isinstance(run, dict) else run for run in value]
    for i in range(1, len(value) - 1):
        left, condition, right = value[i - 1 : i + 2]
        if not all(
            isinstance(run, dict) and isinstance(run.get("text"), str)
            for run in (left, condition, right)
        ) or not condition.get("condition"):
            continue
        end = re.search(r"[ \t]*\r?\n[ \t]*$", left["text"])
        start = re.match(r"[ \t]*\r?\n[ \t]*(?:=+|→|⟶)?[ \t]*", right["text"])
        if not end or not start:
            continue
        lhs = left["text"][: end.start()].split("\n")[-1]
        rhs = right["text"][start.end() :].split("\n")[0]
        if _equation_side(lhs) and _equation_side(rhs):
            left["text"] = left["text"][: end.start()] + " "
            right["text"] = " " + right["text"][start.end() :]
    return value


def _rich(value):
    value = normalize_subscript_markers(value)
    if isinstance(value, str):
        return legacy_runs(value)
    if not isinstance(value, list):
        return value
    value = _join_semantic_condition_lines(value)
    result, group = [], []

    def flush():
        result.extend(_group(group))
        group.clear()

    for run in value:
        if (
            not isinstance(run, dict)
            or not isinstance(run.get("text"), str)
            or any(run.get(k) for k in SPECIAL)
        ):
            flush()
            result.append(run)
        else:
            group.append(run)
    flush()
    return result


def normalize_chemistry(value):
    value = copy.deepcopy(value)
    notes = []

    def field(obj, key, path):
        old = obj[key]
        new = _rich(old)
        if new != old:
            obj[key] = new
            notes.append({"method": "chemistry_format", "path": path})

    def blocks(items, path):
        if not isinstance(items, list):
            return
        for i, block in enumerate(items):
            if not isinstance(block, dict):
                continue
            p = f"{path}[{i}]"
            if block.get("type") == "paragraph" and "content" in block:
                field(block, "content", p + ".content")
            elif block.get("type") == "table":
                headers = block.get("headers")
                if isinstance(headers, list):
                    for j in range(len(headers)):
                        field(headers, j, p + f".headers[{j}]")
                rows = block.get("rows")
                if isinstance(rows, list):
                    for j, row in enumerate(rows):
                        if isinstance(row, list):
                            for k in range(len(row)):
                                field(row, k, p + f".rows[{j}][{k}]")

    if not isinstance(value, dict):
        return value, notes
    outline = value.get("outline", value)
    if isinstance(outline, dict):
        for key in ("goals", "thinking"):
            if isinstance(outline.get(key), list):
                for i in range(len(outline[key])):
                    field(outline[key], i, f"$.outline.{key}[{i}]")
        if isinstance(outline.get("sections"), list):
            for i, section in enumerate(outline["sections"]):
                if isinstance(section, dict):
                    blocks(section.get("blocks"), f"$.outline.sections[{i}].blocks")
    if isinstance(value.get("changes"), list):
        for i, change in enumerate(value["changes"]):
            if isinstance(change, dict):
                blocks(change.get("replacement"), f"$.changes[{i}].replacement")
    return value, notes
