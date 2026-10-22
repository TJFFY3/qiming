"""Real HTTP adapters + real document engine; only remote services are replaced."""

import json
from pathlib import Path
import httpx
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.study_guide.application.pipeline import Pipeline
from backend.app.shared.knowledge.retrieval import FastGPTRetriever
from backend.app.study_guide.llm.client import ModelClient
from backend.app.study_guide.tools.documents import DocumentEngine

SAMPLE = json.loads(Path("vendor/chemistry/examples/outline.json").read_text())


def test_http_generation_review_revision_and_download(tmp_path):
    replies = [
        SAMPLE,
        {
            "mode": "patch",
            "changes": [
                {
                    "block_id": "question-1",
                    "replacement": [
                        {
                            "type": "paragraph",
                            "content": "<script>alert(1)</script> 请逐步判断。",
                        }
                    ],
                }
            ],
        },
    ]

    def transport(request):
        if request.url.host == "kb.test":
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": [
                        {
                            "id": "hit",
                            "collectionId": "collection",
                            "sourceName": "教材.pdf",
                            "q": "化合价",
                            "a": "化合价升降是氧化还原反应的特征。",
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(replies.pop(0), ensure_ascii=False)
                        }
                    }
                ]
            },
        )

    settings = Settings(
        fastgpt_url="https://kb.test",
        fastgpt_key="SECRET",
        datasets=[{"id": "data", "category": "textbook"}],
        model_url="https://model.test/v1",
        model_key="MODELSECRET",
        model="model",
        data_dir=tmp_path,
    )
    mock = httpx.MockTransport(transport)

    def factory(s, store):
        return Pipeline(
            s, store, FastGPTRetriever(s, mock), ModelClient(s, mock), DocumentEngine()
        )

    with TestClient(create_app(settings, factory)) as client:
        sid = client.post("/api/sessions", json={}).json()["id"]
        # Source verification is optional: the first request already creates a downloadable version.
        job = client.post(
            f"/api/sessions/{sid}/generate", json={"prompt": "设计导学案"}
        ).json()
        assert client.get("/api/jobs/" + job["id"]).json()["status"] == "completed"
        session = client.get(f"/api/sessions/{sid}").json()
        first_version = session["versions"][0]
        assert (
            client.get(
                f"/api/sessions/{sid}/versions/{first_version['id']}/files/outline"
            ).status_code
            == 200
        )
        source = session["sources"][0]
        assert source["verified"] is False
        client.post(
            f"/api/sessions/{sid}/sources/{source['id']}/review",
            json={"verified": True, "note": "已查看教材原文并核对摘录"},
        )
        # The fixture's intentional source gap must be removed explicitly by the test content author.
        clean = json.loads(json.dumps(SAMPLE))
        clean["source_gaps"] = []
        clean["sources"] = [{"verified": True, "title": "模型伪造来源"}]
        replies.insert(0, clean)
        job = client.post(
            f"/api/sessions/{sid}/generate", json={"prompt": "设计导学案"}
        ).json()
        assert client.get("/api/jobs/" + job["id"]).json()["status"] == "completed"
        session = client.get(f"/api/sessions/{sid}").json()
        version = session["versions"][-1]
        assert version["report"]["draft"] is False
        assert (
            len(version["sources"]) == 1
            and version["sources"][0]["title"] == "教材.pdf"
        )
        assert "directory" not in version and "files" not in version["report"]
        download = client.get(
            f"/api/sessions/{sid}/versions/{version['id']}/files/outline"
        )
        assert download.status_code == 200 and download.content[:2] == b"PK"
        assert (
            client.get(
                f"/api/sessions/{sid}/versions/{version['id']}/files/secret"
            ).status_code
            == 404
        )
        job = client.post(
            f"/api/sessions/{sid}/revise",
            json={"prompt": "增加分步提示", "base_version_id": version["id"]},
        ).json()
        assert client.get("/api/jobs/" + job["id"]).json()["status"] == "completed"
        session = client.get(f"/api/sessions/{sid}").json()
        assert len(session["versions"]) == 3
        assert session["versions"][1]["content"] == version["content"]
        assert session["versions"][0]["content"] == first_version["content"]
        assert (
            client.post(
                f"/api/sessions/{sid}/revise",
                json={"prompt": "错误基线", "base_version_id": version["id"]},
            ).status_code
            == 409
        )
        assert "SECRET" not in json.dumps(session)
