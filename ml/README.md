# ml/ — model training and local inference

**Status: placeholder (Phase 1).** No training code runs in Phase 1.

Planned (Phase 3):

| Path | Purpose |
| --- | --- |
| `configs/` | LoRA/QLoRA configs for `Qwen/Qwen2.5-VL-3B-Instruct` (Unsloth + PEFT + TRL SFT) |
| `sketchlogic_ml/data/` | Dataset builders that turn `data/processed/` into chat-format SFT samples |
| `sketchlogic_ml/train.py` | Fine-tuning entry point (Unsloth `FastVisionModel`, TRL `SFTTrainer`) |
| `sketchlogic_ml/serve.py` | Local inference used by the backend `local` provider |
| `outputs/`, `checkpoints/` | Git-ignored training artifacts |

Contract with the backend:

- The model's target output is a JSON `GraphDocument` that validates against
  `shared/schemas/graph.v1.json`. Training targets are generated from that schema, not
  free-form text, and decoding is constrained/validated before reaching the API.
- The model never outputs executable frontend code.
- Edges the model cannot see drawn must be emitted with `"evidence": "inferred"` and
  `confidence < 1.0`.

Rules:

- Only data with recorded consent (`training_consent = 1`) or synthetic/public-licensed data
  may enter a training set. See `data/README.md`.
- Training on AWS (SageMaker/Bedrock custom models) is out of scope until explicitly
  approved.
