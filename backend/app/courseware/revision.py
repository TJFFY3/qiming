"""Merge page patches without asking the model to rewrite unrelated pages."""

import copy
import re

from .models import RevisionResult


def merge_revision(raw, previous, prompt, allow_full_revision=False):
    result = RevisionResult.model_validate(raw)
    if result.mode == "full":
        if not allow_full_revision or result.deck is None or result.changes:
            raise ValueError(
                "请先选择“调整页数与结构”进行整体修改；当前只允许替换指定页。"
            )
        return result.deck.model_dump(exclude_defaults=True, exclude_none=True)
    if result.deck is not None or (not result.changes and result.title is None):
        raise ValueError("patch 需要非空 changes 或课件 title，不可附带完整 deck")
    content = copy.deepcopy(previous)
    changed = set()
    targets = {int(n) for n in re.findall(r"第\s*(\d+)\s*页", prompt)}
    if "封面" in prompt:
        targets.add(1)
    for change in result.changes:
        if change.page > len(content["slides"]) or change.page in changed:
            raise ValueError("修改页号越界或重复，请按现有逻辑页序返回补丁")
        if targets and "保留其他" in prompt and change.page not in targets:
            raise ValueError("补丁修改了指定页面之外的内容，请只返回教师指定的页面")
        changed.add(change.page)
        content["slides"][change.page - 1] = change.slide.model_dump(
            exclude_defaults=True, exclude_none=True
        )
    if result.title is not None:
        content["title"] = result.title
    return content
