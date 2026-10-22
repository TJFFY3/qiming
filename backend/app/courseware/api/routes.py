"""【接口层·互动课件】管理课件会话、资料、后台任务、预览与下载入口。"""

import json
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from backend.app.shared.knowledge.library import KnowledgeLibrary
from backend.app.shared.tools.publication import clean_office_download, clean_public
from backend.app.shared.tools.resources import MAX_BYTES, extract_resource
from backend.app.courseware.domain.models import CoursewareSettings, Generation, Revision
from backend.app.courseware.tools.ppt_equations import coefficient_download
from backend.app.courseware.tools.formatted_download import display_content, formatted_artifact


def public_resource(resource):
    return {
        k: v for k, v in resource.items() if k not in ("file_path", "text", "pages")
    }


def public_job(job):
    return clean_public(
        {k: v for k, v in job.items() if k not in ("request", "snapshot")}
    )


def make_router(settings, store, pipeline):
    router = APIRouter(prefix="/api/courseware", tags=["互动课件 Agent"])
    library = KnowledgeLibrary(settings)

    def session(sid):
        value = store.get_session(sid)
        value["resources"] = [public_resource(r) for r in value["resources"]]
        value["jobs"] = [public_job(j) for j in store.jobs_for(sid)]
        value["versions"] = [
            {**v, "content": display_content(v["content"])} for v in value["versions"]
        ]
        return clean_public(value)

    @router.get("/health")
    def health():
        needed = (
            ["fastgpt_app_id", "fastgpt_url", "fastgpt_key"]
            if settings.model_provider == "fastgpt"
            else ["model_url", "model_key", "model"]
        )
        missing = [name for name in needed if not getattr(settings, name)]
        return dict(ready=not missing, missing=missing)

    @router.get("/sessions")
    def history():
        return store.list_sessions()

    @router.post("/sessions")
    def create(payload: CoursewareSettings):
        return session(store.create_session(payload.model_dump())["id"])

    @router.get("/sessions/{sid}")
    def get(sid: str):
        return session(sid)

    @router.patch("/sessions/{sid}")
    def update(sid: str, payload: CoursewareSettings):
        store.update_settings(sid, payload.model_dump())
        return session(sid)

    @router.post("/sessions/{sid}/generate")
    def generate(sid: str, payload: Generation, background: BackgroundTasks):
        job = pipeline.start_generation(sid, payload.model_dump())
        background.add_task(pipeline.run, job["id"])
        return public_job(job)

    @router.post("/sessions/{sid}/revise")
    def revise(sid: str, payload: Revision, background: BackgroundTasks):
        job = pipeline.start_revision(sid, payload.model_dump())
        background.add_task(pipeline.run, job["id"])
        return public_job(job)

    @router.get("/jobs/{jid}")
    def job(jid: str):
        return public_job(store.get_job(jid))

    @router.post("/sessions/{sid}/resources")
    def upload(
        sid: str, file: UploadFile = File(...), category: str = Form("textbook")
    ):
        if category not in (
            "textbook",
            "teacher_book",
            "exercises",
            "practice",
            "exam",
        ):
            raise HTTPException(400, "资料类别无效")
        store.get_session(sid)
        resource_id = uuid.uuid4().hex
        directory = settings.data_dir / "courseware" / sid / "resources"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / resource_id
        data = file.file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("文件超过20MB")
        try:
            path.write_bytes(data)
            extracted = extract_resource(path, file.filename or "")
            resource = dict(
                id=resource_id,
                title=Path((file.filename or "").replace("\\", "/")).name,
                category=category,
                locator="本课上传原文；PDF页序不等于印刷页码",
                verified=False,
                file_path=str(path),
                evidence=extracted["text"],
                **extracted,
            )
            store.add_resource(sid, resource)
            return public_resource(resource)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @router.delete("/sessions/{sid}/resources/{rid}")
    def remove(sid: str, rid: str):
        resource = next(
            (r for r in store.get_session(sid)["resources"] if r["id"] == rid), None
        )
        store.delete_resource(sid, rid)
        if resource:
            path = Path(resource["file_path"]).resolve()
            root = (settings.data_dir / "courseware" / sid / "resources").resolve()
            if path.is_relative_to(root):
                path.unlink(missing_ok=True)
        return session(sid)

    def version(sid, vid, formatted=True):
        value = next(
            (v for v in store.get_session(sid)["versions"] if v["id"] == vid), None
        )
        if value is None:
            raise KeyError("课件版本不存在")
        return clean_public({**value, "content": display_content(value["content"])}) if formatted else clean_public(value)

    @router.get("/sessions/{sid}/versions/{vid}")
    def get_version(sid: str, vid: str):
        return version(sid, vid)

    @router.get("/sessions/{sid}/versions/{vid}/images/{image_id}")
    def image(sid: str, vid: str, image_id: str):
        from docx.image.image import Image
        v = version(sid, vid, formatted=False)
        referenced = {s.get("image_id") for s in v["content"]["slides"]}
        if not re.fullmatch(r"[0-9a-f]{24}", image_id) or image_id not in referenced:
            raise KeyError("课件图片不存在")
        root = (settings.data_dir / "courseware").resolve()
        path = (root / sid / "versions" / vid / "images" / (image_id + ".bin")).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise KeyError("课件图片不存在")
        return FileResponse(path, media_type=Image.from_file(str(path)).content_type,
                            headers={"Cache-Control": "private, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"})

    @router.get("/sessions/{sid}/versions/{vid}/files/{kind}")
    def download(sid: str, vid: str, kind: str):
        v = version(sid, vid, formatted=False)
        names = {
            "pptx": "courseware.pptx",
            "content": "content.json",
            "report": "generation_report.json",
        }
        if kind not in names:
            raise KeyError("文件类型不存在")
        root = (settings.data_dir / "courseware").resolve()
        path = (root / sid / "versions" / vid / names[kind]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise KeyError("课件文件不存在")
        if kind != "pptx":
            return JSONResponse(
                clean_public(display_content(v["content"]) if kind == "content" else json.loads(path.read_text())),
                headers={
                    "Content-Disposition": f'attachment; filename="{v["number"]}-{names[kind]}"'
                },
            )
        return FileResponse(
            clean_office_download(coefficient_download(formatted_artifact(v, path, image_origin=settings.fastgpt_url or "https://cloud.fastgpt.cn"))),
            filename=f"{v['number']}-{names[kind]}",
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
            if kind == "pptx"
            else "application/json",
        )

    @router.get("/library")
    def full_library():
        return store.get_library()

    @router.post("/library/sync")
    def sync_library():
        return store.save_library(library.synchronize())

    @router.get("/library/{cid}/original")
    def original(cid: str):
        if not any(d["id"] == cid for d in store.get_library()["documents"]):
            raise KeyError("资料不存在，请先同步")
        return RedirectResponse(library.original_url(cid), status_code=303)

    return router
