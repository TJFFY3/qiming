"""【流程适配】将任务上下文绑定到单次工作流请求，并合并可信引用。"""

from .client import WorkflowClient, WorkflowOutputError, WorkflowServiceError


def missing_workflow_settings(settings):
    return [name for name in ('fastgpt_url', 'fastgpt_key') if not getattr(settings, name, '')]


def generate(model, messages, *, agent_category, teacher_settings, prompt, operation,
             sources, requirements=None, on_progress=None):
    # 仅为显式注入的测试替身保留通用模型接口；应用默认只装配 WorkflowClient。
    if not isinstance(model, WorkflowClient):
        streaming = getattr(model, 'generate_json_with_progress', None)
        return streaming(messages, on_progress) if streaming and on_progress else model.generate_json(messages)

    def merge(received):
        combined = {source['id']: source for source in sources}
        for source in received:
            old = combined.get(source['id'], {})
            if old.get('evidence') == source.get('evidence'):
                source = {**source, 'verified': bool(old.get('verified')),
                          'review_note': old.get('review_note', '')}
            combined[source['id']] = source
        if sum(len(item.get('evidence', '')) for item in combined.values()) > 120000:
            raise WorkflowServiceError('工作流引用资料超过120000字符，请缩小检索范围')
        sources[:] = combined.values()

    try:
        result = model.generate_task(messages, agent_category=agent_category,
                                     teacher_settings=teacher_settings, prompt=prompt,
                                     operation=operation, sources=sources,
                                     requirements=requirements, on_progress=on_progress)
        merge(result.sources)
        # 工作流只能返回可信切片范围内的图别名；导出仍使用原有哈希ID校验。
        from backend.app.shared.tools.images import image_catalog
        aliases = {}
        for source in sources:
            for index, image in enumerate(image_catalog([source]), 1):
                aliases[f"{source['id']}:image:{index}"] = image['image_id']

        def normalize_images(value):
            if isinstance(value, dict):
                image_id = value.get('image_id')
                if isinstance(image_id, str) and image_id in aliases:
                    value['image_id'] = aliases[image_id]
                for item in value.values():
                    normalize_images(item)
            elif isinstance(value, list):
                for item in value:
                    normalize_images(item)

        normalize_images(result.content)
        return result.content
    except WorkflowOutputError as exc:
        merge(exc.sources)
        # 原有三条流程保留各自的内容修复异常与诊断记录格式。
        if agent_category == '导学案':
            from backend.app.study_guide.llm.client import ModelOutputError
        elif agent_category == '互动课件':
            from backend.app.courseware.llm.client import CoursewareModelOutputError as ModelOutputError
        else:
            from backend.app.timed_practice.llm.client import ModelOutputError
        raise ModelOutputError(str(exc), exc.response_text) from None
    except WorkflowServiceError as exc:
        if agent_category == '导学案':
            from backend.app.study_guide.llm.client import ModelServiceError
            raise ModelServiceError(str(exc)) from None
        raise
