"""【规则处理·限时练习】解析指定题号并保护未涉及题目，阻止局部修改引发整卷漂移。"""

import re


def question_scope(prompt):
    number = r"(?:\d+|[零一二三四五六七八九十百两]+)"
    references = re.finditer(
        rf"第\s*({number}(?:\s*题?\s*[、,，和及到至—-]\s*(?:第\s*)?{number})*)\s*题",
        prompt,
    )
    digits = {char: i for i, char in enumerate("零一二三四五六七八九")}
    digits["两"] = 2

    def parse(value):
        if value.isdecimal():
            result = int(value)
        else:
            hundreds, _, remainder = value.partition("百")
            result = digits.get(hundreds, 1) * 100 if "百" in value else 0
            rest = remainder.lstrip("零") if "百" in value else value
            tens, _, units = rest.partition("十")
            result += (digits.get(tens, 1) * 10 + digits.get(units, 0)) if "十" in rest else digits.get(rest, 0)
        if not 1 <= result <= 110:
            raise ValueError("指定题号必须在1至110之间")
        return result

    targets, protected = set(), set()
    for match in references:
        before = re.split(r"[，,。；;\n]", prompt[:match.start()])[-1]
        after = prompt[match.end():]
        # Use the closest operation, so “保留第2题并修改第1题” gives
        # each reference its own instruction rather than preserving both.
        operations = list(re.finditer(
            r"保留|保持|不(?:要|必|需|需要)?(?:修改|改动|调整|改)|无需修改|修改|改动|调整|改写|更新|替换|补充|改",
            before,
        ))
        preserve = (
            bool(operations and re.match(r"保留|保持|不|无需", operations[-1].group()))
            or re.match(r"\s*(?:保持不变|保持原样|不变|不动|不(?:要|必|需|需要)?(?:修改|改动|改)|无需修改)", after)
        )
        selected = protected if preserve else targets
        for group in re.split(r"[、,，和及]", match[1]):
            values = [parse(value) for value in re.findall(number, group)]
            selected.update(range(min(values), max(values) + 1) if len(values) == 2 else values)
    return targets, protected


def validate_revision_scope(content, previous, prompt):
    targets, protected = question_scope(prompt)
    if not targets and not protected:
        return
    old = [q for group in ("choice", "written", "optional") for q in previous[group]]
    new = [q for group in ("choice", "written", "optional") for q in content[group]]
    if any(number > len(old) for number in targets | protected):
        raise ValueError("指定题号超出原卷范围")
    if any(len(content[group]) != len(previous[group]) for group in ("choice", "written", "optional")):
        raise ValueError("指定题目修改不能同时改变题型数量，请单独提交题量调整")
    for index, (before, after) in enumerate(zip(old, new), 1):
        if (index in protected or (targets and index not in targets)) and before != after:
            raise ValueError(f"第{index}题超出指定修改范围，请保留未涉及题目的完整内容")
