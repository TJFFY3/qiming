"""Practice typography only: preserve chemistry, question text and source evidence."""

import copy
import re

from ..chemistry_format import FORMULA

# These are formatting markers only when immediately between chemical terms.
CONDITION = re.compile(
    r"[=═→⟶]*[ \t]*(?:"
    r"[（(](?P<catalyst>(?:MnO2|二氧化锰|催化剂)(?:[ ,，、/]*(?:△|Δ|加热))?)[)）]"
    r"|(?P<bare>MnO2[,，、/]*(?:△|Δ|加热))"
    r"|(?P<label>点燃|通电|高温|加热|△|Δ))"
    r"[ \t]*[=═→⟶]*"
)
MOLECULE = re.compile(
    r"(?<![A-Za-z_])(?P<body>[A-Z][A-Za-z0-9]*(?:\([A-Za-z0-9]+\)\d*)*)"
    r"(?:\^(?P<charge>\d*[+-]))?"
)


def _sides(text, start, end):
    left = re.search(r"([A-Z][A-Za-z0-9()]*)(?:[↑↓])?\s*$", re.sub(r"[（(](?:浓|稀)[)）]\s*$", "", text[:start]))
    right = re.match(r"\s*\d*([A-Z][A-Za-z0-9]*(?:\([A-Za-z0-9]+\)\d*)*)", text[end:])
    return left and right and FORMULA.fullmatch(left[1]) and FORMULA.fullmatch(right[1])


def format_runs(runs):
    """Repair bare formulas and lost condition operators across styled run boundaries."""
    text = "".join(r["text"] for r in runs)
    styles = []
    explicit = {}
    for run in runs:
        if run.get("condition") or run.get("isotope"):
            explicit[len(styles)] = (len(styles) + len(run["text"]), run)
        styles.extend(
            [{k: v for k, v in run.items() if k != "text"}] * len(run["text"])
        )
    conditions = {}
    protected = {
        i
        for i, style in enumerate(styles)
        if style.get("condition") or style.get("isotope")
    }
    for match in CONDITION.finditer(text):
        if any(i in protected for i in range(match.start(), match.end())):
            continue
        if _sides(text, match.start(), match.end()):
            label = (match["catalyst"] or match["bare"] or match["label"]).replace("Δ", "△")
            label = re.sub(r"[,，/]", "、", label)
            conditions[match.start()] = (match.end(), label)
            protected.update(range(match.start(), match.end()))
    subs, charges = set(), set()
    # Mark each formula separately: stoichiometric coefficients never enter the body.
    lexical = "".join(" " if i in protected else char for i, char in enumerate(text))
    for match in MOLECULE.finditer(lexical):
        if not FORMULA.fullmatch(match["body"]) or any(
            i in protected for i in range(match.start(), match.end())
        ):
            continue
        # A trailing ionic sign is ambiguous without explicit ^ charge markup.
        # Preserve that token rather than turning its charge magnitude into a subscript.
        if not match["charge"] and re.match(r"[+-](?:\s|$)", text[match.end() :]):
            continue
        subs.update(
            i
            for i in range(match.start("body"), match.end("body"))
            if text[i].isdigit()
        )
        if match["charge"]:
            charges.update(range(match.start("charge"), match.end("charge")))
    result = []

    def append(fragment, style):
        if (
            result
            and not style.get("condition")
            and {k: v for k, v in result[-1].items() if k != "text"} == style
        ):
            result[-1]["text"] += fragment
        else:
            result.append(dict(text=fragment, **style))

    i = 0
    while i < len(text):
        if i in explicit:
            end, run = explicit[i]
            result.append(copy.deepcopy(run))
            i = end
            continue
        if i in conditions:
            end, label = conditions[i]
            style = {
                k: v
                for k, v in styles[i].items()
                if k not in ("sub", "sup", "charge", "isotope")
            }
            result.append(dict(text=label, **style, condition=True))
            i = end
            continue
        style = dict(styles[i])
        if i in charges:
            style.update(sup=True, charge=True)
            style.pop("sub", None)
        elif i in subs and not any(
            style.get(k) for k in ("sub", "sup", "charge", "condition", "isotope")
        ):
            style["sub"] = True
        if text[i] != "^" or i + 1 not in charges:
            append(text[i], style)
        i += 1
    return result or copy.deepcopy(runs)


def format_content(content):
    # Local import avoids a document/formatter import cycle.
    from .documents import canonical_rich

    result = copy.deepcopy(content)
    for group in ("choice", "written", "optional"):
        for question in result.get(group, []):
            for field in ("stem", "answer", "explanation"):
                question[field] = canonical_rich(question[field])
            if question.get("options"):
                question["options"] = [canonical_rich(v) for v in question["options"]]
    return result
