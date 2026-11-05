"""【工作流调用】传递全局变量，读取成品 JSON 与独立的检索引用元数据。"""

import hashlib
import json
import socket
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass

from .retrieval_query import build_retrieval_query
from .subject_prompts import subject_dynamic_prompt

import httpx

WORKFLOW_APP_ID = '6ae34b10b1b18f9bb876d8ac'


class WorkflowServiceError(ValueError):
    """连接、权限或执行故障，不能靠模型改写内容修复。"""


def _check_search_error(value):
    """知识库的业务拒绝直接作为失败原因，不能当成成品 JSON 进入自动修复。"""
    if isinstance(value, dict):
        reason = value.get('errorInfo')
        if isinstance(reason, str) and reason.strip():
            raise WorkflowServiceError(reason.strip())


class WorkflowOutputError(ValueError):
    def __init__(self, message, response_text='', sources=None):
        super().__init__(message)
        self.response_text = response_text
        self.sources = sources or []


@dataclass
class WorkflowResult:
    content: dict
    sources: list[dict]


@contextmanager
def response_deadline(response, started, seconds):
    """心跳不能无限延长任务；到总时限时唤醒被阻塞的网络读取。"""
    expired = threading.Event()

    def interrupt():
        expired.set()
        stream = response.extensions.get('network_stream')
        try:
            connection = stream.get_extra_info('socket') if stream else None
            if connection:
                connection.shutdown(socket.SHUT_RDWR)
        except (OSError, AttributeError):
            pass
        try:
            response.close()
        except (OSError, RuntimeError, httpx.HTTPError):
            pass

    timer = threading.Timer(max(0, seconds - (time.monotonic() - started)), interrupt)
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()
        if expired.is_set():
            raise WorkflowServiceError(f'工作流调用超过{seconds:g}秒，已停止，请稍后重试') from None


class WorkflowClient:
    """无会话可变状态：每次调用独立传递 Agent、操作和上下文，防止并发串用。"""

    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    def generate_task(self, messages, *, agent_category, teacher_settings, prompt,
                      operation, sources, requirements=None, on_progress=None):
        s = self.settings
        if not s.fastgpt_url or not s.fastgpt_key:
            raise WorkflowServiceError('请配置新 FastGPT 工作流的地址和 API 密钥')
        if agent_category not in ('导学案', '互动课件', '限时练习'):
            raise WorkflowServiceError('未知智能体分类')
        if operation not in ('初始化', '微调'):
            raise WorkflowServiceError('未知工作流操作')
        base = s.fastgpt_url.rstrip('/')
        if not base.endswith('/api'):
            base += '/api'
        from backend.app.shared.knowledge.subjects import SUBJECTS, select_subject_datasets
        subject = teacher_settings.get('subject', '化学')
        if subject not in SUBJECTS:
            raise WorkflowServiceError('不支持的学科')
        datasets = getattr(s, 'datasets', [])
        chapter = teacher_settings.get('chapter', '')
        chapters = chapter if isinstance(chapter, list) else [chapter] if chapter else []
        filters = getattr(s, 'repo_label_config', {})
        if not isinstance(filters, dict):
            raise WorkflowServiceError('repo_label_config 必须是 JSON 对象')
        system = '\n\n'.join(m['content'] for m in messages if m['role'] == 'system')
        if subject != '化学':
            system = system.replace('高中化学', '高中' + subject).replace('化学问题', subject + '问题')
            system += f'\n本次教学学科为{subject}，仅设计该学科内容；化学式规则仅在实际涉及化学符号时适用。'
        system += (
            "\n工作流原图标识协议：本次检索新增原图若尚无本地image_catalog ID，"
            "请用‘切片ID:image:序号’作为image_id，例如hit123:image:1；"
            "序号按该切片Markdown原图按URL去重后的首次出现顺序从1起计。"
            "切片ID必须来自工作流实际检索记录；已有image_catalog中的ID继续有效。"
            "应用仅根据响应quoteList中的真实原图证据转换标识，未知标识会被拒绝。"
            "不得输出或虚构图片URL，不得将描述当作图片。"
        )
        # repoSearchInfo 仅供检索；dynamicPromot 按学科提供生成要求，不参与检索词提炼。
        context = {
            'teacher_request': prompt,
            'output_contract': system,
            'teacher_settings': teacher_settings,
            'effective_requirements': requirements,
            'provided_sources': sources,
            'messages': [m for m in messages if m['role'] != 'system'],
        }
        variables = dict(
            datasetIds=[],
            chapters=json.dumps(chapters, ensure_ascii=False),
            repoLabelConfig=json.dumps(filters, ensure_ascii=False),
            subject=subject,
            repoSearchInfo=build_retrieval_query(teacher_settings, prompt),
            dynamicPromot=subject_dynamic_prompt(subject),
            agentCategory=agent_category,
            basePromot=system,
            operation=operation,
        )
        payload = dict(appId=getattr(s, 'workflow_app_id', WORKFLOW_APP_ID),
                       variables=variables, stream=True, detail=True,
                       messages=[dict(role='user', content=(
                           prompt + '\n\n本次任务上下文与输出协议（必须遵守，修复时执行最新反馈）：\n'
                           + json.dumps(context, ensure_ascii=False)))])
        read_timeout = float(getattr(s, 'model_read_timeout', 300))
        total_timeout = float(getattr(s, 'model_total_timeout', 600))
        if read_timeout <= 0 or total_timeout <= 0:
            raise WorkflowServiceError('工作流等待时间和总时限必须大于0')
        timeout = httpx.Timeout(connect=min(15, total_timeout),
                               read=min(read_timeout, total_timeout),
                               write=min(30, total_timeout), pool=min(15, total_timeout))
        collected = {}
        parts = []
        received = 0
        started = time.monotonic()
        last_progress = -1.0

        def remaining_timeout():
            remaining = total_timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise WorkflowServiceError(f'工作流调用超过{total_timeout:g}秒总时限，已停止')
            return httpx.Timeout(connect=min(15, remaining), read=min(read_timeout, remaining),
                                 write=min(30, remaining), pool=min(15, remaining))

        def progress(force=False):
            nonlocal last_progress
            elapsed = time.monotonic() - started
            if on_progress and (force or elapsed - last_progress >= 1):
                on_progress(dict(received_chars=received, elapsed_seconds=int(elapsed)))
                last_progress = elapsed

        def collect(nodes):
            # 只接受响应元数据的 quoteList，不读取模型正文的 sources/verified 声明。
            if isinstance(nodes, list):
                for node in nodes:
                    collect(node)
            elif isinstance(nodes, dict):
                _check_search_error(nodes)
                error = nodes.get('errorText') or nodes.get('errorMessage') or nodes.get('error')
                if error:
                    if 'unExistDataset' in str(error):
                        raise WorkflowServiceError('工作流知识库节点执行失败：知识库不存在或当前应用无权访问（unExistDataset）')
                    raise WorkflowServiceError('FastGPT 工作流节点执行失败，请检查已发布流程的运行记录')
                quotes = nodes.get('quoteList', [])
                if isinstance(quotes, list):
                    for quote in quotes:
                        if not isinstance(quote, dict):
                            continue
                        q, a = quote.get('q', ''), quote.get('a', '')
                        if not isinstance(q, str) or not isinstance(a, str):
                            continue
                        evidence = (q + '\n' + a).strip()
                        if not evidence:
                            continue
                        dataset = quote.get('datasetId') or quote.get('dataset_id') or ''
                        identity = quote.get('id') or hashlib.sha256((str(dataset) + evidence).encode()).hexdigest()[:24]
                        if not isinstance(identity, str):
                            continue
                        spec = next((d for d in datasets if d.get('id') == dataset), {})
                        collected[identity] = dict(
                            id=identity, hit_id=quote.get('id'), dataset_id=dataset,
                            dataset_name=spec.get('name', '知识库'),
                            collection_id=quote.get('collectionId'),
                            title=quote.get('sourceName') or spec.get('name', '知识库文档'),
                            category=spec.get('category', 'textbook'),
                            locator=f"集合 {quote.get('collectionId', '未知')} / 切片 {identity}（非教材页码）",
                            evidence=evidence, score=quote.get('score'), verified=False,
                        )
                for key in ('responseData', 'flowResponses', 'toolResponses'):
                    if key in nodes:
                        collect(nodes[key])

        def output_error(message, text):
            return WorkflowOutputError(message, text, list(collected.values()))

        try:
            progress(True)
            with httpx.Client(timeout=timeout, transport=self.transport) as client:
                # 只解析目录，不再调用 searchTest；内容召回由工作流负责。
                from .datasets import expand_datasets
                datasets = expand_datasets(client, base, s.fastgpt_key, datasets, remaining_timeout, started, total_timeout, max_datasets=1000)
                datasets = select_subject_datasets(datasets, subject)
                if len(datasets) > 30:
                    raise WorkflowServiceError('所选学科知识库数量超过30个，请缩小配置范围')
                variables['datasetIds'] = [{'datasetId': d['id']} for d in datasets]
                request_timeout = remaining_timeout()
                with client.stream('POST', base + '/v1/chat/completions',
                                   timeout=request_timeout,
                                   headers={'Authorization': 'Bearer ' + s.fastgpt_key,
                                            'Accept': 'text/event-stream'},
                                   json=payload) as response, response_deadline(response, started, total_timeout):
                    response.raise_for_status()
                    if 'text/event-stream' not in response.headers.get('content-type', '').lower():
                        try:
                            body = json.loads(response.read())
                        except (ValueError, UnicodeDecodeError):
                            raise WorkflowServiceError('工作流服务返回非 JSON 响应') from None
                        _check_search_error(body)
                        if not isinstance(body, dict) or body.get('error') or body.get('code') not in (None, 0, 200):
                            raise WorkflowServiceError('FastGPT 工作流执行失败，请检查应用配置和权限')
                        collect(body.get('responseData', []))
                        try:
                            choice = body['choices'][0]
                            text = choice['message']['content']
                        except (KeyError, TypeError, IndexError):
                            raise WorkflowServiceError('工作流响应缺少 choices[0].message.content') from None
                        if choice.get('finish_reason') == 'length':
                            raise output_error('工作流输出被截断，请提高工作流输出上限或减少内容', text)
                    else:
                        completed = False
                        name, data = '', []

                        def consume():
                            nonlocal completed, received
                            if not data:
                                return
                            raw = '\n'.join(data)
                            if raw.strip() == '[DONE]':
                                completed = True
                                return
                            if name == 'error':
                                try:
                                    error_body = json.loads(raw)
                                except ValueError:
                                    pass
                                else:
                                    _check_search_error(error_body)
                                raise WorkflowServiceError('FastGPT 工作流执行失败，请检查应用配置和权限')
                            if name not in ('', 'answer', 'fastAnswer', 'flowResponses'):
                                return
                            try:
                                item = json.loads(raw)
                            except ValueError:
                                raise WorkflowServiceError('工作流流式响应包含无效事件') from None
                            _check_search_error(item)
                            if name == 'flowResponses':
                                collect(item)
                                return
                            if not isinstance(item, dict) or item.get('error') or item.get('code') not in (None, 0, 200):
                                raise WorkflowServiceError('工作流返回执行错误')
                            for choice in item.get('choices', []):
                                piece = (choice.get('delta') or {}).get('content', '')
                                if piece is None:
                                    piece = ''
                                if not isinstance(piece, str):
                                    raise WorkflowServiceError('工作流正文必须是文本')
                                parts.append(piece)
                                received += len(piece)
                                if received > 512000:
                                    raise WorkflowServiceError('工作流输出过长，请缩小内容范围')
                                if choice.get('finish_reason') == 'length':
                                    raise output_error('工作流输出被截断，请提高工作流输出上限或减少内容', ''.join(parts))
                                if choice.get('finish_reason') == 'stop':
                                    completed = True

                        for line in response.iter_lines():
                            progress()
                            if not line:
                                consume()
                                name, data = '', []
                            elif line.startswith('event:'):
                                name = line[6:].strip()
                            elif line.startswith('data:'):
                                data.append(line[5:].lstrip())
                        # 不在 DONE/stop 处提前退出：引用元数据可能晚于正文结束事件。
                        consume()
                        if not completed:
                            raise WorkflowServiceError('工作流连接中断，未收到完整结束标记，请重试')
                        text = ''.join(parts)
        except httpx.TimeoutException:
            raise WorkflowServiceError(f'工作流连续{min(read_timeout, total_timeout):g}秒未返回数据，请重试') from None
        except httpx.HTTPStatusError as exc:
            raise WorkflowServiceError(f'工作流调用失败（HTTP {exc.response.status_code}），请检查 API 密钥与应用权限') from None
        except httpx.HTTPError:
            raise WorkflowServiceError('工作流网络连接中断，请重试') from None
        if not isinstance(text, str):
            raise output_error('工作流正文必须为 JSON 文本', '')
        if not text.strip():
            raise WorkflowServiceError('工作流未返回正文，请检查已发布流程的分支与最终输出节点')
        received = len(text)
        progress(True)
        original = text
        text = text.strip()
        if text.startswith('```') and text.endswith('```') and '\n' in text:
            text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        try:
            result = json.loads(text, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('非有限数字')))
            if not isinstance(result, dict):
                raise ValueError('必须为对象')
        except (ValueError, TypeError):
            raise output_error('工作流正文不是完整有效的 JSON 对象', original) from None
        # 放在 JSON 解析异常捕获之外，避免将业务拒绝误包装为可重试的格式错误。
        _check_search_error(result)
        return WorkflowResult(result, list(collected.values()))
