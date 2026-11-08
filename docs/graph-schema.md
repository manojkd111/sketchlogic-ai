# Graph schema (v1.0)

Source of truth: [`backend/app/schemas/graph/v1.py`](../backend/app/schemas/graph/v1.py).
Exported JSON Schema: [`shared/schemas/graph.v1.json`](../shared/schemas/graph.v1.json).
Example: [`shared/examples/three-tier.graph.json`](../shared/examples/three-tier.graph.json).

```
GraphDocument
├─ schema_version: "1.0"            (literal; other values are rejected)
├─ id, title
├─ groups[]  Group  { id, label, parent_id?, confidence, provenance }
├─ nodes[]   Node   { id, label, kind, group_id?, position?, source_bbox?, confidence,
│                     provenance, attributes{str:str} }
├─ edges[]   Edge   { id, source, target, label?, direction, evidence, confidence,
│                     rationale?, provenance }
└─ metadata  { source{kind, upload_id?, filename?, width?, height?}, provider?, model?,
               created_at, warnings[] }
```

**Geometry.** `Node.position` is an absolute canvas coordinate (top-left), independent of
grouping. `source_bbox` is a separate, normalised location in the source image. Groups store no
geometry; the editor derives each group's box from its members
(`frontend/src/lib/graph-to-flow.ts`).

## Enums

| Enum | Values |
| --- | --- |
| `NodeKind` | component, service, database, queue, storage, actor, external, process, decision, start_end, note, unknown |
| `EdgeDirection` | forward, bidirectional, none |
| `EdgeEvidence` | **observed** (arrow/line visible in source), **inferred** (model guess) |
| `Origin` | ai_extracted, ai_modified, user_created, user_corrected, imported |
| `SourceKind` | image, xlsx, sketch, manual |

## Invariants (validated)

- `extra="forbid"` everywhere: unknown fields are rejected, so model output can't smuggle
  in code or markup.
- Ids match `^[A-Za-z0-9_.:\-]+$` (≤ 64 chars) and are unique per collection.
- Edges reference existing nodes; `group_id` / `parent_id` reference existing groups; group
  nesting is acyclic.
- `evidence = "inferred"` ⇒ `confidence < 1.0`, so inferred edges can always be surfaced for review.
- `origin = "user_corrected"` ⇒ `locked = true`. Locked elements must not be changed by
  automated operations without explicit user approval.
- `confidence` and `source_bbox` values are in [0, 1].

## Versioning policy

- **Additive, optional** fields → may be added to the current version (minor bump, e.g. `1.1`,
  added to `SUPPORTED_SCHEMA_VERSIONS`).
- **Breaking** changes (rename, remove, change meaning/type) → new module `v2.py`, new
  `graph.v2.json`, and an explicit `v1 → v2` migration function with tests. Never edit the
  meaning of an existing field in place.
- After any change: `python -m scripts.export_schema` (from `backend/`), then update
  `frontend/src/lib/graph-schema.ts`. Tests on both sides fail if they drift.
