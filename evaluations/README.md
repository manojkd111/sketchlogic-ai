# evaluations/: extraction quality benchmarks

Scores predicted `GraphDocument`s against gold ones. Works with any provider, because predictions
are collected through the backend's HTTP API exactly as the UI uses it.

```powershell
# 0. a dataset (see ml/README.md)
ml\.venv\Scripts\python -m sketchlogic_ml.synth --count 200 --seed 0

# 1. a separate backend for evaluation uploads (never your real data dir)
cd backend; $env:SKETCHLOGIC_DATA_DIR="var/eval"; .venv\Scripts\python -m uvicorn app.main:app --port 8001

# 2. predict + score (from evaluations/)
.venv\Scripts\python -m sketchlogic_eval predict --manifest ..\data\raw\synthetic\seed0-n200\manifest.jsonl `
    --api http://127.0.0.1:8001 --split test --out ..\data\interim\predictions\mock-seed0
.venv\Scripts\python -m sketchlogic_eval score --manifest ..\data\raw\synthetic\seed0-n200\manifest.jsonl `
    --predictions ..\data\interim\predictions\mock-seed0 --split test --name mock
```

`score` prints a summary and writes the full report (summary + per-sample scores) to
`results/<name>-<time>.json` (git-ignored). Evaluation uploads are always sent with
`training_consent=false`.

## Metrics

| Metric | Definition |
| --- | --- |
| Schema validity | Share of predictions that pass `shared/schemas/graph.v1.json` + integrity rules (unique ids, known references, inferred < 1.0). Invalid or missing predictions score as empty. |
| Node P / R / F1 | One-to-one greedy matching on normalised labels (`difflib` ratio ≥ 0.8), or box IoU ≥ 0.5 with label ratio ≥ 0.5 when both sides have `source_bbox`. |
| Edge P / R / F1 | Through the node matching. `forward` edges must point the same way; if either side is `bidirectional`/`none`, either orientation counts. |
| Edge label accuracy | Matched edges with a gold label whose labels agree. |
| Group accuracy | Matched nodes in a group with the same normalised label (or both ungrouped). |
| Inferred-edge calibration | Predicted `inferred` edges bucketed by confidence: precision per bucket and ECE. |
| Evidence confusion | For matched edges: gold evidence → predicted evidence counts. |

All figures are micro-averaged over the dataset.

## Baselines

| Run | Data | Node F1 | Edge F1 | Notes |
| --- | --- | --- | --- | --- |
| `mock` provider | synthetic seed 0, test split (22) | 0.0 % | 0.0 % | Fixed 3-node graph; its one inferred edge (0.6) is always wrong → ECE 0.60. Schema validity 100 %. |
| gold vs gold | synthetic seed 0 (100) | 100 % | 100 % | Harness sanity check. |

Every model or prompt change must report these numbers against a fixed test split before it is
promoted to the default provider.
