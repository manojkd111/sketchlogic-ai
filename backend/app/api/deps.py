from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.core.config import Settings
from app.db.repository import Database


def get_app_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_db(request: Request) -> Database:
    return cast(Database, request.app.state.db)


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
DbDep = Annotated[Database, Depends(get_db)]
