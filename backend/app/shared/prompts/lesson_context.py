"""【提示词工具·共享】统一课时上下文的识别与拼接，不包含 Agent 专属生成协议。"""

import re


LESSON_CONTEXT = r"^学科：化学\n教材版本：[^\n]*\n年级：[^\n]*\n章节 / 知识点：[^\n]*\n课时：[^\n]*(?:\n|$)"



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

