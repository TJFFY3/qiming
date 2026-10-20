"""Normalize unambiguous legacy equation typography, never source evidence."""

import copy
import re

ELEMENTS = "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og".split()
ATOM = "(?:" + "|".join(sorted(ELEMENTS, key=len, reverse=True)) + r")\d*"
FORMULA = re.compile(rf"(?:{ATOM}|\((?:{ATOM})+\)\d*)+")
TOKEN = re.compile(
    r"\[[^\[\]]+\]|(?<![A-Za-z_\[])([A-Z][A-Za-z0-9()]*)(?![A-Za-z0-9_\]^]|[+-](?:\s|$))"
)
CONDITION = re.compile(
    r"={2,}[ \t]*([^=\r\n\\(),]{1,30}?)[ \t]*={2,}|([△Δ])[ \t]*(?:→|⟶|=+)"
)
BREAK = re.compile(r"<br\s*/?>", re.I)
SPECIAL = ("condition", "sub", "sup", "charge", "isotope")


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


def _group(runs, equation_context=False):
    runs = [{**r, "text": _coefficient(BREAK.sub("\n", r["text"]))} for r in runs]
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


def _rich(value):
    if isinstance(value, str):
        return legacy_runs(value)
    if not isinstance(value, list):
        return value
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
