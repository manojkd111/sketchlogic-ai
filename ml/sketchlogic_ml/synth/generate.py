"""Random architecture diagrams with an exact ground-truth GraphDocument.

A sample is generated in three steps, all driven by one `random.Random(seed)` so the same seed
always gives the same graph, layout and image:

1. `random_spec`: nodes (label + kind), layers, forward edges and groups. Every node except the
   actors in layer 0 gets at least one incoming edge from an earlier layer, so the graph is
   connected and acyclic in drawing order.
2. `layout`: left-to-right layers. Groups are suffixes of the layer order ("everything from layer
   k on"), so a group's box can never contain a node that is not a member.
3. `to_document`: the gold GraphDocument. Every edge is drawn in the image, so every gold edge is
   `observed` with confidence 1.0. Node `source_bbox` is normalised to the image size.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

GENERATOR = "sketchlogic-synth/0.1.0"

ENTITIES = [
    "Orders", "Payments", "Users", "Inventory", "Search", "Auth", "Billing", "Catalog",
    "Shipping", "Notifications", "Reports", "Cart", "Profiles", "Pricing", "Reviews", "Media",
]  # fmt: skip
TEMPLATES: dict[str, list[str]] = {
    "service": ["{e} Service", "{e} API", "{e} Worker"],
    "database": ["{e} DB", "{e} Store"],
    "queue": ["{e} Queue", "{e} Events"],
    "storage": ["{e} Bucket", "{e} Cache"],
    "component": ["{e} UI", "{e} Module"],
}
ACTORS = ["User", "Customer", "Admin", "Browser", "Mobile App", "Partner"]
EXTERNALS = ["Stripe", "SendGrid", "Twilio", "GitHub", "Auth0", "Slack"]
EDGE_LABELS = ["HTTPS", "REST", "gRPC", "SQL", "publish", "consume", "webhook", "reads", "writes"]
GROUP_LABELS = ["VPC", "Private subnet", "Backend", "Data tier", "Cluster", "Region us-east-1"]
INNER_GROUP_LABELS = ["Private subnet", "Data tier", "Workers", "Storage"]

# Weighted kinds for non-actor nodes.
KIND_WEIGHTS = [
    ("service", 5),
    ("database", 2),
    ("queue", 1),
    ("storage", 1),
    ("component", 1),
    ("external", 1),
]


@dataclass
class SpecNode:
    id: str
    label: str
    kind: str
    layer: int
    group: str | None = None  # innermost group id


@dataclass
class SpecEdge:
    source: str
    target: str
    label: str | None
    direction: str  # forward | bidirectional


@dataclass
class SpecGroup:
    id: str
    label: str
    from_layer: int
    parent: str | None


@dataclass
class Spec:
    nodes: list[SpecNode]
    edges: list[SpecEdge]
    groups: list[SpecGroup] = field(default_factory=list)


def _label_for(kind: str, rng: random.Random, used: set[str]) -> str:
    for _ in range(50):
        if kind == "actor":
            label = rng.choice(ACTORS)
        elif kind == "external":
            label = rng.choice(EXTERNALS)
        else:
            label = rng.choice(TEMPLATES[kind]).format(e=rng.choice(ENTITIES))
        if label not in used:
            used.add(label)
            return label
    label = f"{kind.title()} {len(used) + 1}"
    used.add(label)
    return label


def random_spec(rng: random.Random, min_nodes: int = 3, max_nodes: int = 10) -> Spec:
    n = rng.randint(min_nodes, max_nodes)
    n_layers = max(2, min(n - 1, rng.randint(2, 5)))
    used: set[str] = set()

    nodes: list[SpecNode] = []
    n_actors = 1 if n < 6 else rng.choice([1, 1, 2])
    for _ in range(n_actors):
        nodes.append(
            SpecNode(f"n{len(nodes) + 1}", _label_for("actor", used=used, rng=rng), "actor", 0)
        )
    kinds, weights = zip(*KIND_WEIGHTS, strict=True)
    for i in range(n - n_actors):
        # First fill every layer once, then spread the rest at random.
        layer = 1 + i if i < n_layers - 1 else rng.randint(1, n_layers - 1)
        kind = rng.choices(kinds, weights)[0]
        nodes.append(SpecNode(f"n{len(nodes) + 1}", _label_for(kind, rng, used), kind, layer))

    edges: list[SpecEdge] = []
    pairs: set[tuple[str, str]] = set()

    def add(src: SpecNode, dst: SpecNode) -> None:
        if (src.id, dst.id) in pairs or (dst.id, src.id) in pairs:
            return
        pairs.add((src.id, dst.id))
        label = rng.choice(EDGE_LABELS) if rng.random() < 0.45 else None
        direction = "bidirectional" if rng.random() < 0.1 else "forward"
        edges.append(SpecEdge(src.id, dst.id, label, direction))

    for node in nodes:
        if node.layer == 0:
            continue
        earlier = [m for m in nodes if m.layer < node.layer]
        # Prefer the previous layer so edges stay short and readable.
        prev = [m for m in earlier if m.layer == node.layer - 1] or earlier
        add(rng.choice(prev), node)
    # Extra edges only between adjacent layers: a straight line that skips a layer can pass
    # through a box, and the image would no longer match the gold graph unambiguously.
    for _ in range(rng.randint(0, max(1, n // 3))):
        a, b = rng.sample(nodes, 2)
        if abs(a.layer - b.layer) == 1:
            add(*sorted((a, b), key=lambda m: m.layer))

    groups: list[SpecGroup] = []
    if n_layers >= 3 and rng.random() < 0.6:
        outer_from = rng.randint(1, n_layers - 1)
        groups.append(SpecGroup("g1", rng.choice(GROUP_LABELS), outer_from, None))
        if outer_from + 1 < n_layers and rng.random() < 0.35:
            inner = rng.choice([x for x in INNER_GROUP_LABELS if x != groups[0].label])
            groups.append(SpecGroup("g2", inner, rng.randint(outer_from + 1, n_layers - 1), "g1"))
    for node in nodes:
        for g in groups:  # later (inner) groups win
            if node.layer >= g.from_layer:
                node.group = g.id
    return Spec(nodes, edges, groups)


# --- layout --------------------------------------------------------------------------------------

Box = tuple[float, float, float, float]  # x, y, width, height (pixels)

NODE_H = 64
COL_GAP = 150
ROW_GAP = 46
MARGIN = 60
GROUP_PAD = 26
GROUP_HEADER = 30


@dataclass
class Layout:
    width: int
    height: int
    nodes: dict[str, Box]
    groups: dict[str, Box]


def layout(spec: Spec, node_width: dict[str, float], rng: random.Random) -> Layout:
    n_layers = max(n.layer for n in spec.nodes) + 1
    by_layer = [[n for n in spec.nodes if n.layer == i] for i in range(n_layers)]
    col_w = [max((node_width[n.id] for n in col), default=0.0) for col in by_layer]

    # Depth of group nesting at each layer adds room for the frame on both sides.
    def depth(layer: int) -> int:
        return sum(1 for g in spec.groups if layer >= g.from_layer)

    x = float(MARGIN)
    col_x: list[float] = []
    for i, w in enumerate(col_w):
        entering = depth(i) - (depth(i - 1) if i else 0)
        x += entering * (GROUP_PAD + 8)
        col_x.append(x)
        x += w + COL_GAP
    width = x - COL_GAP + MARGIN + depth(n_layers - 1) * GROUP_PAD

    tallest = max(len(col) for col in by_layer)
    top = MARGIN + len(spec.groups) * GROUP_HEADER + 10
    inner_h = tallest * NODE_H + (tallest - 1) * ROW_GAP
    boxes: dict[str, Box] = {}
    for i, col in enumerate(by_layer):
        col_h = len(col) * NODE_H + (len(col) - 1) * ROW_GAP
        y0 = top + (inner_h - col_h) / 2
        for j, n in enumerate(col):
            jitter_x = rng.uniform(-8, 8)
            jitter_y = rng.uniform(-6, 6)
            w = node_width[n.id]
            boxes[n.id] = (
                col_x[i] + (col_w[i] - w) / 2 + jitter_x,
                y0 + j * (NODE_H + ROW_GAP) + jitter_y,
                w,
                NODE_H,
            )

    group_boxes: dict[str, Box] = {}
    for level, g in enumerate(spec.groups):
        members = [boxes[n.id] for n in spec.nodes if n.layer >= g.from_layer]
        pad = GROUP_PAD * (len(spec.groups) - level)
        x0 = min(b[0] for b in members) - pad
        y0 = min(b[1] for b in members) - pad - GROUP_HEADER
        x1 = max(b[0] + b[2] for b in members) + pad
        y1 = max(b[1] + b[3] for b in members) + pad
        group_boxes[g.id] = (x0, y0, x1 - x0, y1 - y0)

    height = top + inner_h + MARGIN + len(spec.groups) * GROUP_PAD + 20
    return Layout(int(width), int(height), boxes, group_boxes)


# --- gold document --------------------------------------------------------------------------------


def to_document(
    spec: Spec, lay: Layout, *, sample_id: str, filename: str, created_at: str
) -> dict[str, Any]:
    def norm(b: Box) -> dict[str, float]:
        x, y, w, h = b
        return {
            "x": round(max(0.0, x / lay.width), 5),
            "y": round(max(0.0, y / lay.height), 5),
            "width": round(min(1.0, w / lay.width), 5),
            "height": round(min(1.0, h / lay.height), 5),
        }

    provenance = {"origin": "imported", "locked": False}
    return {
        "schema_version": "1.0",
        "id": sample_id,
        "title": f"Synthetic diagram {sample_id}",
        "nodes": [
            {
                "id": n.id,
                "label": n.label,
                "kind": n.kind,
                "group_id": n.group,
                "position": {"x": round(lay.nodes[n.id][0], 1), "y": round(lay.nodes[n.id][1], 1)},
                "source_bbox": norm(lay.nodes[n.id]),
                "confidence": 1.0,
                "provenance": provenance,
                "attributes": {},
            }
            for n in spec.nodes
        ],
        "edges": [
            {
                "id": f"e{i + 1}",
                "source": e.source,
                "target": e.target,
                "label": e.label,
                "direction": e.direction,
                "evidence": "observed",
                "confidence": 1.0,
                "rationale": None,
                "provenance": provenance,
            }
            for i, e in enumerate(spec.edges)
        ],
        "groups": [
            {
                "id": g.id,
                "label": g.label,
                "parent_id": g.parent,
                "confidence": 1.0,
                "provenance": provenance,
            }
            for g in spec.groups
        ],
        "metadata": {
            "source": {
                "kind": "image",
                "upload_id": None,
                "filename": filename,
                "width": lay.width,
                "height": lay.height,
            },
            "provider": "synthetic",
            "model": GENERATOR,
            "created_at": created_at,
            "warnings": [],
        },
    }
