"""【规则处理·限时练习】解析教师要求的优先级、题量增减、总分、时长与题源限制。"""

import re
from backend.app.timed_practice.domain.models import DEFAULT

START = "【限时练习优化设置】"
END = "【限时练习优化设置结束】"
BLOCK = re.compile(re.escape(START) + r"(.*?)" + re.escape(END), re.S)
LABELS = {
    "用时": "duration",
    "满分": "score",
    "题型和数量": "questions",
    "题目难度": "difficulty",
    "出题方式": "origin",
    "补充要求": "extra",
}


def body_text(prompt):
    return BLOCK.sub("", prompt).strip()


def numeric(value, label, maximum):
    hit = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:分钟|分)?\s*", value)
    if not hit or not 0 < float(hit[1]) <= maximum:
        raise ValueError(f"{label}须为大于0且不超过{maximum}的数字")
    return float(hit[1])


def quantity_counts(quantity, current_counts=None):
    """Resolve absolute counts and relative edits in their written order."""
    kinds, result = {}, {}
    for operation, number, kind in re.findall(
        r"(?:(增加|新增|追加|再加|减少|删除|删去|去掉|删掉)\s*)?"
        r"(\d+)\s*道\s*(单项选择题|单选题|选择题|填空题|简答题|解答题|计算题|非选择题|选做题)",
        quantity,
    ):
        category = (
            "optional"
            if kind == "选做题"
            else "choice"
            if kind in ("选择题", "单选题", "单项选择题")
            else "fill"
            if kind == "填空题"
            else "calculation"
            if kind == "计算题"
            else "written"
        )
        key = (
            category + "_count"
            if category in ("choice", "optional")
            else "written_count"
        )
        if operation:
            sign = 1 if operation in ("增加", "新增", "追加", "再加") else -1
            result[key] = result.get(key, (current_counts or {}).get(key, 0)) + sign * int(number)
        else:
            kinds[category] = int(number)
            result[key] = sum(
                value for name, value in kinds.items()
                if (name == category if key != "written_count" else name not in ("choice", "optional"))
            )
    return result


def resolve_requirements(settings, prompt, previous=None, previous_requirements=None):
    options = dict(settings["options"])
    previous = previous or {}
    prior = previous_requirements or {}
    # The filled section remains editable text, so its current values override the dialog snapshot.
    for block in BLOCK.findall(prompt):
        for line in block.splitlines():
            match = re.match(r"^([^：:]+)[：:]\s*(.*)$", line.strip())
            if match and match[1] in LABELS and match[2].strip():
                options[LABELS[match[1]]] = match[2].strip()
    body = options.get("extra", "") + "\n" + body_text(prompt)
    duration = (
        prior.get("duration", previous.get("duration", 35))
        if options["duration"] == DEFAULT
        else numeric(options["duration"], "用时", 180)
    )
    score = (
        prior.get("total_score", previous.get("total_score", 100))
        if options["score"] == DEFAULT
        else numeric(options["score"], "满分", 1000)
    )
    matches = []
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*分钟", body):
        before = re.split(r"[，,。；;\n]", body[:match.start()])[-1]
        after = body[match.end():]
        per_question = list(re.finditer(r"每(?:道|个)?(?:题|小题)|单题|每(?:道)?(?:选择|单选|解答|填空|计算)题", before))
        total = list(re.finditer(r"总用时|总时长|总时间|整卷|全卷|试卷|整份练习", before))
        if per_question and (not total or per_question[-1].start() > total[-1].start()):
            continue
        if re.match(r"\s*(?:[/／]\s*(?:题|小题)|每(?:道)?题|一(?:道)?题)", after):
            continue
        matches.append(match[1])
    if matches:
        duration = numeric(matches[-1], "用时", 180)
    matches = re.findall(r"(?:满分|总分)(?:为|是|改为|：|:|\s)*([\d.]+)\s*分", body)
    if matches:
        score = numeric(matches[-1], "满分", 1000)
    # Old records may lack this marker. Keep their current counts unless the
    # caller can recover a different dialog setting from the original job.
    same_question_setting = bool(previous and prior) and prior.get("question_setting", options["questions"]) == options["questions"]
    counts = (
        {
            k: v
            for k, v in prior.items()
            if k.endswith("_count") or k in ("written_score", "choice_score")
        }
        if options["questions"] == DEFAULT or same_question_setting
        else {}
    )
    actual = {group + "_count": len(previous.get(group, [])) for group in ("choice", "written", "optional")}
    if same_question_setting:
        counts.update(actual)
    quantities = (body,) if same_question_setting else (options["questions"], body)
    for quantity in quantities:
        changed = quantity_counts(quantity, {**actual, **counts})
        if changed:
            counts.pop("written_score", None)
            counts.pop("choice_score", None)
            counts.update(changed)
    # A changed total or duration invalidates the old default's hard-coded score split.
    if duration != 35 or score != 100:
        counts.pop("written_score", None)
        counts.pop("choice_score", None)
    for key, value in counts.items():
        if key.endswith("_count") and not 0 <= value <= (
            60 if key == "choice_count" else 10 if key == "optional_count" else 40
        ):
            raise ValueError("题目数量超出支持范围")
    if (
        not counts
        and options["questions"] == DEFAULT
        and not previous
        and duration == 35
        and score == 100
    ):
        counts = {
            "choice_count": 14,
            "optional_count": 2,
            "written_score": 44,
            "choice_score": 4,
        }
    origin = prior.get("origin", "any") if options["origin"] == DEFAULT else "any"
    for origin_text in (options["origin"], body):
        for match in re.finditer(
            r"只(?:用|使用)(?:教材)?原题|允许改编原题|允许改编和出新题", origin_text
        ):
            token = match.group()
            origin = (
                "original"
                if token.startswith("只")
                else "adapted"
                if token == "允许改编原题"
                else "any"
            )
    return {
        "duration": duration, "total_score": score, "origin": origin,
        "question_setting": options["questions"], **counts,
    }
