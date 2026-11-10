"""Compare a predicted GraphDocument with a gold one.

Matching
--------
* **Nodes** are matched one-to-one, greedily by score. Labels are normalised (case, punctuation,
  whitespace) and compared with `difflib.SequenceMatcher`. When both nodes carry a `source_bbox`,
  box IoU contributes to the score and a strong overlap can rescue a misspelled label. A pair
  needs label similarity >= 0.8, or IoU >= 0.5 with label similarity >= 0.5.
* **Edges** are compared through the node matching. A `forward` edge must point the same way;
  if either side is `bidirectional` or `none`, either orientation matches. Each gold edge can be
  matched once.

Metrics (micro-averaged over the dataset by `aggregate`)
--------------------------------------------------------
* schema validity: share of predictions that pass `shared/schemas/graph.v1.json` + integrity
  checks. Invalid or missing predictions are scored as empty (all gold counted as missed).
* node / edge precision, recall, F1.
* edge label accuracy: matched edges whose gold label is non-empty and whose labels agree.
* group accuracy: matched nodes placed in a group with the same (normalised) label, or both
  ungrouped.
* inferred-edge calibration: predicted `inferred` edges bucketed by confidence; precision per
  bucket (does a matching gold edge exist?) and expected calibration error (ECE).
* evidence confusion: for matched edges, gold evidence x predicted evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from .schema import validation_errors

LABEL_MATCH = 0.8
LABEL_MATCH_WITH_IOU = 0.5
IOU_MATCH = 0.5
CALIBRATION_BUCKETS = 5


@dataclass
class PRF:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, other: PRF) -> None:
        self.tp, self.fp, self.fn = self.tp + other.tp, self.fp + other.fp, self.fn + other.fn

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
        }


@dataclass
class SampleScore:
    valid: bool
    errors: list[str] = field(default_factory=list)
    nodes: PRF = field(default_factory=PRF)
    edges: PRF = field(default_factory=PRF)
    labels_correct: int = 0
    labels_total: int = 0
    groups_correct: int = 0
    groups_total: int = 0
    inferred: list[tuple[float, bool]] = field(default_factory=list)  # (confidence, correct)
    evidence: dict[str, int] = field(default_factory=dict)  # "gold->pred" -> count


def normalise(label: str | None) -> str:
    return " ".join(re.sub(r"[^0-9a-z]+", " ", (label or "").casefold()).split())


def label_similarity(a: str | None, b: str | None) -> float:
    na, nb = normalise(a), normalise(b)
    if not na and not nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def iou(a: dict[str, float] | None, b: dict[str, float] | None) -> float | None:
    if not a or not b:
        return None
    ix = min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"])
    iy = min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"])
    inter = max(0.0, ix) * max(0.0, iy)
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union if union > 0 else 0.0


def match_nodes(gold: list[dict[str, Any]], pred: list[dict[str, Any]]) -> dict[str, str]:
    """pred node id -> gold node id."""
    candidates: list[tuple[float, str, str]] = []
    for p in pred:
        for g in gold:
            sim = label_similarity(p.get("label"), g.get("label"))
            overlap = iou(p.get("source_bbox"), g.get("source_bbox"))
            ok = sim >= LABEL_MATCH or (
                overlap is not None and overlap >= IOU_MATCH and sim >= LABEL_MATCH_WITH_IOU
            )
            if ok:
                score = sim if overlap is None else 0.75 * sim + 0.25 * overlap
                candidates.append((score, p["id"], g["id"]))
    mapping: dict[str, str] = {}
    used_gold: set[str] = set()
    for _, pid, gid in sorted(candidates, key=lambda c: (-c[0], c[1], c[2])):
        if pid not in mapping and gid not in used_gold:
            mapping[pid] = gid
            used_gold.add(gid)
    return mapping


def _undirected(direction: str | None) -> bool:
    return direction in ("bidirectional", "none")


def _group_labels(doc: dict[str, Any]) -> dict[str, str]:
    groups = {g["id"]: normalise(g.get("label")) for g in doc.get("groups", [])}
    return {n["id"]: groups.get(n.get("group_id") or "", "") for n in doc.get("nodes", [])}


def score_sample(gold: dict[str, Any], pred: Any) -> SampleScore:
    errors = ["missing prediction"] if pred is None else validation_errors(pred)
    if errors:
        missed = SampleScore(valid=False, errors=errors[:5])
        missed.nodes.fn = len(gold.get("nodes", []))
        missed.edges.fn = len(gold.get("edges", []))
        return missed

    s = SampleScore(valid=True)
    mapping = match_nodes(gold["nodes"], pred["nodes"])
    s.nodes = PRF(
        tp=len(mapping),
        fp=len(pred["nodes"]) - len(mapping),
        fn=len(gold["nodes"]) - len(mapping),
    )

    gold_groups, pred_groups = _group_labels(gold), _group_labels(pred)
    for pid, gid in mapping.items():
        s.groups_total += 1
        s.groups_correct += int(gold_groups.get(gid, "") == pred_groups.get(pid, ""))

    unmatched = list(gold["edges"])
    for e in pred["edges"]:
        src, dst = mapping.get(e["source"]), mapping.get(e["target"])
        hit = None
        if src and dst:
            for g in unmatched:
                same_way = g["source"] == src and g["target"] == dst
                reverse = g["source"] == dst and g["target"] == src
                either_undirected = _undirected(g.get("direction")) or _undirected(
                    e.get("direction")
                )
                if same_way or (reverse and either_undirected):
                    hit = g
                    break
        if hit is not None:
            unmatched.remove(hit)
            s.edges.tp += 1
            key = f"{hit.get('evidence', 'observed')}->{e.get('evidence', 'observed')}"
            s.evidence[key] = s.evidence.get(key, 0) + 1
            if normalise(hit.get("label")):
                s.labels_total += 1
                s.labels_correct += int(label_similarity(hit.get("label"), e.get("label")) >= 0.8)
        else:
            s.edges.fp += 1
        if e.get("evidence") == "inferred":
            s.inferred.append((float(e.get("confidence", 0.0)), hit is not None))
    s.edges.fn = len(unmatched)
    return s


def calibration(points: list[tuple[float, bool]]) -> dict[str, Any] | None:
    if not points:
        return None
    width = 1.0 / CALIBRATION_BUCKETS
    buckets: list[dict[str, Any]] = []
    ece = 0.0
    for b in range(CALIBRATION_BUCKETS):
        lo, hi = b * width, (b + 1) * width
        inside = [
            (c, ok)
            for c, ok in points
            if lo <= c < hi or (b == CALIBRATION_BUCKETS - 1 and c == 1.0)
        ]
        if not inside:
            continue
        mean_conf = sum(c for c, _ in inside) / len(inside)
        precision = sum(ok for _, ok in inside) / len(inside)
        ece += len(inside) / len(points) * abs(precision - mean_conf)
        buckets.append(
            {
                "range": [round(lo, 2), round(hi, 2)],
                "count": len(inside),
                "mean_confidence": round(mean_conf, 4),
                "precision": round(precision, 4),
            }
        )
    return {"count": len(points), "ece": round(ece, 4), "buckets": buckets}


def aggregate(scores: list[SampleScore]) -> dict[str, Any]:
    nodes, edges = PRF(), PRF()
    labels = [0, 0]
    groups = [0, 0]
    inferred: list[tuple[float, bool]] = []
    evidence: dict[str, int] = {}
    for s in scores:
        nodes.add(s.nodes)
        edges.add(s.edges)
        labels[0] += s.labels_correct
        labels[1] += s.labels_total
        groups[0] += s.groups_correct
        groups[1] += s.groups_total
        inferred += s.inferred
        for k, v in s.evidence.items():
            evidence[k] = evidence.get(k, 0) + v
    valid = sum(s.valid for s in scores)
    return {
        "samples": len(scores),
        "schema_validity": round(valid / len(scores), 4) if scores else 0.0,
        "nodes": nodes.as_dict(),
        "edges": edges.as_dict(),
        "edge_label_accuracy": round(labels[0] / labels[1], 4) if labels[1] else None,
        "group_accuracy": round(groups[0] / groups[1], 4) if groups[1] else None,
        "inferred_calibration": calibration(inferred),
        "evidence_confusion": dict(sorted(evidence.items())),
    }
