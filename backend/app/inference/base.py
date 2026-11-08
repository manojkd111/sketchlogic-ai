"""Inference provider interface.

All model access goes through `InferenceProvider`. Providers return a validated
`GraphDocument` (structured data) — never code. Concrete providers:

  * `mock`    — deterministic, offline; used in dev and tests (Phase 1).
  * `local`   — fine-tuned Qwen2.5-VL-3B served locally (Phase 3).
  * `bedrock` — AWS Bedrock via boto3 (Phase 4); disabled unless
                SKETCHLOGIC_AWS_ENABLED=true AND explicitly approved.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.schemas.graph import GraphDocument, SourceKind


@dataclass(frozen=True)
class ExtractionRequest:
    upload_id: str
    source_kind: SourceKind
    media_type: str
    content: bytes
    hint: str | None = None


class ProviderUnavailableError(RuntimeError):
    """Raised when a provider is not configured, disabled, or not yet implemented."""


class InferenceProvider(ABC):
    name: str

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def extract_graph(self, request: ExtractionRequest) -> GraphDocument: ...
