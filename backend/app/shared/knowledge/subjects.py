"""【学科规则】以目录中的学科标签标记知识库，供浏览和工作流路由共用。"""
SUBJECTS = ('语文', '数学', '英语', '物理', '化学', '生物', '政治', '历史', '地理')


def dataset_subject(dataset):
    explicit = dataset.get('subject')
    if explicit in SUBJECTS:
        return explicit
    name = dataset.get('name', '').strip()
    return next((subject for subject in SUBJECTS if name.startswith(subject)), '')


def select_subject_datasets(datasets, subject):
    annotated = [d for d in datasets if dataset_subject(d)]
    if not annotated:
        # 兼容旧版直接配置的无学科标签知识库；多学科目录绝不回退到全部库。
        if subject == '化学':
            return datasets
        raise ValueError(f'未配置{subject}学科知识库标签，请检查知识库目录')
    selected = [d for d in datasets if dataset_subject(d) == subject]
    if not selected:
        raise ValueError(f'未配置{subject}学科知识库，请检查知识库目录')
    return selected
