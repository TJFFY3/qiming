import json
import httpx
import pytest
from backend.app.config import Settings
from backend.app.library import KnowledgeLibrary


def settings():
    return Settings(
        fastgpt_url="https://kb.test/api",
        fastgpt_key="PRIVATE",
        datasets=[{"id": "ds", "name": "资料", "category": "reference"}],
    )


def test_sync_includes_every_document_and_paginated_chunk_with_images():
    def handle(request):
        body = json.loads(request.content)
        if request.url.path.endswith("listV2"):
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {
                        "total": 2,
                        "list": [
                            {"_id": "ppt", "name": "课件.pptx", "type": "file"},
                            {"_id": "doc", "name": "教材.docx", "type": "file"},
                        ],
                    },
                },
            )
        assert request.url.path.endswith("/data/list")
        offset = body["offset"]
        chunk = {
            "_id": str(offset),
            "q": f"{body['collectionId']} 第{offset + 1}段 ![图](https://kb.test/image.png)",
            "a": "",
            "chunkIndex": offset,
        }
        return httpx.Response(
            200, json={"code": 200, "data": {"total": 2, "list": [chunk]}}
        )

    documents = KnowledgeLibrary(settings(), httpx.MockTransport(handle)).synchronize()
    assert len(documents) == 2
    assert documents[0]["kind"] == "presentation"
    assert documents[1]["kind"] == "document"
    for doc in documents:
        assert len(doc["chunks"]) == 2
        assert "第2段" in doc["chunks"][1]["evidence"]
        assert "![图]" in doc["chunks"][0]["evidence"]
        assert doc["chunks"][0]["verified"] is False


def test_original_url_comes_from_authenticated_read_endpoint():
    def handle(request):
        assert request.url.path.endswith("/collection/read")
        assert request.headers["authorization"] == "Bearer PRIVATE"
        assert json.loads(request.content) == {"collectionId": "ppt"}
        return httpx.Response(
            200,
            json={
                "code": 200,
                "data": {
                    "type": "url",
                    "value": "https://files.test/original.pptx?signature=temporary",
                },
            },
        )

    assert (
        KnowledgeLibrary(settings(), httpx.MockTransport(handle))
        .original_url("ppt")
        .startswith("https://files.test/")
    )


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "file:///etc/passwd", "https://user:password@files.test/a"],
)
def test_invalid_original_url_rejected(url):
    with pytest.raises(ValueError):
        KnowledgeLibrary(
            settings(),
            httpx.MockTransport(
                lambda _: httpx.Response(
                    200, json={"code": 200, "data": {"type": "url", "value": url}}
                )
            ),
        ).original_url("ppt")


def test_nested_datasets_and_collection_folders_are_walked():
    s = settings()
    s.datasets = [{"id": "root", "type": "folder", "category": "reference"}]

    def handle(request):
        body = json.loads(request.content)
        path = request.url.path
        if path.endswith("/dataset/list"):
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": [{"_id": "ds", "type": "dataset", "name": "子库"}],
                },
            )
        if path.endswith("listV2"):
            if body["parentId"] is None:
                data = (
                    {"total": 2, "list": [{"_id": "dir", "type": "folder"}]}
                    if body["offset"] == 0
                    else {"total": 2, "list": [{"_id": "plain", "name": "空文档.txt"}]}
                )
            else:
                assert body["parentId"] == "dir"
                data = {"total": 1, "list": [{"_id": "nested", "name": "嵌套课件.ppt"}]}
            return httpx.Response(200, json={"code": 200, "data": data})
        return httpx.Response(200, json={"code": 200, "data": {"total": 0, "list": []}})

    docs = KnowledgeLibrary(s, httpx.MockTransport(handle)).synchronize()
    assert {d["id"] for d in docs} == {"plain", "nested"}
    assert all(d["dataset_name"] == "子库" for d in docs)
    assert next(d for d in docs if d["id"] == "nested")["kind"] == "presentation"


def test_incomplete_pagination_is_not_accepted_as_full_sync():
    response = {"code": 200, "data": {"total": 5, "list": []}}
    with pytest.raises(ValueError, match="未完整"):
        KnowledgeLibrary(
            settings(),
            httpx.MockTransport(lambda _: httpx.Response(200, json=response)),
        ).synchronize()
