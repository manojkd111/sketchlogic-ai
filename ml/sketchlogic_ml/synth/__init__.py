"""Synthetic whiteboard diagrams paired with exact ground-truth GraphDocuments."""

from __future__ import annotations

import random
from typing import Any

from PIL import Image

from .generate import GENERATOR, layout, random_spec, to_document
from .render import node_widths, render

__all__ = ["GENERATOR", "generate_sample"]


def generate_sample(
    seed: int, *, sample_id: str, created_at: str, min_nodes: int = 3, max_nodes: int = 10
) -> tuple[Image.Image, dict[str, Any]]:
    """One (image, gold GraphDocument) pair. Same arguments -> identical output."""
    rng = random.Random(seed)
    spec = random_spec(rng, min_nodes, max_nodes)
    lay = layout(spec, node_widths(spec), rng)
    image = render(spec, lay, rng)
    doc = to_document(
        spec, lay, sample_id=sample_id, filename=f"{sample_id}.png", created_at=created_at
    )
    return image, doc
