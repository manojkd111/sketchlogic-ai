from __future__ import annotations

from app.core.config import Settings
from app.inference.base import (
    ExtractionRequest,
    InferenceProvider,
    ProviderUnavailableError,
)
from app.schemas.graph import (
    Edge,
    EdgeEvidence,
    GraphDocument,
    GraphMetadata,
    Node,
    NodeKind,
    SourceInfo,
)


class MockProvider(InferenceProvider):
    """Deterministic stand-in so the pipeline is testable before a model exists."""

    name = "mock"

    def is_available(self) -> bool:
        return True

    def extract_graph(self, request: ExtractionRequest) -> GraphDocument:
        return GraphDocument(
            id=f"graph-{request.upload_id}",
            title="Mock extraction",
            nodes=[
                Node(id="n1", label="Client", kind=NodeKind.ACTOR, confidence=0.95),
                Node(id="n2", label="API", kind=NodeKind.SERVICE, confidence=0.9),
                Node(id="n3", label="Database", kind=NodeKind.DATABASE, confidence=0.9),
            ],
            edges=[
                Edge(id="e1", source="n1", target="n2", label="HTTPS", confidence=0.92),
                Edge(
                    id="e2",
                    source="n2",
                    target="n3",
                    evidence=EdgeEvidence.INFERRED,
                    confidence=0.6,
                    rationale="Adjacent boxes with no visible arrow.",
                ),
            ],
            metadata=GraphMetadata(
                source=SourceInfo(kind=request.source_kind, upload_id=request.upload_id),
                provider=self.name,
                model="mock-v0",
            ),
        )


class _NotYetImplemented(InferenceProvider):
    def is_available(self) -> bool:
        return False

    def extract_graph(self, request: ExtractionRequest) -> GraphDocument:
        raise ProviderUnavailableError(f"provider '{self.name}' is not implemented yet")


class LocalQwenProvider(_NotYetImplemented):
    name = "local"


class BedrockProvider(_NotYetImplemented):
    name = "bedrock"

    def __init__(self, settings: Settings) -> None:
        if not settings.aws_enabled:
            raise ProviderUnavailableError(
                "AWS is disabled (SKETCHLOGIC_AWS_ENABLED=false). Enabling it requires approval."
            )


def get_provider(settings: Settings) -> InferenceProvider:
    match settings.inference_provider:
        case "mock":
            return MockProvider()
        case "local":
            return LocalQwenProvider()
        case "bedrock":
            return BedrockProvider(settings)
