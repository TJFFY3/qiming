"""【规则处理·富文本】解码被序列化的 run 内容，供各 Agent 的排版适配层使用。"""

import json
import re

START = re.compile(r'\{\s*(?:"text"|"(?:sub|sup|charge|condition|bold|italic|underline|isotope)"\s*:)')
# Legacy model output opened a second text object inside an unescaped text
# value. Only this exact, unambiguous shape can be flattened without guessing.
NESTED_TEXT = re.compile(r'\{\s*"text"\s*:\s*"([^"\\]*)\{\s*"text"\s*:\s*"([^"\\]*)"\s*\}')
MISSING_SEPARATOR = re.compile(r'\{\s*"text"([^"\\:]+)"((?:\s*,\s*"(?:sub|sup|charge|condition|bold|italic|underline)"\s*:\s*(?:true|false))*)\s*\}')


def decode_rich(value, run_model):
    original = [{"text": value}] if isinstance(value, str) else value
    text = "".join(r["text"] for r in original)
    if not START.search(text):
        return value
    result = []

    def prose(start, end):
        offset = 0
        for run in original:
            lo, hi = max(start, offset), min(end, offset + len(run["text"]))
            if lo < hi:
                result.append({**run, "text": text[lo:hi]})
            offset += len(run["text"])

    cursor = 0
    decoder = json.JSONDecoder()
    while match := START.search(text, cursor):
        start = match.start()
        prefix = text[cursor:start]
        array = bool(re.search(r"\[\s*$", prefix))
        prose(cursor, cursor + prefix.rfind("[") if array else start)
        while True:
            try:
                try:
                    raw, end = decoder.raw_decode(text, start)
                except json.JSONDecodeError:
                    nested = NESTED_TEXT.match(text, start)
                    missing = MISSING_SEPARATOR.match(text, start)
                    if nested:
                        raw, end = {"text": nested[1] + nested[2]}, nested.end()
                    elif missing:
                        raw = json.loads('{"text":' + json.dumps(missing[1]) + missing[2] + '}')
                        end = missing.end()
                    else:
                        raise
                run = run_model.model_validate(raw).model_dump(exclude_defaults=True, exclude_none=True)
                if START.search(run["text"]):
                    raise ValueError("嵌套的结构化文本")
            except (ValueError, TypeError) as exc:
                raise ValueError("方程式混入无法解析的结构化数据，请改用扁平 run 数组返回完整内容") from exc
            result.append(run)
            # Consume commas only between decoded run objects, never prose punctuation.
            following = re.match(r"\s*,?\s*(?=" + START.pattern + r")", text[end:])
            if following:
                start = end + following.end()
                continue
            cursor = end
            if array:
                closing = re.match(r"\s*\]", text[cursor:])
                if not closing:
                    raise ValueError("方程式结构化数组不完整，请返回完整扁平 run 数组")
                cursor += closing.end()
            break
    prose(cursor, len(text))
    return result
