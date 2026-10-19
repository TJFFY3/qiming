import hashlib
import json
import copy
import uuid
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from .library import KnowledgeLibrary
from .models import SessionInput, GenerationInput, RevisionInput, ReviewInput
from .resources import extract_resource, MAX_BYTES
from .store import Conflict


def public_source(source):
    return {k: v for k, v in source.items() if k not in ("file_path", "text", "pages")}


def public_version(version):
    v = copy.deepcopy(version)
    v.pop("directory", None)
    v["report"].pop("files", None)
    if "previous" in v["report"]:
        v["report"]["previous"].pop("directory", None)
    return v


def public_job(job):
    return {
        **{k: v for k, v in job.items() if k != "request"},
        "kind": job["request"].get("kind", "generation"),
        "base_version_id": job["request"].get("base_version_id"),
    }


def public_session(session, jobs):
    return {
        **session,
        "resources": [public_source(r) for r in session["resources"]],
        "versions": [public_version(v) for v in session["versions"]],
        "jobs": [public_job(j) for j in jobs],
    }


def make_router(settings, store, pipeline):
    router = APIRouter(prefix="/api")

    library = KnowledgeLibrary(settings)
    library_id = hashlib.sha256(
        json.dumps([settings.fastgpt_url, settings.datasets], sort_keys=True).encode()
    ).hexdigest()

    @router.get("/library")
    def full_library():
        return store.get_library(library_id)

    @router.post("/library/sync")
    def sync_library():
        # Save only a complete sync. A failed refresh retains the previous snapshot.
        return store.save_library(library_id, library.synchronize())

    @router.get("/library/{collection_id}/original")
    def original(collection_id: str):
        if not any(
            d["id"] == collection_id for d in store.get_library(library_id)["documents"]
        ):
            raise KeyError("资料不存在，请先同步知识库")
        return RedirectResponse(library.original_url(collection_id), status_code=303)

    @router.get("/health")
    def health():
        return {
            "status": "ok",
            "ready": not settings.missing(),
            "missing": settings.missing(),
        }

    @router.get("/sessions")
    def sessions():
        return store.list_sessions()

    @router.post("/sessions")
    def create(payload: SessionInput):
        return public_session(store.create_session(payload.model_dump()), [])

    @router.get("/sessions/{session_id}")
    def get(session_id: str):
        return public_session(store.get_session(session_id), store.jobs_for(session_id))

    @router.patch("/sessions/{session_id}")
    def update(session_id: str, payload: SessionInput):
        if any(
            j["status"] in ("queued", "running") for j in store.jobs_for(session_id)
        ):
            raise Conflict("任务执行中，暂不能修改课时设置")
        return public_session(
            store.update_session(
                session_id, lambda s: s.update(settings=payload.model_dump())
            ),
            store.jobs_for(session_id),
        )

    @router.post("/sessions/{session_id}/resources")
    def upload(
        session_id: str, file: UploadFile = File(...), category: str = Form("textbook")
    ):
        if category not in (
            "textbook",
            "teacher_book",
            "exercises",
            "practice",
            "exam",
        ):
            raise HTTPException(400, "资料类别无效")
        session = store.get_session(session_id)
        if len(session["resources"]) >= 10:
            raise HTTPException(400, "每个会话最多10份资料")
        if any(
            j["status"] in ("queued", "running") for j in store.jobs_for(session_id)
        ):
            raise Conflict("任务执行中，请稍后上传")
        identity = uuid.uuid4().hex
        directory = settings.data_dir / session_id / "resources"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / identity
        data = file.file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise HTTPException(400, "文件超过20MB")
        path.write_bytes(data)
        try:
            extracted = extract_resource(path, file.filename or "")
            resource = {
                "id": identity,
                "title": Path((file.filename or "").replace("\\", "/")).name,
                "category": category,
                "locator": "上传原文件（页码见摘录，非印刷页码）",
                "verified": False,
                "file_path": str(path),
                **extracted,
                "evidence": extracted["text"],
            }

            def append(s):
                if len(s["resources"]) >= 10:
                    raise ValueError("每个会话最多10份资料")
                s["resources"].append(resource)

            store.update_session(session_id, append)
            return public_source(resource)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @router.delete("/sessions/{session_id}/resources/{resource_id}")
    def delete_resource(session_id: str, resource_id: str):
        return public_session(
            store.delete_resource(session_id, resource_id), store.jobs_for(session_id)
        )

    @router.get("/sessions/{session_id}/resources")
    def resources(session_id: str):
        session = store.get_session(session_id)
        return {
            "resources": [public_source(r) for r in session["resources"]],
            "sources": session["sources"],
        }

    @router.post("/sessions/{session_id}/sources/{source_id}/review")
    def review(session_id: str, source_id: str, payload: ReviewInput):
        def change(s):
            targets = [x for x in s["sources"] + s["resources"] if x["id"] == source_id]
            if not targets:
                raise KeyError("来源不存在")
            for source in targets:
                source.update(verified=payload.verified, review_note=payload.note)

        return public_session(
            store.update_session(session_id, change), store.jobs_for(session_id)
        )

    @router.post("/sessions/{session_id}/generate")
    def generate(
        session_id: str, payload: GenerationInput, background: BackgroundTasks
    ):
        job = pipeline.start_generation(session_id, payload.model_dump())
        background.add_task(pipeline.run, job["id"])
        return public_job(job)

    @router.post("/sessions/{session_id}/revise")
    def revise(session_id: str, payload: RevisionInput, background: BackgroundTasks):
        job = pipeline.start_revision(session_id, payload.model_dump())
        background.add_task(pipeline.run, job["id"])
        return public_job(job)

    @router.get("/jobs/{job_id}")
    def job(job_id: str):
        return public_job(store.get_job(job_id))

    def find_version(sid, vid):
        version = next(
            (v for v in store.get_session(sid)["versions"] if v["id"] == vid), None
        )
        if version is None:
            raise KeyError("版本不存在")
        return version

    @router.get("/sessions/{session_id}/versions/{version_id}")
    def version(session_id: str, version_id: str):
        return public_version(find_version(session_id, version_id))

    @router.get("/sessions/{session_id}/versions/{version_id}/files/{kind}")
    def download(session_id: str, version_id: str, kind: str):
        v = find_version(session_id, version_id)
        names = {
            "outline": "outline.docx",
            "content": "content.json",
            "report": "generation_report.json",
        }
        if kind not in names:
            raise KeyError("文件类型不存在")
        path = (Path(v["directory"]) / names[kind]).resolve()
        root = (settings.data_dir / session_id / "versions").resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise KeyError("文件不存在")
        if kind == "report":
            from fastapi.responses import JSONResponse

            return JSONResponse(
                public_version(v)["report"],
                headers={
                    "Content-Disposition": f'attachment; filename="{v["number"]}-report.json"'
                },
            )
        return FileResponse(
            path,
            filename=f"{v['number']}-"
            + ("待核验-" if v["report"]["draft"] else "")
            + names[kind],
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if kind == "outline"
            else "application/json",
        )

    return router
