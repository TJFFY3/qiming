"""FastGPT dataset search API. Recall is evidence, never automatic verification."""
import hashlib
import httpx


class FastGPTRetriever:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    def search(self, query: str) -> list[dict]:
        s = self.settings
        if not s.fastgpt_url or not s.fastgpt_key or not s.datasets:
            raise ValueError('FastGPT 未配置，请编辑 backend/app/config.py 中的地址、密钥和知识库')
        base = s.fastgpt_url.rstrip('/')
        if not base.endswith('/api'):
            base += '/api'
        result, seen, budget = [], set(), 0
        with httpx.Client(timeout=s.timeout, transport=self.transport) as client:
            for dataset in s.datasets:
                try:
                    response = client.post(base + '/core/dataset/searchTest', headers={'Authorization': 'Bearer ' + s.fastgpt_key}, json={'datasetId':dataset['id'], 'text':query, 'limit':s.search_limit, 'similarity':s.similarity, 'searchMode':s.search_mode, 'usingReRank':s.using_rerank})
                    response.raise_for_status()
                    body = response.json()
                    if not isinstance(body, dict) or body.get('code') not in (200, 0) or not isinstance(body.get('data'), list):
                        raise ValueError('FastGPT 返回业务错误或无法识别的检索结构')
                    for item in body['data']:
                        if not isinstance(item, dict) or not isinstance(item.get('q', ''), str) or not isinstance(item.get('a', ''), str):
                            raise ValueError('FastGPT 切片格式无效')
                        evidence = (item.get('q','') + '\n' + item.get('a','')).strip()
                        if not evidence:
                            raise ValueError('FastGPT 切片内容为空')
                        identity = f"{dataset['id']}:{item.get('id') or hashlib.sha256(evidence.encode()).hexdigest()}"
                        if identity in seen or budget + len(evidence) > 32000:
                            continue
                        seen.add(identity)
                        budget += len(evidence)
                        result.append({'id':hashlib.sha256(identity.encode()).hexdigest()[:24], 'hit_id':item.get('id'), 'dataset_id':dataset['id'], 'collection_id':item.get('collectionId'), 'title':item.get('sourceName') or dataset.get('name','知识库文档'), 'category':dataset.get('category','textbook'), 'locator':f"集合 {item.get('collectionId','未知')} / 切片 {item.get('id','未提供')}（非教材页码）", 'evidence':evidence, 'score':item.get('score'), 'verified':False})
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                    if isinstance(exc, httpx.HTTPStatusError):
                        message = f'FastGPT 检索失败（HTTP {exc.response.status_code}），请检查服务及知识库权限'
                    elif isinstance(exc, httpx.TimeoutException):
                        message = 'FastGPT 检索超时，请重试'
                    elif isinstance(exc, httpx.HTTPError):
                        message = '无法连接 FastGPT，请检查服务地址'
                    else:
                        message = str(exc)
                    raise ValueError(s.redact(message)) from None
        return result
