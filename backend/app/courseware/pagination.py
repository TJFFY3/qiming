"""Paginate native slide content without shortening text or shrinking fonts."""

import copy
import math
import re


def fits(paragraphs):
    # Use the same semantic runs and width metric as the template renderer.
    from ppt_tools import _runs, _width

    if len(paragraphs) > 6:
        return False
    runs = [_runs(p) for p in paragraphs]
    texts = ["".join(r["text"] for r in p) for p in runs]
    if sum(map(len, texts)) > 200:
        return False
    conditions = 0
    for paragraph, text in zip(runs, texts):
        if any(r.get("condition_label") for r in paragraph):
            conditions += 1
            if "\n" in text or _width(text) > 34:
                return False
    lines = sum(sum(max(1, math.ceil(_width(line) / 34)) for line in t.split("\n")) for t in texts)
    return lines * 1.02 + len(texts) * .32 + conditions * 1.46 <= 13.3


def fragment(value, start, end):
    if isinstance(value, str):
        return value[start:end]
    result, offset = [], 0
    for run in value:
        lo, hi = max(start, offset), min(end, offset + len(run["text"]))
        if lo < hi:
            result.append({**run, "text": run["text"][lo - offset:hi - offset]})
        offset += len(run["text"])
    return result


def split_paragraph(value, page, paragraph):
    if fits([value]):
        return [value]
    text = value if isinstance(value, str) else "".join(r["text"] for r in value)
    if re.search(r"[=→⟶⇌↔]", text) or (isinstance(value, list) and any(r.get("condition") for r in value)):
        raise ValueError(f"第{page}页第{paragraph}段反应式无法单页容纳，请将说明与反应式分段，保留完整方程式")
    protected = [(m.start(), m.end()) for m in re.finditer(r"\d*\[[^\[\]]+\]|\d*[A-Za-z][A-Za-z0-9()^+−-]*", text)]
    if isinstance(value, list):
        offset = 0
        for run in value:
            if any(run.get(k) for k in ("sub", "sup", "charge", "isotope")):
                protected.append((offset, offset + len(run["text"])))
            offset += len(run["text"])
    cuts = [i for i in range(1, len(text) + 1) if not any(a < i < b for a, b in protected)]
    result, start = [], 0
    while start < len(text):
        candidates = [i for i in cuts if i > start]
        lo, hi = 0, len(candidates)
        while lo < hi:
            mid = (lo + hi) // 2
            if fits([fragment(value, start, candidates[mid])]):
                lo = mid + 1
            else:
                hi = mid
        if not lo:
            raise ValueError(f"第{page}页第{paragraph}段包含不可拆分的超长内容，请调整该段")
        end = candidates[lo - 1]
        if end < len(text):
            natural = [i for i in candidates[:lo] if text[i - 1] in "。！？；\n，、 " and text[start:i].strip()]
            if natural:
                end = natural[-1]
        result.append(fragment(value, start, end))
        start = end
    return result


def paginate_slides(slides, allow_split=True):
    result = []
    for number, slide in enumerate(slides, 1):
        if fits(slide["paragraphs"]):
            result.append(copy.deepcopy(slide))
            continue
        if not allow_split:
            raise ValueError(f"第{number}页正文过密，局部修改不能改变页序，请精简该页或选择调整页数与结构")
        current = []
        for index, paragraph in enumerate(slide["paragraphs"], 1):
            for piece in split_paragraph(paragraph, number, index):
                if current and not fits(current + [piece]):
                    result.append({**copy.deepcopy(slide), "paragraphs": current})
                    current = []
                current.append(piece)
        if current:
            result.append({**copy.deepcopy(slide), "paragraphs": current})
    if len(result) > 60:
        raise ValueError(f"自动分页后共{len(result)}页，超过60页，请精简内容")
    return result
