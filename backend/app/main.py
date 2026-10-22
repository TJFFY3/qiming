"""【应用装配】创建三个 Agent 的独立存储、模型客户端和流程，注册 HTTP 路由。"""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from backend.app.config import settings as default_settings
from backend.app.study_guide.storage.store import Store, Conflict
from backend.app.shared.knowledge.retrieval import FastGPTRetriever
from backend.app.study_guide.llm.client import ModelClient
from backend.app.study_guide.tools.documents import DocumentEngine
from backend.app.study_guide.application.pipeline import Pipeline
from backend.app.study_guide.api.routes import make_router
from backend.app.courseware.configuration.settings import resolve_settings
from backend.app.courseware.storage.store import CoursewareStore, CoursewareConflict
from backend.app.courseware.application.pipeline import CoursewarePipeline
from backend.app.courseware.llm.client import CoursewareModelClient
from backend.app.courseware.api.routes import make_router as make_courseware_router


def create_app(settings=None, pipeline_factory=None, courseware_factory=None, practice_factory=None):
    settings = settings or default_settings
    store = Store(settings.data_dir / "agent.sqlite")
    pipeline = (
        pipeline_factory(settings, store)
        if pipeline_factory
        else Pipeline(
            settings,
            store,
            FastGPTRetriever(settings),
            ModelClient(settings),
            DocumentEngine(settings=settings),
        )
    )

    courseware_settings = resolve_settings(settings)
    courseware_store = CoursewareStore(settings.data_dir / "courseware" / "agent.sqlite")
    courseware_pipeline = (
        courseware_factory(courseware_settings, courseware_store)
        if courseware_factory
        else CoursewarePipeline(
            courseware_settings, courseware_store,
            FastGPTRetriever(courseware_settings), CoursewareModelClient(courseware_settings),
        )
    )

    from backend.app.timed_practice.api.routes import make_router as make_practice_router
    from backend.app.timed_practice.storage.store import PracticeConflict
    practice_router, practice_store = make_practice_router(settings, practice_factory)

    @asynccontextmanager
    async def lifespan(app):
        practice_store.recover_jobs()
        store.recover_jobs()
        courseware_store.recover_jobs()
        yield

    app = FastAPI(title="启鸣 AI · 化学导学案", lifespan=lifespan)
    app.state.store = store
    app.state.pipeline = pipeline
    app.state.practice_store = practice_store
    app.state.courseware_store = courseware_store

    @app.exception_handler(KeyError)
    async def missing(request: Request, exc: KeyError):
        return JSONResponse({"detail": "记录或文件不存在"}, status_code=404)

    @app.exception_handler(PracticeConflict)
    @app.exception_handler(Conflict)
    async def conflict(request: Request, exc: Conflict):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(CoursewareConflict)
    async def courseware_conflict(request: Request, exc: CoursewareConflict):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def invalid(request: Request, exc: ValueError):
        return JSONResponse(
            {"detail": settings.redact(str(exc))[:2000]}, status_code=400
        )

    app.include_router(practice_router)
    app.include_router(make_router(settings, store, pipeline))
    app.include_router(make_courseware_router(courseware_settings, courseware_store, courseware_pipeline))
    dist = Path(__file__).resolve().parents[2] / "frontend/dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/")
    def index():
        if (dist / "index.html").is_file():
            return FileResponse(dist / "index.html")
        return JSONResponse(
            {
                "message": "请先运行 npm --prefix frontend run build，或访问开发服务器 http://127.0.0.1:5173"
            }
        )

    return app


app = create_app()
