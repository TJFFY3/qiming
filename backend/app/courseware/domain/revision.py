"""【规则处理·互动课件】解析教师指定页码并合并补丁，保护未涉及页面及历史来源说明。"""

import copy
import re

from backend.app.courseware.domain.models import RevisionResult


def revision_page_scope(prompt):
    number = r"(?:\d+|[一二三四五六七八九十两]+)"
    references = re.finditer(
        rf"第\s*({number}(?:\s*页?\s*[、,，和及到至—-]\s*(?:第\s*)?{number})*)\s*页",
        prompt,
    )
    digits = {char: i for i, char in enumerate("零一二三四五六七八九")}
    digits["两"] = 2

    def parse(value):
        if value.isdecimal():
            result = int(value)
        elif "十" in value:
            tens, units = value.split("十", 1)
            result = digits.get(tens, 1) * 10 + digits.get(units, 0)
        else:
            result = digits.get(value, 0)
        if not 1 <= result <= 60:
            raise ValueError("指定页号必须在1至60页之间")
        return result

    def preserved(match):
        before = re.split(r"[，,。；;\n]", prompt[:match.start()])[-1]
        after = prompt[match.end():]
        return bool(
            re.search(r"保留|保持|不(?:要|必|需)?(?:修改|改动|调整|更新|改写|改)|无需修改", before)
            or re.match(r"\s*(?:的)?(?:标题|内容|文字)?\s*(?:保持不变|保持原样|不变|不动|不改|无需修改|不要修改)", after)
        )

    targets, protected = set(), set()
    for reference in references:
        selected = protected if preserved(reference) else targets
        for group in re.split(r"[、,，和及]", reference[1]):
            values = [parse(n) for n in re.findall(number, group)]
            if len(values) == 2:
                selected.update(range(min(values), max(values) + 1))
            else:
                selected.update(values)
    for cover in re.finditer("封面", prompt):
        (protected if preserved(cover) else targets).add(1)
    return targets, protected


def merge_revision(raw, previous, prompt, allow_full_revision=False):
    result = RevisionResult.model_validate(raw)
    if result.mode == "full":
        if not allow_full_revision or result.deck is None or result.changes:
            raise ValueError(
                "请先选择“调整页数与结构”进行整体修改；当前只允许替换指定页。"
            )
        content = result.deck.model_dump(exclude_defaults=True, exclude_none=True)
    else:
        if result.deck is not None or not (
            result.changes or result.title is not None or result.source_gaps or result.conflicts
        ):
            raise ValueError("patch 需要 changes、课件 title 或资料缺口/冲突，不可附带完整 deck")
        content = copy.deepcopy(previous)
        changed = set()
        targets, protected = revision_page_scope(prompt)
        for change in result.changes:
            if change.page > len(content["slides"]) or change.page in changed:
                raise ValueError("修改页号越界或重复，请按现有逻辑页序返回补丁")
            if change.page in protected or (targets and change.page not in targets):
                raise ValueError("补丁修改了指定页面之外的内容，请只返回教师指定的页面")
            changed.add(change.page)
            content["slides"][change.page - 1] = change.slide.model_dump(
                exclude_defaults=True, exclude_none=True
            )
        if result.title is not None and result.title != previous["title"]:
            if 1 in protected or (targets and 1 not in targets):
                raise ValueError("总标题修改会影响封面，超出指定页面之外的范围")
            content["title"] = result.title
    if content["title"] != previous["title"]:
        # A renamed total title must be visible in the downloaded deck, for
        # both page patches and explicitly authorized full revisions.
        content["slides"][0]["title"] = content["title"]
    for field in ("source_gaps", "conflicts"):
        values = list(dict.fromkeys(
            previous.get(field, []) + content.get(field, []) + getattr(result, field)
        ))
        if values:
            content[field] = values
    return content
