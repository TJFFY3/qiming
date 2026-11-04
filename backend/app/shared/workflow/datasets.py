"""【知识库目录】将已有文件夹配置展开为工作流可用的知识库 ID，不检索文档内容。"""


def expand_datasets(client, base, key, configured, remaining_timeout=None, started=None, total_timeout=None, max_datasets=30):
    from backend.app.shared.knowledge.subjects import dataset_subject
    import time
    from .client import WorkflowServiceError, response_deadline

    result, seen, folders = [], set(), set()

    def expand(dataset, depth=0):
        if depth > 8 or len(result) > max_datasets or len(folders) > 100:
            raise WorkflowServiceError('知识库目录层级或数量过多，请缩小配置范围')
        identity = dataset.get('id')
        if not isinstance(identity, str) or not identity:
            raise WorkflowServiceError('知识库配置缺少有效 ID')
        if dataset.get('type') != 'folder':
            if identity not in seen:
                result.append(dataset)
                seen.add(identity)
            return
        if identity in folders:
            return
        folders.add(identity)
        timeout = {'timeout': remaining_timeout()} if remaining_timeout else {}
        # 目录同样流式读取并执行墙钟截止，不能靠持续小块响应绕过总时限。
        import json
        with client.stream('POST', base + '/core/dataset/list',
                           headers={'Authorization': 'Bearer ' + key},
                           json={'parentId': identity}, **timeout) as response:
            anchor = started if started is not None else time.monotonic()
            budget = total_timeout if total_timeout is not None else 120
            with response_deadline(response, anchor, budget):
                response.raise_for_status()
                chunks = []
                for chunk in response.iter_bytes():
                    if time.monotonic() - anchor >= budget:
                        raise WorkflowServiceError(f'知识库目录读取超过{budget:g}秒总时限')
                    chunks.append(chunk)
                try:
                    body = json.loads(b''.join(chunks))
                except ValueError:
                    raise WorkflowServiceError('知识库目录返回非 JSON 响应') from None
        if not isinstance(body, dict) or body.get('code') not in (0, 200):
            raise WorkflowServiceError('无法读取知识库目录，请检查权限')
        children = body.get('data')
        if isinstance(children, dict):
            children = children.get('list')
        if not isinstance(children, list):
            raise WorkflowServiceError('知识库目录返回结构无效')
        for child in children:
            if not isinstance(child, dict):
                raise WorkflowServiceError('知识库目录子项格式无效')
            expand({**dataset, 'id': child.get('_id'),
                    'name': child.get('name', dataset.get('name', '知识库')),
                    'type': child.get('type', 'dataset'),
                    'subject': dataset_subject({'name': child.get('name', '')}) or dataset_subject(dataset)}, depth + 1)

    for item in configured:
        expand(item)
    if len(result) > max_datasets:
        raise WorkflowServiceError(f'知识库数量超过{max_datasets}个，请缩小配置范围')
    return result
