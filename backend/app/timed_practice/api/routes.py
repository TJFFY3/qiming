"""【接口层·限时练习】装配独立练习依赖，提供会话、任务、资料、预览与两份 Word 下载。"""

import hashlib
import json
import uuid
import re
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from backend.app.shared.tools.publication import clean_public, clean_office_download
from backend.app.shared.knowledge.library import KnowledgeLibrary
from backend.app.shared.tools.resources import extract_resource, MAX_BYTES
from backend.app.shared.knowledge.retrieval import FastGPTRetriever
from backend.app.timed_practice.configuration.settings import practice_settings
from backend.app.timed_practice.domain.models import LessonSettings, GenerateInput, ReviseInput, ReviewInput
from backend.app.timed_practice.storage.store import PracticeStore
from backend.app.timed_practice.llm.client import PracticeModelClient
from backend.app.timed_practice.application.pipeline import PracticePipeline
from backend.app.timed_practice.domain.equations import format_content
from backend.app.timed_practice.tools.formatted_download import formatted_artifact
from backend.app.timed_practice.tools.images import image_blocks


def public_source(source):
    return clean_public(
        {k: v for k, v in source.items() if k not in ("file_path", "text", "pages")}
    )


def public_job(job):
    return clean_public(
        {
            k: v
            for k, v in job.items()
            if k not in ("request", "can_draft", "allow_draft")
        }
        | dict(
            kind=job["request"]["kind"],
            base_version_id=job["request"].get("base_version_id"),
        )
    )


def public_version(version):
    return clean_public(
        {k: v for k, v in version.items() if k != "directory"}
        | {"content": format_content(version["content"])}
    )


def make_router(base_settings, pipeline_factory=None):
    settings = practice_settings(base_settings)
    store = PracticeStore(settings.data_dir / "practice.sqlite")
    pipeline = (
        pipeline_factory(settings, store)
        if pipeline_factory
        else PracticePipeline(
            settings, store, FastGPTRetriever(settings), PracticeModelClient(settings)
        )
    )
    router = APIRouter(prefix="/api/timed-practice", tags=["独立限时练习"])
    library = KnowledgeLibrary(settings)
    identity = hashlib.sha256(
        json.dumps([settings.fastgpt_url, settings.datasets], sort_keys=True).encode()
    ).hexdigest()

    def session_response(sid):
        s = store.get_session(sid)
        return clean_public(
            s
            | dict(
                resources=[public_source(r) for r in s["resources"]],
                versions=[public_version(v) for v in s["versions"]],
                jobs=[public_job(j) for j in store.jobs_for(sid)],
            )
        )

    @router.get("/health")
    def health():
        return dict(ready=not settings.missing(), missing=settings.missing())

    @router.get("/library")
    def catalog():
        return clean_public(store.get_library(identity))

    @router.post("/library/sync")
    def sync_catalog():
        return clean_public(store.save_library(identity, library.synchronize()))

    @router.get("/library/{collection_id}/original")
    def original(collection_id: str):
        if not any(
            d["id"] == collection_id for d in store.get_library(identity)["documents"]
        ):
            raise KeyError("资料不存在")
        return RedirectResponse(library.original_url(collection_id), status_code=303)

    @router.get("/sessions")
    def history():
        return clean_public(store.list_sessions())

    @router.post("/sessions")
    def create(payload: LessonSettings):
        return session_response(store.create_session(payload.model_dump())["id"])

    @router.get("/sessions/{sid}")
    def get_session(sid: str):
        return session_response(sid)

    @router.patch("/sessions/{sid}")
    def update(sid: str, payload: LessonSettings):
        store.change_idle(sid, lambda s: s.update(settings=payload.model_dump()))
        return session_response(sid)

    @router.post("/sessions/{sid}/resources")
    def upload(
        sid: str, file: UploadFile = File(...), category: str = Form("textbook")
    ):
        store.get_session(sid)
        if category not in (
            "textbook",
            "teacher_book",
            "exercises",
            "practice",
            "exam",
        ):
            raise ValueError("资料类型无效")
        data = file.file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("文件超过20MB")
        rid = uuid.uuid4().hex
        path = settings.data_dir / sid / "resources" / rid
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        try:
            extracted = extract_resource(path, file.filename or "")
            resource = dict(
                id=rid,
                title=Path((file.filename or "").replace("\\", "/")).name,
                category=category,
                locator="上传原文件（PDF页序非印刷页码）",
                verified=False,
                file_path=str(path),
                evidence=extracted["text"],
                **extracted,
            )

            def append(s):
                if len(s["resources"]) >= 10:
                    raise ValueError("每个限时练习会话最多10份资料")
                s["resources"].append(resource)

            store.change_idle(sid, append)
            return public_source(resource)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @router.delete("/sessions/{sid}/resources/{rid}")
    def remove(sid: str, rid: str):
        def change(s):
            if not any(r["id"] == rid for r in s["resources"]):
                raise KeyError("本课资料不存在")
            s["resources"] = [r for r in s["resources"] if r["id"] != rid]
            s["sources"] = [r for r in s["sources"] if r["id"] != rid]

        store.change_idle(sid, change)
        return session_response(sid)

    @router.post("/sessions/{sid}/sources/{source_id}/review")
    def review(sid: str, source_id: str, payload: ReviewInput):
        def change(s):
            targets = [r for r in s["resources"] + s["sources"] if r["id"] == source_id]
            if not targets:
                raise KeyError("来源不存在")
            for r in targets:
                r.update(verified=payload.verified, review_note=payload.note)

        store.change_idle(sid, change)
        return session_response(sid)

    @router.post("/sessions/{sid}/generate")
    def generate(sid: str, payload: GenerateInput, background: BackgroundTasks):
        j = store.create_job(sid, payload.model_dump() | dict(kind="generation"))
        background.add_task(pipeline.run, j["id"])
        return public_job(j)

    @router.post("/sessions/{sid}/revise")
    def revise(sid: str, payload: ReviseInput, background: BackgroundTasks):
        j = store.create_job(sid, payload.model_dump() | dict(kind="revision"))
        background.add_task(pipeline.run, j["id"])
        return public_job(j)

    @router.get("/jobs/{jid}")
    def get_job(jid: str):
        return public_job(store.get_job(jid))

    def find_version(sid, vid):
        v = next(
            (v for v in store.get_session(sid)["versions"] if v["id"] == vid), None
        )
        if not v:
            raise KeyError("限时练习版本不存在")
        return v

    @router.get("/sessions/{sid}/versions/{vid}")
    def version(sid: str, vid: str):
        return public_version(find_version(sid, vid))

    @router.get("/sessions/{sid}/versions/{vid}/files/{kind}")
    def download(sid: str, vid: str, kind: str):
        v = find_version(sid, vid)
        names = {
            "paper": "paper.docx",
            "answers": "answers.docx",
            "content": "content.json",
            "report": "generation_report.json",
        }
        if kind not in names:
            raise KeyError("文件类型不存在")
        path = (Path(v["directory"]) / names[kind]).resolve()
        root = (settings.data_dir / sid / "versions").resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise KeyError("文件不存在")
        name = (
            v["number"]
            + "-"
            + (
                "学生卷.docx"
                if kind == "paper"
                else "答案解析卷.docx"
                if kind == "answers"
                else names[kind]
            )
        )
        if kind in ("content", "report"):
            return JSONResponse(
                clean_public(
                    format_content(v["content"])
                    if kind == "content"
                    else json.loads(path.read_text(encoding="utf-8"))
                ),
                headers={"Content-Disposition": f'attachment; filename="{name}"'},
            )
        return FileResponse(
            clean_office_download(formatted_artifact(v, kind, settings)),
            filename=name,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if kind in ("paper", "answers")
            else "application/json",
        )

    @router.get("/sessions/{sid}/versions/{vid}/images/{image_id}")
    def image(sid: str, vid: str, image_id: str):
        from docx.image.image import Image

        value = next(
            (v for v in store.get_session(sid)["versions"] if v["id"] == vid), None
        )
        if value is None:
            raise KeyError("版本不存在")
        referenced = {block["image_id"] for block in image_blocks(value["content"])}
        if not re.fullmatch(r"[0-9a-f]{24}", image_id) or image_id not in referenced:
            raise KeyError("图片不存在")
        path = (Path(value["directory"]) / "images" / f"{image_id}.bin").resolve()
        root = (settings.data_dir / sid / "versions").resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise KeyError("图片不存在")
        return FileResponse(
            path,
            media_type=Image.from_file(str(path)).content_type,
            headers={
                "Cache-Control": "private, max-age=31536000, immutable",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router, store
