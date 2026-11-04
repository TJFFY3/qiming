"""【检索规则】从本课信息和教师要求中提炼检索词，不混入生成协议或来源全文。"""

import re

# 优化设置里只有这些字段描述需要检索的教学内容；时长、页数、分值等仍由生成节点处理。
CONTENT_FIELDS = {'教学内容', '学习范围', '重点练什么', '本课重点', '重点', '知识点', '补充要求', '检索内容'}
CONTROL_FIELDS = {'题型和数量', '题目难度', '自学用时', '任务数量', '内容难度', '提示详略', '课堂时长', '限时练习时长', '时长', '用时', '满分', '分数', '题量', '课件页数', '课堂练习', '上课方式', '难度', '题型数量', '学习任务', '提示程度', '出题方式', '课件格式', '输出格式', '字体', '字号', '版式', '布局'}
CONTEXT_FIELDS = {'学科', '教材版本', '年级', '章节 / 知识点', '课时'}


def _content_terms(text):
    if not isinstance(text, str):
        return []
    text = re.sub(r'```[\s\S]*?```', '', text)
    result = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(('【', '重点仅表示')):
            continue
        match = re.match(r'^([^：:]{1,24})[：:](.*)$', line)
        if match:
            label, line = match.groups()
            if label in CONTEXT_FIELDS:
                continue  # 课时上下文统一取本次实际设置，避免重复或旧章节污染检索。
            if label in CONTROL_FIELDS:
                continue
            if label not in CONTENT_FIELDS:
                line = label + '：' + line
        for part in re.split(r'[。；;，,\n]', line):
            part = re.sub(r'(?:生成|制作|设计|安排|字体|字号)?\s*\d+\s*(?:分钟|页|分|题|pt)', '', part.strip(), flags=re.I)
            # 格式和知识点可能在同一句话里，先移除格式短语，不能整句丢弃。
            part = re.sub(r'(?:用|以|使用|采用)?(?:表格|PPT|JSON|Markdown|幻灯片)(?:格式|形式)?(?:总结|介绍|展示|呈现|输出|返回)?', '', part, flags=re.I)
            part = re.sub(r'(?:只|仅|必须)?(?:输出|返回|生成)(?:完整|一个|对象|内容|格式|字符串)*', '', part)
            if not part or re.search(r'默认|按本课安排|^无$|当前课时|schema|字号|字体|排版|页数|版式|布局|下载|导出|保留其他|第\s*\d+\s*页', part, re.I):
                continue
            part = re.sub(r'^(?:请|仅|只需|需要|帮我|根据本课内容|本课内容|根据教材|重点|围绕|关于|补充|增加|加入|查找|检索|设计|生成|制作|一份|本课|的|：|:|\s)+', '', part)
            part = re.sub(r'导学案|互动课件|课件|PPT|练习卷|限时练习|教学内容|内容$', '', part, flags=re.I).strip()
            if part and part not in ('生成', '修改', '优化', '调整'):
                result.append(part[:200])
    return result


def build_retrieval_query(teacher_settings, prompt):
    """使用正文中的内容要求及本课重点，不读取历史成品、来源证据和修复消息。"""
    terms = [teacher_settings.get('subject', '化学')]
    for key in ('edition', 'grade', 'chapter', 'period'):
        value = teacher_settings.get(key)
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, str) and item.strip():
                terms.append(item.strip())
    terms.extend(_content_terms(prompt))
    options = teacher_settings.get('options') or {}
    # 教师已编辑优化正文时，不再把旧结构化重点补回检索词。
    if not re.search(r'(?:本课重点|重点练什么|重点|知识点)[：:]', prompt):
        focus = options.get('focus') or []
        if isinstance(focus, str):
            focus = [focus]
        for value in focus:
            terms.extend(_content_terms(value))
    if not re.search(r'补充要求[：:]', prompt):
        terms.extend(_content_terms(options.get('extra', '')))
    # 去重并限制检索输入长度，避免生成说明挤占语义召回上下文。
    return ' '.join(dict.fromkeys(terms))[:800] or '化学教材知识点'
