import httpx
import pytest
from backend.app.config import Settings
from backend.app.retrieval import FastGPTRetriever
from backend.app.model_client import ModelClient


def configured(**kw):
    return Settings(
        fastgpt_url="https://kb.test/api",
        fastgpt_key="SECRET",
        datasets=[{"id": "dataset1", "category": "textbook"}],
        model_url="https://model.test/v1",
        model_key="MODELSECRET",
        model="model",
        **kw,
    )


def test_search_retains_evidence_and_path():
    def handle(request):
        assert request.url.path == "/api/core/dataset/searchTest"
        assert request.headers["authorization"] == "Bearer SECRET"
        return httpx.Response(
            200,
            json={
                "code": 200,
                "data": [
                    {
                        "id": "hit1",
                        "q": "反应",
                        "a": "化合价变化",
                        "sourceName": "教材.pdf",
                        "collectionId": "col1",
                        "score": 0.9,
                    }
                ],
            },
        )

    hits = FastGPTRetriever(configured(), httpx.MockTransport(handle)).search(
        "氧化还原"
    )
    assert hits[0]["verified"] is False
    assert hits[0]["evidence"] == "反应\n化合价变化"
    assert hits[0]["category"] == "textbook"


@pytest.mark.parametrize(
    "body",
    [
        {"code": 401, "message": "bad SECRET"},
        {"code": 200, "data": {}},
        {"code": 200, "data": [{"id": "bad", "a": None}]},
    ],
)
def test_invalid_or_business_error(body):
    with pytest.raises(ValueError) as exc:
        FastGPTRetriever(
            configured(), httpx.MockTransport(lambda _: httpx.Response(200, json=body))
        ).search("q")
    assert "SECRET" not in str(exc.value)


def test_empty_hits():
    assert (
        FastGPTRetriever(
            configured(),
            httpx.MockTransport(
                lambda _: httpx.Response(200, json={"code": 200, "data": []})
            ),
        ).search("q")
        == []
    )


def test_model_bad_json():
    client = ModelClient(
        configured(),
        httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"choices": [{"message": {"content": "not json"}}]}
            )
        ),
    )
    with pytest.raises(ValueError, match="JSON"):
        client.generate_json([])


def test_fastgpt_model_unconfigured_error():
    body = {
        "code": 513001,
        "statusText": "modelUnConfigured",
        "message": "common:not_model_config",
    }
    with pytest.raises(ValueError, match="模型配置"):
        FastGPTRetriever(
            configured(), httpx.MockTransport(lambda _: httpx.Response(500, json=body))
        ).search("q")


def test_fastgpt_app_generation_uses_app_id_and_controlled_prompt():
    s = configured()
    s.model_provider = "fastgpt"
    s.fastgpt_app_id = "app1"

    def handle(request):
        import json

        body = json.loads(request.content)
        assert request.url.path == "/api/v1/chat/completions"
        assert body["appId"] == "app1"
        assert body["stream"] is False
        assert len(body["messages"]) == 1
        assert "system instructions" in body["messages"][0]["content"]
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"outline": {}}'}}]}
        )

    value = ModelClient(s, httpx.MockTransport(handle)).generate_json(
        [
            {"role": "system", "content": "system instructions"},
            {"role": "user", "content": "task"},
        ]
    )
    assert value == {"outline": {}}


def test_malformed_source_name_rejected():
    body = {
        "code": 200,
        "data": [{"id": "a", "q": "text", "sourceName": {"bad": "object"}}],
    }
    with pytest.raises(ValueError):
        FastGPTRetriever(
            configured(), httpx.MockTransport(lambda _: httpx.Response(200, json=body))
        ).search("q")


@pytest.mark.parametrize("wrapped", [False, True])
def test_folder_expands_and_accepts_cloud_list_response(wrapped):
    s = configured()
    s.datasets = [
        {"id": "folder", "type": "folder", "category": "reference", "name": "教学资料"}
    ]

    def handle(request):
        import json

        body = json.loads(request.content)
        if request.url.path.endswith("/dataset/list"):
            assert body["parentId"] == "folder"
            items = [{"_id": "child", "type": "dataset", "name": "课题知识库"}]
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {"total": 1, "list": items} if wrapped else items,
                },
            )
        assert body["datasetId"] == "child"
        return httpx.Response(
            200,
            json={
                "code": 200,
                "data": {
                    "list": [
                        {
                            "id": "hit",
                            "q": "教材片段",
                            "sourceName": "资料.docx",
                            "score": [{"type": "embedding", "value": 0.8}],
                        }
                    ]
                },
            },
        )

    hits = FastGPTRetriever(s, httpx.MockTransport(handle)).search("氧化还原")
    assert hits[0]["dataset_id"] == "child"
    assert hits[0]["dataset_name"] == "课题知识库"
    assert hits[0]["category"] == "reference" and hits[0]["verified"] is False
