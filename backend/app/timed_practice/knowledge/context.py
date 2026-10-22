"""【规则处理·限时练习】按课题相关性与预算选择已有题源片段，不发送知识库请求。"""

import re

BUDGET = 12000


def prepare_source_context(sources, lesson, origin="any"):
    topic = re.sub(
        r"^第[一二三四五六七八九十\d]+[章节]\s*", "", lesson.get("chapter", "")
    ).strip()
    period = (
        lesson.get("period", "")
        .replace("第一", "第1")
        .replace("第二", "第2")
        .replace("第三", "第3")
    )

    def priority(source):
        title = source.get("title", "")
        score = 100 if topic and topic in title else 0
        if (
            score
            and period
            and period
            in title.replace("第一", "第1")
            .replace("第二", "第2")
            .replace("第三", "第3")
        ):
            score += 20
        if topic and topic in source.get("evidence", ""):
            score += 10
        if source.get("category") in ("textbook", "teacher_book"):
            score += 5
        return score

    candidates = [
        s
        for s in sources
        if not re.search(r"模板|格式样例|测试样例", s.get("title", ""))
    ]
    candidates = sorted(candidates, key=priority, reverse=True)
    selected = []
    used = 0
    excluded = 0
    for source in candidates:
        evidence = source.get("evidence", "")
        if not evidence:
            continue
        truncated = False
        if len(evidence) > BUDGET:
            if origin == "original":
                # Reserve the full context budget for this original-source excerpt.
                if selected:
                    continue
                excerpt = evidence[:BUDGET]
            else:
                start = (
                    max(0, evidence.find(topic) - 400)
                    if topic and topic in evidence
                    else 0
                )
                excerpt = evidence[start : start + min(4500, BUDGET - used)]
            evidence = excerpt
            truncated = True
        if used + len(evidence) > BUDGET or len(selected) >= 10:
            excluded += 1
            continue
        item = {
            k: source[k]
            for k in ("id", "title", "category", "locator", "verified")
            if k in source
        }
        item["evidence"] = evidence
        if truncated:
            item["excerpt_truncated"] = True
        selected.append(item)
        used += len(evidence)
    stats = dict(
        total_count=len(sources),
        selected_count=len(selected),
        evidence_chars=used,
        excluded_format_count=len(sources) - len(candidates),
        budget_excluded_count=excluded,
    )
    return selected, stats
