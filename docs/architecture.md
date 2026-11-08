# Architecture

```
            ┌────────────────────────── frontend/ (Next.js 16, React 19, Tailwind 4) ─────────┐
 Browser ──▶│  Upload panel · (P2) Excalidraw canvas · (P2) React Flow editor + ELK.js layout │
            │  (P4) presentation mode · exports (PNG/SVG/Mermaid/JSON)                        │
            └───────────────┬────────────────────────────────────────────────────────────────┘
                            │  JSON over HTTP  (NEXT_PUBLIC_API_BASE_URL, CORS)
            ┌───────────────▼──────────── backend/ (FastAPI, Pydantic v2) ────────────────────┐
            │  /api/v1/health   /uploads   /uploads/validate   /schema/graph   /graphs/validate│
            │        │                │                                                      │
            │  upload_validation   graph schema v1  ◀── single source of truth               │
            │        │                │                                                      │
            │  SQLite (var/)     graph_ops (NetworkX)     inference provider interface       │
            │                                              ├─ mock     (P1, default)         │
            │                                              ├─ local    (P3, Qwen2.5-VL-3B)    │
            │                                              └─ bedrock  (P4, disabled default) │
            └──────────────────────────────────────────────────────────────────────────────┘
   ml/  training & local serving (P3)     data/  consented datasets     evaluations/  metrics
   shared/schemas/graph.v1.json  — exported from Pydantic, consumed by frontend tests & ML
```

## Data flow (target state)

1. **Upload** → backend sniffs magic bytes, decodes fully, stores under `var/uploads/<id>.<ext>`,
   records metadata + `training_consent` in SQLite.
2. **Extract** (P3) → provider returns a `GraphDocument`; backend re-validates it with Pydantic.
   Invalid output is rejected or repaired by deterministic code, never by `eval`.
3. **Edit** (P2) → the frontend maps `GraphDocument` ⇄ React Flow nodes/edges; ELK.js computes
   positions. Inferred edges render dashed with confidence; user edits set
   `provenance.origin = "user_corrected"` (which forces `locked = true`).
4. **Modify by NL** (P3) → the model proposes a *patch* (structured ops) against the document.
   Ops touching locked elements are returned as "needs approval" instead of being applied.
5. **Present / export** (P4) → derived from the same document.

## Phase 1 API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health` | Liveness + DB check, schema version, provider, `aws_enabled` |
| POST | `/api/v1/uploads/validate` | Validate a file (multipart `file`) without storing it |
| POST | `/api/v1/uploads` | Validate + store; optional form field `training_consent` (default false) |
| GET | `/api/v1/uploads/{id}` | Upload metadata |
| GET | `/api/v1/schema/graph` | JSON Schema of `GraphDocument` |
| POST | `/api/v1/graphs/validate` | Validate a `GraphDocument`; returns NetworkX summary |

Upload errors use one shape: `{"valid": false, "error": {"code": "...", "message": "..."}}`
with status 413 (too large), 415 (unsupported type) or 422 (invalid content). Codes are listed in
`ErrorCode` in `backend/app/services/upload_validation.py`.

## Upload validation rules

| Check | Default |
| --- | --- |
| Max file size (streamed, aborts early) | 10 MiB |
| Allowed kinds (by magic bytes) | PNG, JPEG, WebP, XLSX |
| Image side | 32 px – 12,000 px, ≤ 40 MP total; full Pillow decode |
| XLSX | Must contain `[Content_Types].xml` + `xl/workbook.xml`; no `vbaProject.bin`; ≤ 100 MiB uncompressed; CRC-checked; no DOCTYPE |
| Filename | Directory parts stripped, unsafe chars replaced; stored under a random id |
