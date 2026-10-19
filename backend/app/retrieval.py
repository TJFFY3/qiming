"""FastGPT dataset search API. Recall is evidence, never automatic verification."""

import hashlib
import httpx


class FastGPTRetriever:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    def search(self, query: str) -> list[dict]:
        s = self.settings
        if not s.fastgpt_url or not s.fastgpt_key or not s.datasets:
            raise ValueError(
                "FastGPT 未配置，请编辑 backend/app/config.py 中的地址、密钥和知识库"
            )
        base = s.fastgpt_url.rstrip("/")
        if not base.endswith("/api"):
            base += "/api"
        result, seen, budget = [], set(), 0
        with httpx.Client(timeout=s.timeout, transport=self.transport) as client:
            datasets = []

            def expand(dataset, depth=0):
                if depth > 8 or len(datasets) > 30:
                    raise ValueError("知识库文件夹层级或数量过多，请缩小范围")
                if dataset.get("type") != "folder":
                    datasets.append(dataset)
                    return
                response = client.post(
                    base + "/core/dataset/list",
                    headers={"Authorization": "Bearer " + s.fastgpt_key},
                    json={"parentId": dataset["id"]},
                )
                response.raise_for_status()
                body = response.json()
                if (
                    isinstance(body, dict)
                    and isinstance(body.get("data"), dict)
                    and isinstance(body["data"].get("list"), list)
                ):
                    body = {**body, "data": body["data"]["list"]}
                if (
                    not isinstance(body, dict)
                    or body.get("code") not in (0, 200)
                    or not isinstance(body.get("data"), list)
                ):
                    raise ValueError("无法读取知识库文件夹，请检查访问权限")
                for child in body["data"]:
                    if not isinstance(child, dict) or not isinstance(
                        child.get("_id"), str
                    ):
                        raise ValueError("知识库文件夹返回结构无效")
                    expand(
                        {
                            **dataset,
                            "id": child["_id"],
                            "name": child.get("name", "知识库"),
                            "type": child.get("type", "dataset"),
                        },
                        depth + 1,
                    )

            try:
                for dataset in s.datasets:
                    expand(dataset)
            except httpx.HTTPError:
                raise ValueError(
                    "无法读取 FastGPT 知识库目录，请检查地址及权限"
                ) from None
            for dataset in datasets:
                try:
                    response = client.post(
                        base + "/core/dataset/searchTest",
                        headers={"Authorization": "Bearer " + s.fastgpt_key},
                        json={
                            "datasetId": dataset["id"],
                            "text": query,
                            "limit": s.search_limit,
                            "similarity": s.similarity,
                            "searchMode": s.search_mode,
                            "usingReRank": s.using_rerank,
                        },
                    )
                    try:
                        body = response.json()
                    except ValueError:
                        response.raise_for_status()
                        raise ValueError("FastGPT 返回非 JSON 响应")
                    if isinstance(body, dict) and (
                        body.get("code") == 513001
                        or body.get("statusText") == "modelUnConfigured"
                    ):
                        raise ValueError(
                            "FastGPT 未完成模型配置（513001 / modelUnConfigured），请检查知识库关联的模型"
                        )
                    response.raise_for_status()
                    if (
                        isinstance(body, dict)
                        and isinstance(body.get("data"), dict)
                        and isinstance(body["data"].get("list"), list)
                    ):
                        body = {**body, "data": body["data"]["list"]}
                    if (
                        not isinstance(body, dict)
                        or body.get("code") not in (200, 0)
                        or not isinstance(body.get("data"), list)
                    ):
                        raise ValueError("FastGPT 返回业务错误或无法识别的检索结构")
                    for item in body["data"]:
                        if (
                            not isinstance(item, dict)
                            or not isinstance(item.get("q", ""), str)
                            or not isinstance(item.get("a", ""), str)
                        ):
                            raise ValueError("FastGPT 切片格式无效")
                        if any(
                            item.get(k) is not None and not isinstance(item[k], str)
                            for k in ("sourceName", "collectionId", "id")
                        ):
                            raise ValueError("FastGPT 切片来源字段无效")
                        evidence = (
                            item.get("q", "") + "\n" + item.get("a", "")
                        ).strip()
                        if not evidence:
                            raise ValueError("FastGPT 切片内容为空")
                        identity = f"{dataset['id']}:{item.get('id') or hashlib.sha256(evidence.encode()).hexdigest()}"
                        if identity in seen or budget + len(evidence) > 32000:
                            continue
                        seen.add(identity)
                        budget += len(evidence)
                        result.append(
                            {
                                "id": hashlib.sha256(identity.encode()).hexdigest()[
                                    :24
                                ],
                                "hit_id": item.get("id"),
                                "dataset_id": dataset["id"],
                                "dataset_name": dataset.get("name", "知识库"),
                                "collection_id": item.get("collectionId"),
                                "title": item.get("sourceName")
                                or dataset.get("name", "知识库文档"),
                                "category": dataset.get("category", "textbook"),
                                "locator": f"集合 {item.get('collectionId', '未知')} / 切片 {item.get('id', '未提供')}（非教材页码）",
                                "evidence": evidence,
                                "score": item.get("score"),
                                "verified": False,
                            }
                        )
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                    if isinstance(exc, httpx.HTTPStatusError):
                        message = f"FastGPT 检索失败（HTTP {exc.response.status_code}），请检查服务及知识库权限"
                    elif isinstance(exc, httpx.TimeoutException):
                        message = "FastGPT 检索超时，请重试"
                    elif isinstance(exc, httpx.HTTPError):
                        message = "无法连接 FastGPT，请检查服务地址"
                    else:
                        message = str(exc)
                    raise ValueError(s.redact(message)) from None
        return result
