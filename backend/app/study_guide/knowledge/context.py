"""【规则处理·导学案】按修改任务与字符预算节选已有资料，不重新检索知识库。"""

import re

from backend.app.shared.prompts.lesson_context import LESSON_CONTEXT

REVISION_EVIDENCE_BUDGET = 12000


def revision_source_context(sources, prompt):
    # Optimization text contains explicit teacher requirements too. Remove only
    # the repeated lesson metadata, not the optimization block.
    request = re.sub(LESSON_CONTEXT, "", prompt, flags=re.M).lower()
    terms = set(re.findall(r"[a-z][a-z0-9]*", request))
    for phrase in re.findall(r"[\u4e00-\u9fff]+", request):
        terms.update(phrase[i:i + 2] for i in range(len(phrase) - 1))

    result, remaining = [], REVISION_EVIDENCE_BUDGET
    for index, source in enumerate(sources):
        evidence = source["evidence"]
        # Share the total budget fairly, carrying unused space to later sources.
        allowance = remaining // (len(sources) - index)
        if len(evidence) <= allowance:
            excerpt = evidence
        elif allowance:
            width = min(800, allowance)
            starts = range(0, len(evidence), max(1, width // 2))
            ranked = sorted(starts, key=lambda start: (
                -sum(term in evidence[start:start + width].lower() for term in terms),
                start,
            ))
            spans, used = [], 0
            separator = "\n[…]\n"
            for start in ranked:
                end = min(start + width, len(evidence))
                if any(start < right and end > left for left, right in spans):
                    continue
                cost = end - start + (len(separator) if spans else 0)
                if used + cost > allowance:
                    continue
                spans.append((start, end))
                used += cost
            excerpt = separator.join(evidence[a:b] for a, b in sorted(spans))
        else:
            excerpt = ""
        remaining -= len(excerpt)
        result.append({
            **{k: v for k, v in source.items() if k != "evidence"},
            "evidence_excerpt": excerpt,
            "excerpt_truncated": len(excerpt) < len(evidence),
        })
    return result
