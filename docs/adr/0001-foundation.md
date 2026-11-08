# ADR 0001: Monorepo layout, schema-first contract, provider interface

- Status: accepted
- Date: 2026-11-08

## Context

SketchLogic spans a web UI, an API, model training and evaluation. All of them need to agree on a
diagram representation that AI produces and humans edit.

## Decisions

1. **One repo, separate top-level packages**: `frontend/`, `backend/`, `ml/`, `data/`,
   `evaluations/`, `docs/`, plus `shared/` for language-neutral artifacts (JSON Schema, examples).
   Each package has its own toolchain (npm / uv) and no cross-package imports. They share only
   files in `shared/`.
2. **Pydantic is the schema source of truth**. The JSON Schema is exported to `shared/` and checked
   by tests on both sides. The schema is versioned by module (`v1.py`) and by a
   `schema_version` literal.
3. **Structured output only**: models return `GraphDocument` JSON (or patch ops later) validated
   with `extra="forbid"`. The frontend renders data with React components. Model output is never
   evaluated as code.
4. **Observed vs inferred** is a required field on edges, not a UI heuristic.
5. **Provenance + locking** on every element, so automated edits can't silently overwrite user
   corrections.
6. **Provider interface** (`InferenceProvider`) isolates model backends; `mock` is the default.
   `bedrock` cannot be selected unless `aws_enabled` is true, and that is false by default.
7. **SQLite via stdlib `sqlite3`** with `PRAGMA user_version` migrations for the MVP. We can move to
   SQLAlchemy/Postgres when we need concurrency or multiple users.
8. **Frontend calls the API directly** (CORS) rather than through Next.js rewrites, so multi-MB
   uploads don't run into proxy body limits and the API stays the only backend.

## Consequences

- Schema changes need a deliberate export + TS mirror update (enforced by tests).
- Swapping or adding model providers doesn't touch routes or UI.
