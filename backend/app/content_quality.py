"""Keep generation instructions and compliance reports out of student handouts."""

import re

# Deliberately narrow: normal subject content and teacher-directed learning tasks
# may discuss learning goals, conditions and blank answers without being leakage.
LEAK = re.compile(
    r"【优化提示(?:结束)?】|teacher_settings|outline\.sections|"
    r"(?:本(?:导学案|文档|次生成)|以上(?:内容|导学案)).{0,160}(?:遵循|紧扣|执行|满足).{0,100}(?:优化提示|提示词|生成要求)|"
    r"(?:condition\s*对象|(?:使用|采用|指定)\s*condition|(?:留白|空白).{0,12}(?:使用|用|以)\s*null)|"
    r"化学式.{0,30}(?:按规范|已经|已按).{0,15}方括号标记",
    re.I | re.S,
)


def _text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            x.get("text", "")
            for x in value
            if isinstance(x, dict) and isinstance(x.get("text"), str)
        )
    return ""


def check_student_content(raw):
    """Reject rather than silently delete content; the existing model repair loop retries."""

    def check(value, path):
        if LEAK.search(_text(value)):
            raise ValueError(
                f"PROMPT_LEAK {path}：正文混入生成说明或提示词执行汇报。请移除这些说明；thinking 仅填写面向学生的化学思考问题，不得复述优化提示、JSON 协议或格式实现。保留实际教学内容和其他无关字段。"
            )

    def blocks(values, path):
        if not isinstance(values, list):
            return
        for i, block in enumerate(values):
            if not isinstance(block, dict):
                continue
            p = f"{path}[{i}]"
            if block.get("type") == "paragraph":
                check(block.get("content"), p + ".content")
            elif block.get("type") == "table":
                if isinstance(block.get("headers"), list):
                    for j, h in enumerate(block["headers"]):
                        check(h, p + f".headers[{j}]")
                if isinstance(block.get("rows"), list):
                    for j, row in enumerate(block["rows"]):
                        if isinstance(row, list):
                            for k, cell in enumerate(row):
                                check(cell, p + f".rows[{j}][{k}]")

    if not isinstance(raw, dict):
        return
    outline = raw.get("outline", raw)
    if isinstance(outline, dict):
        for key in ("title", "schedule_note"):
            check(outline.get(key), "$.outline." + key)
        for key in ("goals", "thinking"):
            if isinstance(outline.get(key), list):
                for i, value in enumerate(outline[key]):
                    check(value, f"$.outline.{key}[{i}]")
        if isinstance(outline.get("sections"), list):
            for i, section in enumerate(outline["sections"]):
                if isinstance(section, dict):
                    p = f"$.outline.sections[{i}]"
                    check(section.get("title"), p + ".title")
                    check(section.get("group"), p + ".group")
                    blocks(section.get("blocks"), p + ".blocks")
    if isinstance(raw.get("changes"), list):
        for i, change in enumerate(raw["changes"]):
            if isinstance(change, dict):
                blocks(change.get("replacement"), f"$.changes[{i}].replacement")
