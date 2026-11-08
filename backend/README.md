# SketchLogic backend (FastAPI)

Python 3.11+ API: health, upload validation/storage, and the versioned graph schema.

```powershell
# Windows (PowerShell), from backend/
uv venv --python 3.12 .venv
uv pip install --python .venv -e ".[dev]"
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

```bash
# WSL2 / Linux / macOS, from backend/
uv venv --python 3.12 .venv && uv pip install --python .venv -e ".[dev]"
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Interactive API docs: http://127.0.0.1:8000/docs

## Checks

```bash
python -m pytest            # all tests
python -m pytest -m smoke   # smoke tests only
python -m ruff check . && python -m ruff format --check .
python -m mypy app
python -m scripts.export_schema   # regenerate ../shared/schemas/graph.v1.json
```

## Layout

| Path | Purpose |
| --- | --- |
| `app/main.py` | App factory (`create_app`), CORS, error handlers |
| `app/core/config.py` | `SKETCHLOGIC_*` environment settings |
| `app/api/routes/` | `health`, `uploads`, `graphs` routers under `/api/v1` |
| `app/schemas/graph/v1.py` | **Versioned graph schema** (source of truth) |
| `app/services/upload_validation.py` | Magic-byte sniffing, Pillow decode, XLSX/zip-bomb checks |
| `app/services/graph_ops.py` | NetworkX conversion and summaries |
| `app/inference/` | Provider interface (`mock` now; `local`, `bedrock` later) |
| `app/db/repository.py` | SQLite (stdlib) with `user_version` migrations |
| `var/` | Runtime data (DB + uploads). Git-ignored. Never used for training. |
