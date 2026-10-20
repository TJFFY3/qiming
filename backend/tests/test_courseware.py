"""Courseware boundaries: real DB/export and HTTP adapter, only remote HTTP replaced."""

import copy
import io
import json
from zipfile import ZipFile

import httpx
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app

PREFIX = "/api/courseware"


def deck(title="氧化还原反应"):
    return {
        "title": title,
        "slides": [
            {
                "title": "情境导入",
                "stage": "启",
                "paragraphs": ["观察反应中元素化合价的变化。"],
                "notes": "引导观察",
            },
            {
                "title": "电子转移",
                "stage": "析",
                "paragraphs": ["2[Na] + [Cl2] = 2[NaCl]", "[Fe^3+] 与 [SO4^2-]"],
                "notes": "教师提示",
            },
        ],
        "source_gaps": [],
        "conflicts": [],
    }


def app_for(tmp_path, replies=None, hits=True):
    from backend.app.courseware.model_client import CoursewareModelClient
    from backend.app.courseware.pipeline import CoursewarePipeline
    from backend.app.retrieval import FastGPTRetriever

    responses = list(replies or [deck()])
    requests = []

    def remote(request):
        requests.append(json.loads(request.content))
        if request.url.host == "kb.test":
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": [
                        {
                            "id": "hit",
                            "collectionId": "book",
                            "sourceName": "教材.pdf",
                            "q": "化合价",
                            "a": "电子得失与化合价变化。",
                        }
                    ]
                    if hits
                    else [],
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(responses.pop(0), ensure_ascii=False)
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(remote)
    settings = Settings(
        data_dir=tmp_path,
        fastgpt_url="https://kb.test",
        fastgpt_key="SECRET",
        datasets=[{"id": "book", "category": "textbook"}],
        model_url="https://model.test/v1",
        model_key="MODELSECRET",
        model="test",
    )

    def factory(s, store):
        return CoursewarePipeline(
            s,
            store,
            FastGPTRetriever(s, transport),
            CoursewareModelClient(s, transport),
        )

    return create_app(settings, courseware_factory=factory), requests


def test_courseware_namespace_exists_and_rejects_guide_session(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        guide = client.post("/api/sessions", json={}).json()
        response = client.post(PREFIX + "/sessions", json={})
        assert response.status_code == 200
        course = response.json()
        assert client.get(PREFIX + "/sessions/" + guide["id"]).status_code == 404
        assert client.get("/api/sessions/" + course["id"]).status_code == 404
        assert len(client.get("/api/sessions").json()) == 1
        assert len(client.get(PREFIX + "/sessions").json()) == 1


def test_generate_actual_editable_pptx_revision_and_snapshot(tmp_path):
    app, requests = app_for(
        tmp_path, [deck(), {"mode": "patch", "title": "修改后课件", "changes": []}]
    )
    with TestClient(app) as client:
        sid = client.post(PREFIX + "/sessions", json={}).json()["id"]
        job = client.post(
            f"{PREFIX}/sessions/{sid}/generate",
            json={"prompt": "设计互动课件", "allow_draft": True},
        ).json()
        done = client.get(PREFIX + "/jobs/" + job["id"]).json()
        assert done["status"] == "completed", done
        session = client.get(PREFIX + "/sessions/" + sid).json()
        original = copy.deepcopy(session["versions"][0])
        assert original["report"]["validation"]["passed"]
        assert original["report"]["draft"] is False
        assert original["sources"][0]["verified"] is False
        assert "directory" not in original
        assert "SECRET" not in json.dumps(session)
        url = f"{PREFIX}/sessions/{sid}/versions/{original['id']}/files/pptx"
        response = client.get(url)
        assert response.status_code == 200
        assert (
            "%E5%BE%85%E6%A0%B8%E9%AA%8C" not in response.headers["content-disposition"]
        )
        with ZipFile(io.BytesIO(response.content)) as z:
            slides = [
                n
                for n in z.namelist()
                if n.startswith("ppt/slides/slide") and n.endswith(".xml")
            ]
            assert len(slides) == 2
            assert b'baseline="-25000"' in z.read("ppt/slides/slide2.xml")
            assert b'baseline="30000"' in z.read("ppt/slides/slide2.xml")
        revision = client.post(
            f"{PREFIX}/sessions/{sid}/revise",
            json={
                "prompt": "修改标题",
                "base_version_id": original["id"],
                "allow_draft": True,
            },
        ).json()
        assert (
            client.get(PREFIX + "/jobs/" + revision["id"]).json()["status"]
            == "completed"
        )
        latest = client.get(PREFIX + "/sessions/" + sid).json()
        assert latest["versions"][0] == original
        assert latest["versions"][1]["content"]["title"] == "修改后课件"
        assert client.get(url).content == response.content
        assert (
            client.post(
                f"{PREFIX}/sessions/{sid}/revise",
                json={"prompt": "旧版本", "base_version_id": original["id"]},
            ).status_code
            == 409
        )
        assert all(
            "导学案内容任务" not in json.dumps(r, ensure_ascii=False) for r in requests
        )
        assert (tmp_path / "courseware" / "agent.sqlite").exists()


def test_source_gap_does_not_gate_generation_and_uploads_are_isolated(tmp_path):
    app, _ = app_for(tmp_path, [deck(), deck()], hits=False)
    with TestClient(app) as client:
        sid = client.post(PREFIX + "/sessions", json={}).json()["id"]
        job = client.post(
            f"{PREFIX}/sessions/{sid}/generate", json={"prompt": "设计课件"}
        ).json()
        done = client.get(PREFIX + "/jobs/" + job["id"]).json()
        assert done["status"] == "completed", done
        assert client.get(PREFIX + "/sessions/" + sid).json()["versions"]
        upload = client.post(
            f"{PREFIX}/sessions/{sid}/resources",
            files={"file": ("教材.txt", "电子转移是实质。".encode(), "text/plain")},
            data={"category": "textbook"},
        )
        assert upload.status_code == 200
        resource = upload.json()
        assert "file_path" not in resource
        job = client.post(
            f"{PREFIX}/sessions/{sid}/generate",
            json={"prompt": "设计课件", "allow_draft": True},
        ).json()
        assert client.get(PREFIX + "/jobs/" + job["id"]).json()["status"] == "completed"
        version = client.get(PREFIX + "/sessions/" + sid).json()["versions"][0]
        assert (
            client.delete(
                f"{PREFIX}/sessions/{sid}/resources/{resource['id']}"
            ).status_code
            == 200
        )
        assert (
            client.get(PREFIX + "/sessions/" + sid).json()["versions"][0]["sources"]
            == version["sources"]
        )


def test_invalid_model_paths_and_overflow_fail_without_pptx(tmp_path):
    for bad in [
        dict(deck(), slides=[dict(deck()["slides"][0], image="/etc/passwd")]),
        dict(deck(), slides=[dict(deck()["slides"][0], paragraphs=["字" * 201])]),
    ]:
        app, _ = app_for(tmp_path, [bad, bad, bad])
        with TestClient(app) as client:
            sid = client.post(PREFIX + "/sessions", json={}).json()["id"]
            job = client.post(
                f"{PREFIX}/sessions/{sid}/generate",
                json={"prompt": "设计", "allow_draft": True},
            ).json()
            assert (
                client.get(PREFIX + "/jobs/" + job["id"]).json()["status"] == "failed"
            )
            assert not client.get(PREFIX + "/sessions/" + sid).json()["versions"]


def test_atomic_reservation_and_restart_recovery(tmp_path):
    import pytest

    from backend.app.courseware.store import CoursewareConflict, CoursewareStore

    store = CoursewareStore(tmp_path / "courseware" / "agent.sqlite")
    sid = store.create_session({})["id"]
    job = store.reserve(sid, {"prompt": "设计", "allow_draft": True}, "generation")
    with pytest.raises(CoursewareConflict):
        store.reserve(sid, {"prompt": "重复"}, "generation")
    with pytest.raises(CoursewareConflict):
        store.update_settings(sid, {})
    store.recover_jobs()
    assert store.get_job(job["id"])["status"] == "failed"
    assert "中断" in store.get_job(job["id"])["error"]


def test_library_sync_stores_complete_documents_and_keeps_cache_on_failure(
    tmp_path, monkeypatch
):
    from backend.app.library import KnowledgeLibrary

    documents = [
        {
            "id": "book",
            "title": "教材.pdf",
            "dataset_name": "教材库",
            "kind": "document",
            "chunks": [
                {
                    "id": "chunk",
                    "title": "定义",
                    "locator": "第一章",
                    "evidence": "电子转移",
                }
            ],
        }
    ]
    monkeypatch.setattr(KnowledgeLibrary, "synchronize", lambda _: documents)
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        synced = client.post(PREFIX + "/library/sync", json={})
        assert synced.status_code == 200
        assert synced.json()["documents"] == documents
        assert synced.json()["chunk_count"] == 1
        assert client.get(PREFIX + "/library").json()["documents"] == documents
        assert client.get("/api/library").json()["documents"] == []

        def broken(_):
            raise ValueError("同步失败")

        monkeypatch.setattr(KnowledgeLibrary, "synchronize", broken)
        assert client.post(PREFIX + "/library/sync", json={}).status_code == 400
        assert client.get(PREFIX + "/library").json()["documents"] == documents


def test_page_count_conflict_is_visible_and_submission_settings_are_snapshotted(
    tmp_path,
):
    app, _ = app_for(tmp_path)
    with TestClient(app) as client:
        sid = client.post(
            PREFIX + "/sessions", json={"options": {"pages": "15 页"}}
        ).json()["id"]
        job = client.post(
            f"{PREFIX}/sessions/{sid}/generate", json={"allow_draft": True}
        ).json()
        done = client.get(PREFIX + "/jobs/" + job["id"]).json()
        assert done["status"] == "completed", done
        version = client.get(PREFIX + "/sessions/" + sid).json()["versions"][0]
        assert any("15" in c and "2" in c for c in version["report"]["conflicts"])


def test_revision_retains_original_evidence_after_upload_is_removed(tmp_path):
    app, _ = app_for(
        tmp_path,
        [deck(), {"mode": "patch", "title": "修改标题", "changes": []}],
        hits=False,
    )
    with TestClient(app) as client:
        sid = client.post(PREFIX + "/sessions", json={}).json()["id"]
        resource = client.post(
            f"{PREFIX}/sessions/{sid}/resources",
            files={"file": ("教材.txt", "原文证据：电子转移。".encode(), "text/plain")},
        ).json()
        first = client.post(
            f"{PREFIX}/sessions/{sid}/generate", json={"allow_draft": True}
        ).json()
        assert (
            client.get(PREFIX + "/jobs/" + first["id"]).json()["status"] == "completed"
        )
        v1 = client.get(PREFIX + "/sessions/" + sid).json()["versions"][0]
        client.delete(f"{PREFIX}/sessions/{sid}/resources/{resource['id']}")
        second = client.post(
            f"{PREFIX}/sessions/{sid}/revise",
            json={
                "prompt": "只改标题",
                "allow_draft": True,
                "base_version_id": v1["id"],
            },
        ).json()
        assert (
            client.get(PREFIX + "/jobs/" + second["id"]).json()["status"] == "completed"
        )
        v2 = client.get(PREFIX + "/sessions/" + sid).json()["versions"][1]
        assert v2["sources"] == v1["sources"]


def test_draft_cover_does_not_silently_truncate_topic(tmp_path):
    import pytest

    from backend.app.courseware.export import export_deck

    raw = deck()
    raw["slides"][0]["title"] = "探究氯气与氢氧化钠反应中的电子转移规律"
    content, _ = export_deck(raw, tmp_path, True)
    assert content["slides"][0]["title"] == "探究氯气与氢氧化钠反应中的电子转移规律"
    raw["slides"][0]["title"] = "字" * 24
    with pytest.raises(ValueError, match="标题过长"):
        export_deck(raw, tmp_path, True)


def test_model_placeholder_content_is_repaired_before_delivery(tmp_path):
    bad = deck()
    bad["slides"][0]["paragraphs"] = ["授课教师：XXX", "日期：XXXX年XX月"]
    app, _ = app_for(tmp_path, [bad, deck()])
    with TestClient(app) as client:
        sid = client.post(PREFIX + "/sessions", json={}).json()["id"]
        job = client.post(
            f"{PREFIX}/sessions/{sid}/generate", json={"allow_draft": True}
        ).json()
        assert client.get(PREFIX + "/jobs/" + job["id"]).json()["status"] == "completed"
        v = client.get(PREFIX + "/sessions/" + sid).json()["versions"][0]
        assert "XXX" not in json.dumps(v["content"])


def test_new_upload_is_in_revision_context_when_baseline_uses_full_budget(tmp_path):
    app, requests = app_for(
        tmp_path,
        [deck(), {"mode": "patch", "title": "依据新资料修订", "changes": []}],
        hits=False,
    )
    with TestClient(app) as client:
        sid = client.post(PREFIX + "/sessions", json={}).json()["id"]
        for i in range(4):
            assert (
                client.post(
                    f"{PREFIX}/sessions/{sid}/resources",
                    files={
                        "file": (
                            f"旧资料{i}.txt",
                            ("旧" * 12000).encode(),
                            "text/plain",
                        )
                    },
                ).status_code
                == 200
            )
        client.post(f"{PREFIX}/sessions/{sid}/generate", json={"allow_draft": True})
        v1 = client.get(PREFIX + "/sessions/" + sid).json()["versions"][0]
        client.post(
            f"{PREFIX}/sessions/{sid}/resources",
            files={
                "file": (
                    "新资料.txt",
                    "新资料独有证据：化合价变化。".encode(),
                    "text/plain",
                )
            },
        )
        client.post(
            f"{PREFIX}/sessions/{sid}/revise",
            json={
                "prompt": "按新资料修订",
                "allow_draft": True,
                "base_version_id": v1["id"],
            },
        )
        v2 = client.get(PREFIX + "/sessions/" + sid).json()["versions"][1]
        assert len(v2["sources"]) == 5
        assert "新资料独有证据" in json.dumps(requests[-1], ensure_ascii=False)
        assert v2["sources"][:4] == v1["sources"]


def test_page_patch_replaces_only_requested_page_and_keeps_other_pages(tmp_path):
    changed = {
        "title": "新封面",
        "stage": "启",
        "paragraphs": ["课堂主题"],
        "notes": "封面",
    }
    patch = {"mode": "patch", "changes": [{"page": 1, "slide": changed}]}
    app, _ = app_for(tmp_path, [deck(), patch])
    with TestClient(app) as client:
        sid = client.post(PREFIX + "/sessions", json={}).json()["id"]
        client.post(f"{PREFIX}/sessions/{sid}/generate", json={"allow_draft": True})
        first = client.get(PREFIX + "/sessions/" + sid).json()["versions"][0]
        job = client.post(
            f"{PREFIX}/sessions/{sid}/revise",
            json={
                "prompt": "只修改封面，保留其他页面",
                "base_version_id": first["id"],
                "allow_draft": True,
            },
        ).json()
        done = client.get(PREFIX + "/jobs/" + job["id"]).json()
        assert done["status"] == "completed", done
        latest = client.get(PREFIX + "/sessions/" + sid).json()["versions"][-1]
        assert len(latest["content"]["slides"]) == 2
        assert latest["content"]["slides"][1] == first["content"]["slides"][1]
        assert latest["content"]["slides"][0]["paragraphs"] == ["课堂主题"]


def test_out_of_range_page_patch_does_not_create_version(tmp_path):
    bad = {"mode": "patch", "changes": [{"page": 9, "slide": deck()["slides"][0]}]}
    app, _ = app_for(tmp_path, [deck(), bad, bad, bad])
    with TestClient(app) as client:
        sid = client.post(PREFIX + "/sessions", json={}).json()["id"]
        client.post(f"{PREFIX}/sessions/{sid}/generate", json={"allow_draft": True})
        first = client.get(PREFIX + "/sessions/" + sid).json()["versions"][0]
        job = client.post(
            f"{PREFIX}/sessions/{sid}/revise",
            json={
                "prompt": "修改封面",
                "base_version_id": first["id"],
                "allow_draft": True,
            },
        ).json()
        assert client.get(PREFIX + "/jobs/" + job["id"]).json()["status"] == "failed"
        assert len(client.get(PREFIX + "/sessions/" + sid).json()["versions"]) == 1


def test_full_revision_requires_explicit_mode_even_if_prompt_mentions_adding_pages():
    import pytest

    from backend.app.courseware.models import Revision
    from backend.app.courseware.revision import merge_revision

    raw = {"mode": "full", "deck": deck("整体改写")}
    with pytest.raises(ValueError, match="整体"):
        merge_revision(
            raw,
            deck(),
            "只修改第2页，不要新增页面，保留其他内容",
            allow_full_revision=False,
        )
    request = Revision(
        prompt="将课件改为3页", base_version_id="v1", allow_full_revision=True
    )
    raw["deck"]["slides"].append(copy.deepcopy(raw["deck"]["slides"][0]))
    result = merge_revision(
        raw, deck(), request.prompt, allow_full_revision=request.allow_full_revision
    )
    assert len(result["slides"]) == 3


def test_equation_content_errors_trigger_model_repair_before_publication(tmp_path):
    missing = deck()
    missing["slides"][0]["paragraphs"] = [
        [{"text": "Zn + H2SO4"}, {"text": "ZnSO4 + H2↑"}]
    ]
    unbalanced = deck()
    unbalanced["slides"][0]["paragraphs"] = [
        [{"text": "Cu + O2"}, {"text": "△", "condition": True}, {"text": "CuO"}]
    ]
    corrected = deck()
    corrected["slides"][0]["paragraphs"] = [
        [{"text": "2Cu + O2 "}, {"text": "△", "condition": True}, {"text": " 2CuO"}]
    ]
    app, requests = app_for(tmp_path, [missing, unbalanced, corrected])
    with TestClient(app) as client:
        sid = client.post(PREFIX + "/sessions", json={}).json()["id"]
        job = client.post(f"{PREFIX}/sessions/{sid}/generate", json={}).json()
        assert client.get(PREFIX + "/jobs/" + job["id"]).json()["status"] == "completed"
        versions = client.get(PREFIX + "/sessions/" + sid).json()["versions"]
        assert len(versions) == 1
        assert (
            versions[0]["content"]["slides"][0]["paragraphs"][0][0]["text"]
            == "2[Cu] + [O2] "
        )
        assert "缺少连接符" in json.dumps(requests, ensure_ascii=False)
        assert "原子数不守恒" in json.dumps(requests, ensure_ascii=False)
