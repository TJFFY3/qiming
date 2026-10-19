from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from .config import settings as default_settings
from .store import Store, Conflict
from .retrieval import FastGPTRetriever
from .model_client import ModelClient
from .documents import DocumentEngine
from .pipeline import Pipeline
from .api import make_router


def create_app(settings=None,pipeline_factory=None):
    settings=settings or default_settings
    store=Store(settings.data_dir/'agent.sqlite')
    pipeline=pipeline_factory(settings,store) if pipeline_factory else Pipeline(settings,store,FastGPTRetriever(settings),ModelClient(settings),DocumentEngine())
    @asynccontextmanager
    async def lifespan(app):
        store.recover_jobs()
        yield
    app=FastAPI(title='启鸣 AI · 化学导学案',lifespan=lifespan)
    app.state.store=store;app.state.pipeline=pipeline
    @app.exception_handler(KeyError)
    async def missing(request:Request,exc:KeyError):return JSONResponse({'detail':'记录或文件不存在'},status_code=404)
    @app.exception_handler(Conflict)
    async def conflict(request:Request,exc:Conflict):return JSONResponse({'detail':str(exc)},status_code=409)
    @app.exception_handler(ValueError)
    async def invalid(request:Request,exc:ValueError):return JSONResponse({'detail':settings.redact(str(exc))[:2000]},status_code=400)
    app.include_router(make_router(settings,store,pipeline))
    dist=Path(__file__).resolve().parents[2]/'frontend/dist'
    if (dist/'assets').is_dir():app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/')
    def index():
        if (dist/'index.html').is_file():return FileResponse(dist/'index.html')
        return JSONResponse({'message':'请先运行 npm --prefix frontend run build，或访问开发服务器 http://127.0.0.1:5173'})
    return app

app=create_app()
