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
