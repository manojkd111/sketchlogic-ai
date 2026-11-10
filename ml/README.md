# ml/: training data, (later) fine-tuning and local serving

**Status:** the synthetic data generator is built. Fine-tuning and local serving are not started:
no model is downloaded, trained or run by anything in this package yet.

```powershell
cd ml
.venv\Scripts\python -m sketchlogic_ml.synth --count 200 --seed 0          # -> data/raw/synthetic/seed0-n200
.venv\Scripts\python -m sketchlogic_ml.synth --count 50 --seed 1 --val 0.2 --test 0.2 --max-nodes 14
.venv\Scripts\python -m pytest; .venv\Scripts\python -m ruff check .; .venv\Scripts\python -m mypy sketchlogic_ml
```

## Synthetic data (`sketchlogic_ml/synth/`)

Each sample is a whiteboard-style PNG plus an exact gold `GraphDocument`:

- **Graphs**: 3–10 nodes (configurable), actors on the left, services, databases, queues,
  storage, components and external systems in layers to the right. Every node after the first
  layer has an incoming edge; extra edges only join adjacent layers so no line passes through a
  box. About 45 % of edges are labelled (HTTPS, SQL, publish, …), about 10 % are bidirectional.
  60 % of graphs with three or more layers get a group, sometimes with a nested group.
- **Rendering**: wobbly marker strokes, random ink colour, stroke width, background and light
  blur; cylinders for databases, ellipses for actors, double borders for external systems,
  divided boxes for queues, dashed frames for groups.
- **Gold**: every edge is drawn, so every gold edge is `observed` with confidence 1.0. Nodes carry
  `source_bbox` (normalised to the image) and pixel `position`. Every document is validated
  against `shared/schemas/graph.v1.json` (+ integrity rules) before it is written.
- **Determinism**: the same `--seed` and `--count` produce identical images and JSON.

Output layout (`data/` is git-ignored):

```
data/raw/synthetic/<name>/
  images/<id>.png
  graphs/<id>.json
  manifest.jsonl   # {id, image, graph, split, source: "synthetic", generator, seed, created}
```

Splits are derived from a hash of the sample id, so they are stable when you generate more data.

## Planned (not started; needs an explicit go-ahead)

| Path | Purpose |
| --- | --- |
| `configs/` | LoRA/QLoRA configs for `Qwen/Qwen2.5-VL-3B-Instruct` (Unsloth + PEFT + TRL SFT) |
| `sketchlogic_ml/data/` | Turn manifests into chat-format SFT samples |
| `sketchlogic_ml/train.py` | Fine-tuning entry point |
| `sketchlogic_ml/serve.py` | Local inference used by the backend `local` provider |
| `outputs/`, `checkpoints/` | Git-ignored training artifacts |

Contract with the backend:

- The model's target output is a JSON `GraphDocument` that validates against
  `shared/schemas/graph.v1.json`. Decoding is constrained/validated before reaching the API.
- The model never outputs executable frontend code.
- Edges the model cannot see drawn must be emitted with `"evidence": "inferred"` and
  `confidence < 1.0`.

Rules:

- Only data with recorded consent (`training_consent = 1`) or synthetic/public-licensed data
  may enter a training set. See `data/README.md`.
- Training on AWS (SageMaker/Bedrock custom models) is out of scope until explicitly approved.
- `sketchlogic_ml/schema.py` is duplicated in `evaluations/` (packages don't import each other);
  a test in `evaluations/` fails if the two drift.
