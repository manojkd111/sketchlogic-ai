from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.api.deps import DbDep, SettingsDep
from app.schemas.graph import CURRENT_SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    graph_schema_version: str
    supported_schema_versions: list[str]
    database: Literal["ok", "unavailable"]
    inference_provider: str
    aws_enabled: bool


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDep, db: DbDep) -> HealthResponse:
    db_ok = db.ping()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        version=__version__,
        environment=settings.environment,
        graph_schema_version=CURRENT_SCHEMA_VERSION,
        supported_schema_versions=list(SUPPORTED_SCHEMA_VERSIONS),
        database="ok" if db_ok else "unavailable",
        inference_provider=settings.inference_provider,
        aws_enabled=settings.aws_enabled,
    )
