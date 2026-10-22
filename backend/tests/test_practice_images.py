import json
from types import SimpleNamespace

import httpx
import pytest
from docx import Document
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.shared.tools.images import image_catalog
from backend.app.timed_practice.tools.documents import validate_content
from backend.app.timed_practice.application.pipeline import PracticePipeline
from backend.app.timed_practice.domain.requirements import resolve_requirements
from backend.app.timed_practice.tools.images import question_image_catalog
from backend.tests.test_timed_practice import paper, settings, source, PREFIX
from backend.tests.test_study_images import png, URL, ID


def image_source():
    return {**source(), "evidence": "实验装置资料 " + f"![实验装置]({URL})"}


def image_paper():
    content = paper()
    content["choice"][0]["images"] = [
        {"image_id": ID, "caption": "题干装置图", "placement": "stem"},
        {"image_id": ID, "caption": "选项装置图", "placement": "option_B"},
        {"image_id": ID, "caption": "解析示意图", "placement": "explanation"},
    ]
    return content


def test_question_accepts_only_source_bound_images_and_valid_placements():
    constraints = resolve_requirements(settings(), "生成")
    content = validate_content(image_paper(), constraints, [image_source()])
    assert len(content["choice"][0]["images"]) == 3
    assert "images" not in content["choice"][1]
    for change in (
        {"image_id": "f" * 24},
        {"url": "https://evil.test/a.png"},
        {"placement": "unknown"},
    ):
        raw = image_paper()
        raw["choice"][0]["images"][0].update(change)
        with pytest.raises(ValueError):
            validate_content(raw, constraints, [image_source()])
    raw = image_paper()
    raw["choice"][0]["source_ids"] = []
    raw["choice"][0]["origin"] = "new"
    with pytest.raises(ValueError, match="图片|来源"):
        validate_content(raw, constraints, [image_source()])
    raw = image_paper()
    raw["written"][0]["images"] = [
        {"image_id": ID, "caption": "无效选项图", "placement": "option_A"}
    ]
    with pytest.raises(ValueError, match="选项"):
        validate_content(raw, constraints, [image_source()])


def test_image_catalog_does_not_select_template_provenance_for_shared_original():
    template = {**image_source(), "id": "template", "title": "限时练模板.docx"}
    catalog = question_image_catalog([template, image_source()])
    assert catalog[0]["source_id"] == "s1"
    assert question_image_catalog([template]) == []


def app_for_images(tmp_path, offline=False):
    captured = []
    downloads = []

    def factory(config, store):
        class Model:
            def generate_json(self, messages):
                captured.append(json.loads(messages[1]["content"]))
                value = image_paper()
                if "current_practice" in captured[-1]:
                    value["title"] += "（修订）"
                return value

        def remote(request):
            downloads.append(request)
            if offline:
                raise httpx.ConnectError("offline")
            return httpx.Response(200, content=png())

        return PracticePipeline(
            config,
            store,
            SimpleNamespace(search=lambda q: [image_source()]),
            Model(),
            image_transport=httpx.MockTransport(remote),
        )

    return (
        create_app(Settings(data_dir=tmp_path), practice_factory=factory),
        captured,
        downloads,
    )


def test_generation_embeds_images_serves_snapshots_and_revision_reuses_them_offline(
    tmp_path,
):
    app, captured, downloads = app_for_images(tmp_path)
    with TestClient(app) as client:
        sid = client.post(PREFIX + "/sessions", json=settings()).json()["id"]
        job = client.post(
            PREFIX + f"/sessions/{sid}/generate", json={"prompt": "生成带图练习"}
        ).json()
        result = client.get(PREFIX + f"/jobs/{job['id']}").json()
        assert result["status"] == "completed", result
        vid = result["version_id"]
        catalog = captured[0]["image_catalog"]
        assert catalog == [
            {k: v for k, v in image_catalog([image_source()])[0].items() if k != "url"}
        ]
        directory = tmp_path / "timed-practice" / sid / "versions" / vid
        assert (directory / "images" / f"{ID}.bin").read_bytes() == png()
        assert len(downloads) == 1
        for kind, expected in (
            ("paper", ["题干装置图", "选项装置图"]),
            ("answers", ["题干装置图", "解析示意图"]),
        ):
            doc = Document(directory / f"{kind}.docx")
            assert len(doc.inline_shapes) == 2
            text = "\n".join(p.text for p in doc.paragraphs)
            assert all(caption in text for caption in expected)
            assert ("解析示意图" in text) == (kind == "answers")
        url = PREFIX + f"/sessions/{sid}/versions/{vid}/images/"
        response = client.get(url + ID)
        assert response.status_code == 200 and response.content == png()
        assert response.headers["content-type"] == "image/png"
        (directory / "images" / ("f" * 24 + ".bin")).write_bytes(png())
        assert client.get(url + "f" * 24).status_code == 404
        assert client.get(url + "invalid").status_code == 404
        # Cached Word downloads must use version snapshots, without a network request.
        original = (directory / "paper.docx").read_bytes()
        assert (
            client.get(
                PREFIX + f"/sessions/{sid}/versions/{vid}/files/paper"
            ).status_code
            == 200
        )
        assert (directory / "paper.docx").read_bytes() == original
    app, _, offline_downloads = app_for_images(tmp_path, offline=True)
    with TestClient(app) as client:
        job = client.post(
            PREFIX + f"/sessions/{sid}/revise",
            json={"prompt": "修改标题", "base_version_id": vid},
        ).json()
        result = client.get(PREFIX + f"/jobs/{job['id']}").json()
        assert result["status"] == "completed", result
        assert not offline_downloads
        assert (directory / "paper.docx").read_bytes() == original


def test_image_download_failure_does_not_retry_model_or_publish_partial_version(
    tmp_path,
):
    app, captured, downloads = app_for_images(tmp_path, offline=True)
    with TestClient(app) as client:
        sid = client.post(PREFIX + "/sessions", json=settings()).json()["id"]
        job = client.post(
            PREFIX + f"/sessions/{sid}/generate", json={"prompt": "生成"}
        ).json()
        result = client.get(PREFIX + f"/jobs/{job['id']}").json()
        assert result["status"] == "failed" and "原图" in result["error"]
        assert len(captured) == 1 and len(downloads) == 1
        assert client.get(PREFIX + f"/sessions/{sid}").json()["versions"] == []
