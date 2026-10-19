from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app


def test_health_and_session(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        health = client.get("/api/health").json()
        assert health["ready"] is False
        assert "fastgpt_key" in health["missing"]
        session = client.post("/api/sessions", json={"chapter": "氧化还原反应"}).json()
        assert (
            client.get("/api/sessions/" + session["id"]).json()["settings"]["chapter"]
            == "氧化还原反应"
        )
        assert client.get("/api/sessions/not-found").status_code == 404
        assert (
            client.get(
                "/api/sessions/" + session["id"] + "/versions/no/files/outline"
            ).status_code
            == 404
        )
        assert client.get("/api/no-such-route").status_code == 404


def test_upload_and_review(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        sid = client.post("/api/sessions", json={}).json()["id"]
        response = client.post(
            f"/api/sessions/{sid}/resources",
            files={"file": ("教材.txt", "教材原文".encode(), "text/plain")},
            data={"category": "textbook"},
        )
        assert response.status_code == 200, response.text
        source = response.json()
        assert "file_path" not in source
        assert source["verified"] is False
        assert (
            client.post(
                f"/api/sessions/{sid}/sources/{source['id']}/review",
                json={"verified": True, "note": "已核对原文"},
            ).status_code
            == 200
        )
        session = client.get(f"/api/sessions/{sid}").json()
        assert session["resources"][0]["verified"] is True
        response = client.post(
            f"/api/sessions/{sid}/resources",
            files={"file": ("fake.docx", b"bad", "application/octet-stream")},
        )
        assert response.status_code == 400


def test_unknown_review_and_invalid_revision(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        sid = client.post("/api/sessions", json={}).json()["id"]
        assert (
            client.post(
                f"/api/sessions/{sid}/sources/fake/review",
                json={"verified": True, "note": "核验"},
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/sessions/{sid}/revise",
                json={"prompt": "修改", "base_version_id": "fake"},
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/api/sessions/{sid}/generate", json={"prompt": "x" * 9000}
            ).status_code
            == 422
        )


def test_full_library_is_independent_of_session_recall(tmp_path, monkeypatch):
    from backend.app.library import KnowledgeLibrary

    docs = [
        {
            "id": "ppt",
            "title": "课件.pptx",
            "dataset_name": "知识库",
            "kind": "presentation",
            "chunks": [{"id": "all", "evidence": "未命中但属于全库的片段"}],
        }
    ]
    monkeypatch.setattr(KnowledgeLibrary, "synchronize", lambda _: docs)
    monkeypatch.setattr(
        KnowledgeLibrary, "original_url", lambda _, cid: "https://files.test/课件.pptx"
    )
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={}).json()["id"]
        assert client.get("/api/library").json()["synced_at"] is None
        result = client.post("/api/library/sync").json()
        assert result["documents"] == docs
        assert result["chunk_count"] == 1
        assert client.get("/api/library").json() == result
        assert client.get(f"/api/sessions/{sid}").json()["sources"] == []
        assert (
            client.get("/api/library/ppt/original", follow_redirects=False).status_code
            == 303
        )
        assert client.get("/api/library/unknown/original").status_code == 404
    # The full catalog survives restart, without a model/search call.
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        assert client.get("/api/library").json()["documents"] == docs


def test_failed_full_sync_retains_previous_catalog(tmp_path, monkeypatch):
    from backend.app.library import KnowledgeLibrary

    monkeypatch.setattr(
        KnowledgeLibrary, "synchronize", lambda _: [{"id": "ok", "chunks": []}]
    )
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        saved = client.post("/api/library/sync").json()

        def fail(_):
            raise ValueError("读取中断")

        monkeypatch.setattr(KnowledgeLibrary, "synchronize", fail)
        assert client.post("/api/library/sync").status_code == 400
        assert client.get("/api/library").json() == saved


def test_delete_uploaded_resource_removes_active_sources_only(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={}).json()["id"]
        source = client.post(
            f"/api/sessions/{sid}/resources",
            files={"file": ("教材.txt", "保留历史原文".encode(), "text/plain")},
        ).json()
        store = app.state.store

        def seed(s):
            s["sources"] = [source, {"id": "kb-hit", "evidence": "知识库命中"}]
            s["versions"] = [{"id": "v1", "report": {}, "sources": [source]}]

        store.update_session(sid, seed)
        response = client.delete(f"/api/sessions/{sid}/resources/{source['id']}")
        assert response.status_code == 200
        current = response.json()
        assert current["resources"] == []
        assert [s["id"] for s in current["sources"]] == ["kb-hit"]
        assert current["versions"][0]["sources"] == [source]
        assert client.delete(f"/api/sessions/{sid}/resources/kb-hit").status_code == 404
        assert (
            client.delete(f"/api/sessions/{sid}/resources/{source['id']}").status_code
            == 404
        )
        other = client.post("/api/sessions", json={}).json()["id"]
        assert (
            client.delete(f"/api/sessions/{other}/resources/kb-hit").status_code == 404
        )


def test_deleting_resource_during_generation_is_rejected(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={}).json()["id"]
        source = client.post(
            f"/api/sessions/{sid}/resources",
            files={"file": ("教材.txt", b"evidence", "text/plain")},
        ).json()
        app.state.store.create_job(sid, {"kind": "generation", "prompt": "生成"})
        response = client.delete(f"/api/sessions/{sid}/resources/{source['id']}")
        assert response.status_code == 409
        assert (
            client.get(f"/api/sessions/{sid}").json()["resources"][0]["id"]
            == source["id"]
        )
