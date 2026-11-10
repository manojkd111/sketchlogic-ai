from __future__ import annotations

import copy
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from sketchlogic_eval.cli import main, score_dataset
from sketchlogic_eval.metrics import aggregate, calibration, match_nodes, score_sample
from sketchlogic_eval.predict import predict_via_api
from sketchlogic_eval.schema import REPO_ROOT

PROV = {"origin": "imported", "locked": False}


def node(nid: str, label: str, group: str | None = None, bbox: Any = None) -> dict[str, Any]:
    n: dict[str, Any] = {"id": nid, "label": label, "kind": "service", "group_id": group}
    if bbox:
        n["source_bbox"] = dict(zip(("x", "y", "width", "height"), bbox, strict=True))
    return n


def edge(eid: str, s: str, t: str, **kw: Any) -> dict[str, Any]:
    return {"id": eid, "source": s, "target": t, **kw}


def doc(nodes: list[Any], edges: list[Any], groups: list[Any] | None = None) -> dict[str, Any]:
    return {"id": "g", "nodes": nodes, "edges": edges, "groups": groups or []}


GOLD = doc(
    [
        node("a", "User", bbox=(0.0, 0.4, 0.1, 0.1)),
        node("b", "Orders API", "g1", bbox=(0.3, 0.4, 0.15, 0.1)),
        node("c", "Orders DB", "g1", bbox=(0.6, 0.4, 0.15, 0.1)),
    ],
    [
        edge("e1", "a", "b", label="HTTPS"),
        edge("e2", "b", "c", label="SQL", direction="bidirectional"),
    ],
    [{"id": "g1", "label": "Private subnet"}],
)


def test_perfect_prediction() -> None:
    s = score_sample(GOLD, copy.deepcopy(GOLD))
    r = aggregate([s])
    assert r["schema_validity"] == 1.0
    assert r["nodes"]["f1"] == r["edges"]["f1"] == 1.0
    assert r["edge_label_accuracy"] == r["group_accuracy"] == 1.0
    assert r["inferred_calibration"] is None
    assert r["evidence_confusion"] == {"observed->observed": 2}


def test_missing_and_invalid_predictions_count_as_empty() -> None:
    missing = score_sample(GOLD, None)
    invalid = score_sample(GOLD, {**copy.deepcopy(GOLD), "render": "<script>"})
    broken = copy.deepcopy(GOLD)
    broken["edges"][0]["target"] = "nope"
    dangling = score_sample(GOLD, broken)
    for s in (missing, invalid, dangling):
        assert not s.valid and s.errors
        assert (s.nodes.tp, s.nodes.fn, s.edges.fn) == (0, 3, 2)
    assert any("not a known node" in e for e in dangling.errors)
    assert aggregate([missing, score_sample(GOLD, GOLD)])["schema_validity"] == 0.5


def test_label_normalisation_fuzzy_matching_and_bbox_rescue() -> None:
    pred = doc(
        [
            node("x", "user"),
            node("y", "orders-api."),
            node("z", "Ord. D8", bbox=(0.61, 0.41, 0.15, 0.1)),  # misspelt, same place
        ],
        [],
    )
    assert match_nodes(GOLD["nodes"], pred["nodes"]) == {"x": "a", "y": "b", "z": "c"}
    far = doc([node("z", "Ord. D8", bbox=(0.0, 0.0, 0.05, 0.05))], [])
    assert match_nodes(GOLD["nodes"], far["nodes"]) == {}


def test_matching_is_one_to_one() -> None:
    pred = doc([node("p1", "User"), node("p2", "User")], [])
    s = score_sample(GOLD, pred)
    assert (s.nodes.tp, s.nodes.fp, s.nodes.fn) == (1, 1, 2)


def test_edge_direction_rules() -> None:
    pred = copy.deepcopy(GOLD)
    pred["edges"] = [
        edge("r1", "b", "a", label="HTTPS"),  # forward edge reversed -> wrong
        edge("r2", "c", "b", label="SQL"),  # gold is bidirectional -> either way matches
    ]
    s = score_sample(GOLD, pred)
    assert (s.edges.tp, s.edges.fp, s.edges.fn) == (1, 1, 1)


def test_edge_labels_and_groups() -> None:
    pred = copy.deepcopy(GOLD)
    pred["edges"][0]["label"] = "gRPC"
    pred["groups"][0]["label"] = "Public subnet"
    s = score_sample(GOLD, pred)
    assert (s.labels_correct, s.labels_total) == (1, 2)
    assert (s.groups_correct, s.groups_total) == (1, 3)  # only the ungrouped "User" agrees


def test_inferred_calibration_and_evidence_confusion() -> None:
    pred = copy.deepcopy(GOLD)
    pred["edges"][1].update(evidence="inferred", confidence=0.9)  # correct, confident
    pred["edges"].append(edge("e9", "a", "c", evidence="inferred", confidence=0.3))  # wrong
    s = score_sample(GOLD, pred)
    assert sorted(s.inferred) == [(0.3, False), (0.9, True)]
    cal = calibration(s.inferred)
    assert cal is not None and cal["count"] == 2
    assert cal["ece"] == pytest.approx((abs(0 - 0.3) + abs(1 - 0.9)) / 2)
    assert aggregate([s])["evidence_confusion"] == {
        "observed->inferred": 1,
        "observed->observed": 1,
    }


# Datasets and CLI ----------------------------------------------------------------------------


def _full(d: dict[str, Any]) -> dict[str, Any]:
    """Fill the defaults a real backend document would carry, so it passes the JSON Schema."""
    out = copy.deepcopy(d)
    out.update(schema_version="1.0", title="t", metadata={"created_at": "2026-11-08T00:00:00Z"})
    for n in out["nodes"]:
        n.setdefault("confidence", 1.0)
        n["provenance"] = PROV
    for e in out["edges"]:
        e.update(evidence=e.get("evidence", "observed"), provenance=PROV)
    for g in out["groups"]:
        g["provenance"] = PROV
    return out


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    (tmp_path / "graphs").mkdir()
    (tmp_path / "images").mkdir()
    rows = []
    for i, split in enumerate(["test", "test", "train"]):
        sid = f"s{i}"
        (tmp_path / "graphs" / f"{sid}.json").write_text(json.dumps(_full(GOLD)), encoding="utf-8")
        (tmp_path / "images" / f"{sid}.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
        rows.append(
            {"id": sid, "image": f"images/{sid}.png", "graph": f"graphs/{sid}.json", "split": split}
        )
    (tmp_path / "manifest.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    return tmp_path / "manifest.jsonl"


def test_score_dataset_handles_good_missing_and_garbage(dataset: Path, tmp_path: Path) -> None:
    preds = tmp_path / "preds"
    preds.mkdir()
    (preds / "s0.json").write_text(json.dumps(_full(GOLD)), encoding="utf-8")
    (preds / "s2.json").write_text("{not json", encoding="utf-8")
    report, samples = score_dataset(dataset, preds)
    assert report["samples"] == 3 and report["schema_validity"] == pytest.approx(1 / 3, abs=1e-3)
    assert [s["valid"] for s in samples] == [True, False, False]
    report_test, _ = score_dataset(dataset, preds, split="test")
    assert report_test["samples"] == 2


def test_cli_score_writes_report_and_prints_summary(
    dataset: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    preds = tmp_path / "preds"
    preds.mkdir()
    for sid in ("s0", "s1"):
        (preds / f"{sid}.json").write_text(json.dumps(_full(GOLD)), encoding="utf-8")
    out = tmp_path / "report.json"
    main(["score", "--manifest", str(dataset), "--predictions", str(preds), "--split", "test",
          "--name", "unit", "--report", str(out)])  # fmt: skip
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["name"] == "unit" and report["summary"]["edges"]["f1"] == 1.0
    printed = capsys.readouterr().out
    assert "Schema validity" in printed and "100.0%" in printed


# Prediction client ---------------------------------------------------------------------------


@pytest.fixture
def fake_api() -> Iterator[tuple[str, list[bytes]]]:
    bodies: list[bytes] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            bodies.append(body)
            if self.path == "/api/v1/uploads":
                payload: dict[str, Any] = {"id": "0" * 32}
            elif self.path.endswith("/extract"):
                payload = {"document": _full(GOLD)}
            else:
                self.send_response(404)
                self.end_headers()
                return
            data = json.dumps(payload).encode()
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args: Any) -> None:  # keep test output quiet
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", bodies
    finally:
        server.shutdown()


def test_predict_uploads_without_consent_and_saves_documents(
    dataset: Path, tmp_path: Path, fake_api: tuple[str, list[bytes]]
) -> None:
    url, bodies = fake_api
    out = tmp_path / "preds"
    counts = predict_via_api(dataset, out, url, split="test")
    assert counts == {"ok": 2, "failed": 0}
    assert sorted(p.name for p in out.iterdir()) == ["s0.json", "s1.json"]
    uploads = [b for b in bodies if b.startswith(b"--")]
    assert len(uploads) == 2
    assert all(b'name="training_consent"\r\n\r\nfalse' in b for b in uploads)
    report, _ = score_dataset(dataset, out, split="test")
    assert report["nodes"]["f1"] == 1.0


def test_predict_rejects_non_http_urls(dataset: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="http"):
        predict_via_api(dataset, tmp_path, "file:///etc/passwd")


def test_predict_reports_unreachable_backend(dataset: Path, tmp_path: Path) -> None:
    counts = predict_via_api(dataset, tmp_path / "p", "http://127.0.0.1:9", limit=1)
    assert counts == {"ok": 0, "failed": 1}


def test_schema_module_copies_stay_in_sync() -> None:
    """ml/ and evaluations/ can't import each other (ADR 0001); their copies must not drift."""

    def code(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        return text[text.index('"""', 3) + 3 :]  # everything after the module docstring

    ml = REPO_ROOT / "ml" / "sketchlogic_ml" / "schema.py"
    ev = REPO_ROOT / "evaluations" / "sketchlogic_eval" / "schema.py"
    assert code(ml) == code(ev)
