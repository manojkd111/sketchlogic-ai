"""Generate a synthetic dataset.

    python -m sketchlogic_ml.synth --count 200 --seed 0
    python -m sketchlogic_ml.synth --count 50 --out ../data/raw/synthetic/smoke --val 0.2 --test 0.2

Writes `images/<id>.png`, `graphs/<id>.json` and `manifest.jsonl` (one line per sample with its
split and provenance, as required by data/README.md). Every gold document is validated against
`shared/schemas/graph.v1.json` before it is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from ..schema import REPO_ROOT, validation_errors
from . import GENERATOR, generate_sample


def split_for(sample_id: str, val: float, test: float) -> str:
    """Stable split from the id alone, so adding samples never reshuffles existing ones."""
    bucket = int(hashlib.sha256(sample_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    if bucket < test:
        return "test"
    if bucket < test + val:
        return "val"
    return "train"


def generate_dataset(
    out: Path,
    *,
    count: int,
    seed: int,
    val: float = 0.1,
    test: float = 0.1,
    min_nodes: int = 3,
    max_nodes: int = 10,
    created_at: str | None = None,
) -> Path:
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"{out} is not empty; choose a new --out directory")
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "graphs").mkdir(parents=True, exist_ok=True)
    created = created_at or datetime.now(UTC).replace(microsecond=0).isoformat()

    lines: list[str] = []
    for i in range(count):
        sample_id = f"syn-{seed}-{i:06d}"
        sample_seed = seed * 1_000_003 + i
        image, doc = generate_sample(
            sample_seed,
            sample_id=sample_id,
            created_at=created,
            min_nodes=min_nodes,
            max_nodes=max_nodes,
        )
        errors = validation_errors(doc)
        if errors:  # a generator bug; never write invalid gold data
            raise ValueError(f"{sample_id}: generated an invalid GraphDocument: {errors[:3]}")
        image.save(out / "images" / f"{sample_id}.png", optimize=True)
        (out / "graphs" / f"{sample_id}.json").write_text(
            json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        lines.append(
            json.dumps(
                {
                    "id": sample_id,
                    "image": f"images/{sample_id}.png",
                    "graph": f"graphs/{sample_id}.json",
                    "split": split_for(sample_id, val, test),
                    "source": "synthetic",
                    "generator": GENERATOR,
                    "seed": sample_seed,
                    "created": created,
                }
            )
        )
    manifest = out / "manifest.jsonl"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="sketchlogic-synth", description=__doc__.split("\n\n")[0])
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path, help="default: data/raw/synthetic/seed<seed>-n<count>")
    p.add_argument("--val", type=float, default=0.1)
    p.add_argument("--test", type=float, default=0.1)
    p.add_argument("--min-nodes", type=int, default=3)
    p.add_argument("--max-nodes", type=int, default=10)
    args = p.parse_args(argv)
    if args.val < 0 or args.test < 0 or args.val + args.test >= 1:
        p.error("--val and --test must be >= 0 and sum to less than 1")
    if not (2 <= args.min_nodes <= args.max_nodes <= 60):
        p.error("need 2 <= --min-nodes <= --max-nodes <= 60")

    out = args.out or REPO_ROOT / "data" / "raw" / "synthetic" / f"seed{args.seed}-n{args.count}"
    manifest = generate_dataset(
        out,
        count=args.count,
        seed=args.seed,
        val=args.val,
        test=args.test,
        min_nodes=args.min_nodes,
        max_nodes=args.max_nodes,
    )
    splits: dict[str, int] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        s = json.loads(line)["split"]
        splits[s] = splits.get(s, 0) + 1
    counts = ", ".join(f"{k}={v}" for k, v in sorted(splits.items()))
    print(f"Wrote {args.count} samples to {out} ({counts})")
