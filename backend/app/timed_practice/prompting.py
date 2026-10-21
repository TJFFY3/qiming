"""Visible lesson context and editable practice options for history and generation."""

import re
from ..prompting import compose_lesson_context
from .requirements import START, END


def compose_prompt(prompt, settings):
    text = prompt.strip() or "请根据本课内容生成一份限时练习。"
    if not (START in text and END in text):
        options = settings.get("options", {})
        default = "按本课安排（默认）"
        labels = [
            ("用时", "duration"),
            ("满分", "score"),
            ("题型和数量", "questions"),
            ("题目难度", "difficulty"),
            ("出题方式", "origin"),
        ]
        lines = [f"{label}：{options.get(key, default)}" for label, key in labels]
        lines += [
            f"重点练什么：{'、'.join(options.get('focus', [])) or default}",
            f"补充要求：{options.get('extra', '') or '无'}",
        ]
        text += "\n\n" + START + "\n" + "\n".join(lines) + "\n" + END
    return compose_lesson_context(
        text, settings, re.escape(START) + r"[\s\S]*?" + re.escape(END)
    )
