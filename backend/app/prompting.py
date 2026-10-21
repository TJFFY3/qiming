"""Visible teacher instructions shared by conversation history and model requests."""

import re


def strip_optimization(prompt):
    return re.sub(r"\n?【优化提示】\n[\s\S]*?【优化提示结束】", "", prompt).strip()


def ensure_optimization(prompt, options):
    if not options or ("【优化提示】" in prompt and "【优化提示结束】" in prompt):
        return prompt
    default = "按本课安排（默认）"
    lines = [
        f"学习范围：{options.get('scope', '当前课时（默认）')}",
        f"自学用时：{options.get('duration', default)}",
        f"任务数量：{options.get('tasks', default)}",
        f"内容难度：{options.get('difficulty', default)}",
        f"提示详略：{options.get('hints', default)}",
        f"本课重点：{'、'.join(options.get('focus', [])) or default}",
        f"补充要求：{options.get('extra', '').strip() or '无额外要求'}",
        "重点仅表示加强，不删除其他必学内容；默认项目按本课内容安排，不预设固定用时和题量。",
    ]
    return (
        prompt.strip() + "\n\n【优化提示】\n" + "\n".join(lines) + "\n【优化提示结束】"
    )


LESSON_CONTEXT = r"^学科：化学\n教材版本：[^\n]*\n年级：[^\n]*\n章节 / 知识点：[^\n]*\n课时：[^\n]*(?:\n|$)"


def instruction_text(prompt):
    return re.sub(LESSON_CONTEXT, "", strip_optimization(prompt), flags=re.M).strip()


def compose_prompt(prompt, settings):
    text = ensure_optimization(prompt, settings.get("options"))
    return compose_lesson_context(
        text, settings, r"【优化提示】\n[\s\S]*?【优化提示结束】"
    )


def compose_lesson_context(prompt, settings, optimization_pattern):
    match = re.search(optimization_pattern, prompt)
    instruction = re.sub(optimization_pattern, "", prompt)
    instruction = re.sub(LESSON_CONTEXT, "", instruction, flags=re.M).strip()
    context = "\n".join(
        [
            "学科：化学",
            f"教材版本：{settings.get('edition', '人教版 必修第一册')}",
            f"年级：{settings.get('grade', '高一')}",
            f"章节 / 知识点：{settings.get('chapter', '')}",
            f"课时：{settings.get('period', '第一课时')}",
        ]
    )
    tail = context + ("\n" + match.group(0) if match else "")
    return "\n\n".join(part for part in [instruction, tail] if part)
