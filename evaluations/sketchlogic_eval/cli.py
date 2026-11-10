"""Evaluate extraction quality.

    # 1. collect predictions from a running backend (any provider)
    python -m sketchlogic_eval predict --manifest ../data/raw/synthetic/seed0-n200/manifest.jsonl \
        --api http://127.0.0.1:8001 --split test --out predictions/mock
    # 2. score them against the gold graphs
    python -m sketchlogic_eval score --manifest ../data/raw/synthetic/seed0-n200/manifest.jsonl \
        --predictions predictions/mock --split test --name mock

`score` prints a summary and writes the full report to evaluations/results/ (git-ignored).
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .metrics import aggregate, score_sample
from .predict import predict_via_api, read_manifest
from .schema import REPO_ROOT

RESULTS_DIR = REPO_ROOT / "evaluations" / "results"


def score_dataset(
    manifest: Path, predictions: Path, *, split: str | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    per_sample: list[dict[str, Any]] = []
    scores = []
    for row in read_manifest(manifest, split):
        gold = json.loads((manifest.parent / row["graph"]).read_text(encoding="utf-8"))
        pred_path = predictions / f"{row['id']}.json"
        try:
            pred = json.loads(pred_path.read_text(encoding="utf-8")) if pred_path.exists() else None
        except json.JSONDecodeError:
            pred = "<not JSON>"  # scored as invalid
        s = score_sample(gold, pred)
        scores.append(s)
        per_sample.append(
            {
                "id": row["id"],
                "valid": s.valid,
                "errors": s.errors,
                "node_f1": round(s.nodes.f1, 4),
                "edge_f1": round(s.edges.f1, 4),
            }
        )
    return aggregate(scores), per_sample


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def summary_table(report: dict[str, Any]) -> str:
    n, e = report["nodes"], report["edges"]
    cal = report["inferred_calibration"]
    rows = [
        ("Samples", str(report["samples"])),
        ("Schema validity", _pct(report["schema_validity"])),
        ("Node P / R / F1", f"{_pct(n['precision'])} / {_pct(n['recall'])} / {_pct(n['f1'])}"),
        ("Edge P / R / F1", f"{_pct(e['precision'])} / {_pct(e['recall'])} / {_pct(e['f1'])}"),
        ("Edge label accuracy", _pct(report["edge_label_accuracy"])),
        ("Group accuracy", _pct(report["group_accuracy"])),
        (
            "Inferred edges (ECE)",
            "none predicted" if cal is None else f"{cal['count']} (ECE {cal['ece']:.3f})",
        ),
    ]
    width = max(len(k) for k, _ in rows)
    return "\n".join(f"{k.ljust(width)}  {v}" for k, v in rows)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="sketchlogic-eval", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("predict", help="collect predictions from a running backend")
    pr.add_argument("--manifest", type=Path, required=True)
    pr.add_argument("--api", default="http://127.0.0.1:8000")
    pr.add_argument("--out", type=Path, required=True)
    pr.add_argument("--split")
    pr.add_argument("--limit", type=int)

    sc = sub.add_parser("score", help="score predictions against gold")
    sc.add_argument("--manifest", type=Path, required=True)
    sc.add_argument("--predictions", type=Path, required=True)
    sc.add_argument("--split")
    sc.add_argument("--name", default="run")
    sc.add_argument("--report", type=Path, help="default: evaluations/results/<name>-<time>.json")

    args = p.parse_args(argv)
    if args.cmd == "predict":
        counts = predict_via_api(
            args.manifest, args.out, args.api, split=args.split, limit=args.limit
        )
        print(f"Predictions: {counts['ok']} saved to {args.out}, {counts['failed']} failed")
        return

    report, per_sample = score_dataset(args.manifest, args.predictions, split=args.split)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = args.report or RESULTS_DIR / f"{args.name}-{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    full = {
        "name": args.name,
        "created": stamp,
        "manifest": str(args.manifest),
        "predictions": str(args.predictions),
        "split": args.split,
        "summary": report,
        "samples": per_sample,
    }
    out.write_text(json.dumps(full, indent=2) + "\n", encoding="utf-8")
    print(summary_table(report))
    print(f"\nReport: {out}")
