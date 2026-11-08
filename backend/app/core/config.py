"""Runtime settings, loaded from environment variables prefixed `SKETCHLOGIC_` (or backend/.env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SKETCHLOGIC_", env_file=BACKEND_ROOT / ".env", extra="ignore"
    )

    environment: Literal["development", "test", "production"] = "development"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    # Storage (SQLite MVP). Relative paths resolve against backend/.
    data_dir: Path = Path("var")
    database_filename: str = "sketchlogic.db"

    # Upload limits.
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_image_pixels: int = Field(default=40_000_000, gt=0)  # ~ 8k x 5k
    min_image_side: int = Field(default=32, gt=0)
    max_image_side: int = Field(default=12_000, gt=0)
    max_xlsx_uncompressed_bytes: int = Field(default=100 * 1024 * 1024, gt=0)

    # Inference. AWS is disabled by default and must be explicitly enabled.
    inference_provider: Literal["mock", "local", "bedrock"] = "mock"
    aws_enabled: bool = False
    aws_region: str | None = None

    @model_validator(mode="after")
    def _bedrock_requires_explicit_opt_in(self) -> Settings:
        if self.inference_provider == "bedrock" and not self.aws_enabled:
            raise ValueError(
                "inference_provider='bedrock' requires SKETCHLOGIC_AWS_ENABLED=true "
                "(AWS operations are disabled by default)"
            )
        return self

    @property
    def resolved_data_dir(self) -> Path:
        p = self.data_dir
        return p if p.is_absolute() else BACKEND_ROOT / p

    @property
    def uploads_dir(self) -> Path:
        return self.resolved_data_dir / "uploads"

    @property
    def database_path(self) -> Path:
        return self.resolved_data_dir / self.database_filename


@lru_cache
def get_settings() -> Settings:
    return Settings()
