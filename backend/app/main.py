from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import graphs, health, uploads
from app.core.config import Settings, get_settings
from app.db.repository import Database
from app.services.graph_store import GraphStoreError
from app.services.upload_validation import UploadValidationError

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.resolved_data_dir.mkdir(parents=True, exist_ok=True)
        app.state.settings = settings
        app.state.db = Database(settings.database_path)
        yield

    app = FastAPI(
        title="SketchLogic AI API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    @app.exception_handler(UploadValidationError)
    async def _upload_error(_: Request, exc: UploadValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"valid": False, "error": {"code": exc.code.value, "message": exc.message}},
        )

    @app.exception_handler(GraphStoreError)
    async def _graph_error(_: Request, exc: GraphStoreError) -> JSONResponse:
        error: dict[str, object] = {"code": exc.code.value, "message": exc.message}
        if exc.current_version is not None:
            error["current_version"] = exc.current_version
        return JSONResponse(status_code=exc.status_code, content={"error": error})

    for r in (health.router, uploads.router, graphs.router):
        app.include_router(r, prefix=API_PREFIX)
    return app


app = create_app()
