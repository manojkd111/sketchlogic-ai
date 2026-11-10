from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import pytest

from sketchlogic_ml.schema import integrity_errors, validation_errors
from sketchlogic_ml.synth import generate_sample
from sketchlogic_ml.synth.cli import generate_dataset, main, split_for
from sketchlogic_ml.synth.generate import random_spec

CREATED = "2026-11-08T00:00:00+00:00"


def _png_digest(seed: int) -> tuple[str, str]:
    image, doc = generate_sample(seed, sample_id="s", created_at=CREATED)
    return hashlib.sha256(image.tobytes()).hexdigest(), json.dumps(doc, sort_keys=True)


@pytest.mark.parametrize("seed", range(40))
def test_every_gold_document_is_valid(seed: int) -> None:
    _, doc = generate_sample(seed, sample_id=f"s{seed}", created_at=CREATED)
    assert validation_errors(doc) == []


def test_same_seed_same_sample_different_seed_different_sample() -> None:
    assert _png_digest(3) == _png_digest(3)
    assert _png_digest(3) != _png_digest(4)


@pytest.mark.parametrize("seed", range(30))
def test_graph_structure(seed: int) -> None:
    spec = random_spec(random.Random(seed), 3, 10)
    assert 3 <= len(spec.nodes) <= 10
    assert spec.nodes[0].kind == "actor" and spec.nodes[0].layer == 0
    layer = {n.id: n.layer for n in spec.nodes}
    incoming = {e.target for e in spec.edges}
    # Connected in drawing order: everything after layer 0 has an incoming edge...
    assert all(n.id in incoming for n in spec.nodes if n.layer > 0)
    # ...edges point forward to the adjacent layer (no skipping, no self-loops)...
    assert all(layer[e.target] - layer[e.source] == 1 for e in spec.edges)
    # ...and there is at most one edge per node pair.
    pairs = [frozenset((e.source, e.target)) for e in spec.edges]
    assert len(pairs) == len(set(pairs))
    labels = [n.label for n in spec.nodes]
    assert len(labels) == len(set(labels))


@pytest.mark.parametrize("seed", range(30))
def test_bboxes_are_normalised_inside_the_image_and_do_not_overlap(seed: int) -> None:
    image, doc = generate_sample(seed, sample_id="s", created_at=CREATED)
    assert (image.width, image.height) == (
        doc["metadata"]["source"]["width"],
        doc["metadata"]["source"]["height"],
    )
    boxes = [n["source_bbox"] for n in doc["nodes"]]
    for b in boxes:
        assert b["x"] >= 0 and b["x"] + b["width"] <= 1
        assert b["y"] >= 0 and b["y"] + b["height"] <= 1
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            overlap_x = min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"])
            overlap_y = min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"])
            assert overlap_x <= 0 or overlap_y <= 0


def test_groups_nest_and_members_follow_layers() -> None:
    seen_nested = False
    for seed in range(200):
        spec = random_spec(random.Random(seed), 6, 12)
        if len(spec.groups) == 2:
            seen_nested = True
            outer, inner = spec.groups
            assert inner.parent == outer.id and inner.from_layer > outer.from_layer
            for n in spec.nodes:
                expected = (
                    inner.id
                    if n.layer >= inner.from_layer
                    else outer.id
                    if n.layer >= outer.from_layer
                    else None
                )
                assert n.group == expected
    assert seen_nested, "generator should sometimes produce nested groups"


def test_gold_edges_are_observed_and_certain() -> None:
    _, doc = generate_sample(11, sample_id="s", created_at=CREATED)
    assert all(e["evidence"] == "observed" and e["confidence"] == 1.0 for e in doc["edges"])
    assert doc["metadata"]["provider"] == "synthetic"


def test_integrity_checks_catch_what_json_schema_cannot() -> None:
    _, doc = generate_sample(1, sample_id="s", created_at=CREATED)
    doc["edges"][0]["target"] = "missing"
    doc["nodes"].append(dict(doc["nodes"][0]))
    errors = integrity_errors(doc)
    assert any("not a known node" in e for e in errors)
    assert any("duplicate node id" in e for e in errors)


def test_split_is_stable_and_roughly_proportional() -> None:
    assert split_for("syn-0-000001", 0.1, 0.1) == split_for("syn-0-000001", 0.1, 0.1)
    splits = [split_for(f"syn-0-{i:06d}", 0.1, 0.2) for i in range(2000)]
    assert 0.15 < splits.count("test") / 2000 < 0.25
    assert 0.06 < splits.count("val") / 2000 < 0.14


def test_dataset_writes_images_graphs_and_manifest_with_provenance(tmp_path: Path) -> None:
    out = tmp_path / "ds"
    manifest = generate_dataset(out, count=5, seed=2, created_at=CREATED)
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 5
    for row in rows:
        assert row["source"] == "synthetic" and row["created"] == CREATED
        assert row["split"] in {"train", "val", "test"}
        assert (out / row["image"]).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        doc = json.loads((out / row["graph"]).read_text(encoding="utf-8"))
        assert doc["id"] == row["id"] and validation_errors(doc) == []


def test_dataset_refuses_a_non_empty_directory(tmp_path: Path) -> None:
    (tmp_path / "keep.txt").write_text("user data", encoding="utf-8")
    with pytest.raises(FileExistsError):
        generate_dataset(tmp_path, count=1, seed=0)
    assert (tmp_path / "keep.txt").read_text(encoding="utf-8") == "user data"


def test_cli_rejects_bad_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--val", "0.6", "--test", "0.5"])
    assert "sum to less than 1" in capsys.readouterr().err
