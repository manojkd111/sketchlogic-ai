# CLAUDE.md: SketchLogic AI

SketchLogic converts whiteboard photos, hand-drawn flows, spreadsheet screenshots and `.xlsx` files
into clean, editable architecture/process diagrams. **Current phase: 2 (editor & sketch canvas) complete; 3 (AI extraction) next.**
See `docs/roadmap.md` for what comes next. Don't start model training or AWS work unless asked.

## Repo map

| Path | What | Toolchain |
| --- | --- | --- |
| `frontend/` | Next.js 16 App Router, React 19, Tailwind 4 | npm, Vitest, ESLint, Prettier |
| `backend/` | FastAPI + Pydantic v2 API, SQLite, NetworkX | uv venv (`backend/.venv`), pytest, ruff, mypy |
| `shared/` | `schemas/graph.v1.json` (generated), `examples/*.graph.json` | — |
| `ml/` | (Phase 3) Qwen2.5-VL-3B fine-tuning (Unsloth/PEFT/TRL) + local serving | — |
| `data/` | Datasets; contents git-ignored; consent policy in README | — |
| `evaluations/` | Extraction metrics & results | — |
| `docs/` | `architecture.md`, `graph-schema.md`, `setup-windows-wsl.md`, `roadmap.md`, `adr/` | — |
| `scripts/` | `setup`, `dev`, `check` in `.ps1` (Windows) and `.sh` (WSL/Linux) | — |

Packages don't import each other. They share data only through `shared/` and the HTTP API.

## Commands

```powershell
.\scripts\check.ps1                                   # everything CI runs (./scripts/check.sh on Linux)
cd backend;  .venv\Scripts\python -m pytest           # backend tests (-m smoke for smoke only)
             .venv\Scripts\python -m ruff check . ; .venv\Scripts\python -m ruff format .
             .venv\Scripts\python -m mypy app scripts
             .venv\Scripts\python -m scripts.export_schema   # after ANY schema change
cd frontend; npm test; npm run typecheck; npm run lint; npm run format; npm run build
             npm run e2e     # Playwright; reuses running dev servers locally
                             # (PLAYWRIGHT_CHANNEL=chrome to use installed Chrome)
```

On Windows, uv may need `UV_SYSTEM_CERTS=1` (HTTPS inspection on this machine).

## Hard rules (product invariants)

1. **AI outputs structured data, never code.** Providers return a `GraphDocument` (or, later,
   structured patch ops) that is re-validated by Pydantic with `extra="forbid"`. Never `eval`,
   `dangerouslySetInnerHTML`, or render model output as JSX/HTML/Mermaid-to-DOM without
   sanitising it.
2. **Observed vs inferred.** Every edge has `evidence: observed | inferred`. Inferred edges need
   `confidence < 1.0` and should carry a `rationale`. The UI must show them differently and let
   users accept or reject them.
3. **Never overwrite manual corrections.** User edits set `provenance.origin = "user_corrected"`,
   which forces `locked = true`. Automated changes (AI modifications, re-extraction, auto-layout
   of pinned positions) to locked elements must be proposed and need user approval, not applied.
4. **Privacy.** `training_consent` defaults to false. Uploads under `backend/var/` are never copied
   into `data/` or any training set without it. Don't add telemetry that ships user diagrams.
5. **AWS is off by default.** `SKETCHLOGIC_AWS_ENABLED=false`; `inference_provider=bedrock` is
   rejected at startup unless it is true. Don't run boto3 or any AWS CLI command, deploy, or create
   cloud resources without explicit approval in the current conversation.
6. **Model access only through `app/inference/`** (`InferenceProvider`). Routes and UI never call a
   model SDK directly.

## Schema conventions

- Source of truth: `backend/app/schemas/graph/v1.py`. Import from `app.schemas.graph`.
- Additive optional field → minor version. Breaking change → new `v2.py`, new JSON file, migration
  and tests. Never change the meaning of an existing field. Details in `docs/graph-schema.md`.
- After changing the schema: run `export_schema`, update `frontend/src/lib/graph-schema.ts`. The
  drift tests (`test_shared_json_schema_is_up_to_date`, `graph-schema.test.ts`) must pass.

## Backend conventions

- App factory `create_app(settings)` in `app/main.py`; tests build their own app with a temp
  `data_dir`. Don't rely on the module-level `app` in tests.
- Settings come only from `app/core/config.py` (`SKETCHLOGIC_*` env vars); no `os.environ` elsewhere.
- Routes live in `app/api/routes/`, mounted under `/api/v1`. Business logic goes in
  `app/services/`. Persistence goes in `app/db/`.
- Upload errors raise `UploadValidationError(ErrorCode.X, msg, status_code=...)` and produce
  `{"valid": false, "error": {code, message}}`. Add new codes to the `ErrorCode` enum and the TS client.
- Trust only magic bytes and full decodes, never filename or Content-Type.
- DB migrations: append to `_MIGRATIONS` in `app/db/repository.py`; never edit an applied one.
- Style: ruff (line length 100), mypy strict, type hints everywhere, `from __future__ import annotations`.

## Frontend conventions

- **Next.js 16 is newer than most training data.** Read `frontend/node_modules/next/dist/docs/`
  before using unfamiliar APIs (see `frontend/AGENTS.md`). `cacheComponents` is enabled.
- Interactive components are `"use client"` in `src/components/`; pages stay server components.
- All backend calls go through `src/lib/api.ts` (base URL from `NEXT_PUBLIC_API_BASE_URL`).
- Client-side upload checks (`src/lib/upload-rules.ts`) are only for UX. The backend decides.
- Tests sit next to the code as `*.test.ts(x)`. Mock `fetch`, not the module under test.
- Tailwind utility classes with `dark:` variants; keep it accessible (labels, `role="alert"`, `aria-live`).

## Testing expectations

- Every new route needs a happy-path test and at least one rejection test. Upload and security
  rules need explicit negative tests.
- Keep smoke tests (`pytest -m smoke`, `src/app/page.test.tsx`) fast and offline. No network,
  no model, no AWS.
