"""【知识库调用·共享】同步完整资料目录、读取文档片段及原文地址，供资料浏览使用。"""

import hashlib
from urllib.parse import urlsplit
import httpx


class KnowledgeLibrary:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport
        self.base = settings.fastgpt_url.rstrip("/")
        if not self.base.endswith("/api"):
            self.base += "/api"

    def _post(self, client, path, payload):
        if not self.settings.fastgpt_key or not self.settings.fastgpt_url:
            raise ValueError("请先在服务端配置 FastGPT 地址和密钥")
        try:
            response = client.post(
                self.base + "/core/dataset/" + path,
                headers={"Authorization": "Bearer " + self.settings.fastgpt_key},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            if body.get("code") not in (0, 200):
                raise ValueError("知识库同步接口返回错误，请检查访问权限")
            return body["data"]
        except (httpx.HTTPError, KeyError, TypeError):
            raise ValueError("无法读取知识库资料，请检查服务和访问权限") from None

    def _pages(self, client, path, payload):
        offset = 0
        while True:
            data = self._post(
                client, path, {**payload, "offset": offset, "pageSize": 30}
            )
            if not isinstance(data, dict) or not isinstance(data.get("list"), list):
                raise ValueError("知识库目录或片段结构无效")
            items = data["list"]
            yield from items
            offset += len(items)
            if offset >= data["total"]:
                break
            if not items:
                raise ValueError("知识库分页未完整返回，请重新同步")

    # 【知识库入口】全量目录同步用于浏览，独立于本次任务的语义召回。
    def synchronize(self):
        if not self.settings.datasets:
            raise ValueError("请先配置需要同步的知识库")
        documents, visited_datasets, visited_folders = [], set(), set()
        with httpx.Client(
            timeout=self.settings.timeout, transport=self.transport
        ) as client:

            def collections(dataset, parent=None):
                identity = (dataset["id"], parent)
                if identity in visited_folders:
                    return
                visited_folders.add(identity)
                for item in self._pages(
                    client,
                    "collection/listV2",
                    {"datasetId": dataset["id"], "parentId": parent, "searchText": ""},
                ):
                    if item.get("type") == "folder":
                        collections(dataset, item["_id"])
                        continue
                    title = item.get("name", "知识库资料")
                    cid = item["_id"]
                    chunks = list(
                        self._pages(client, "data/list", {"collectionId": cid})
                    )
                    chunks.sort(key=lambda x: x.get("chunkIndex", 0))
                    sources = []
                    for chunk in chunks:
                        hid = chunk["_id"]
                        sources.append(
                            {
                                "id": hashlib.sha256(
                                    f"{dataset['id']}:{hid}".encode()
                                ).hexdigest()[:24],
                                "dataset_name": dataset.get("name", "知识库"),
                                "hit_id": hid,
                                "collection_id": cid,
                                "dataset_id": dataset["id"],
                                "title": title,
                                "category": dataset.get("category", "reference"),
                                "locator": f"片段 {chunk.get('chunkIndex', 0) + 1}（非教材页码）",
                                "evidence": (
                                    chunk.get("q", "") + "\n" + chunk.get("a", "")
                                ).strip(),
                                "verified": False,
                            }
                        )
                    documents.append(
                        {
                            "id": cid,
                            "title": title,
                            "dataset_id": dataset["id"],
                            "dataset_name": dataset.get("name", "知识库"),
                            "kind": "presentation"
                            if title.lower().endswith((".ppt", ".pptx"))
                            else "document",
                            "chunks": sources,
                        }
                    )

            def expand(dataset):
                if dataset["id"] in visited_datasets:
                    return
                visited_datasets.add(dataset["id"])
                if dataset.get("type") == "folder":
                    data = self._post(client, "list", {"parentId": dataset["id"]})
                    children = data if isinstance(data, list) else data["list"]
                    for child in children:
                        expand(
                            {
                                **dataset,
                                "id": child["_id"],
                                "name": child.get("name", "知识库"),
                                "type": child.get("type", "dataset"),
                            }
                        )
                else:
                    collections(dataset)

            for dataset in self.settings.datasets:
                expand(dataset)
        return documents

    def original_url(self, collection_id):
        with httpx.Client(
            timeout=self.settings.timeout, transport=self.transport
        ) as client:
            data = self._post(
                client, "collection/read", {"collectionId": collection_id}
            )
        url = data.get("value", "")
        parts = urlsplit(url)
        if (
            data.get("type") != "url"
            or parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.username
            or parts.password
        ):
            raise ValueError("知识库未提供有效原文件地址")
        return url
