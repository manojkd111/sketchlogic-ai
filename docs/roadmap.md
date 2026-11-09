# Roadmap

| Phase | Scope | Status |
| --- | --- | --- |
| **1. Foundation** | Monorepo, Next.js shell, FastAPI, health, upload + validation, graph schema v1, SQLite, dev scripts, tests, CI | ✅ Done |
| **2. Editor & canvas** | React Flow editor with ELK.js layout; GraphDocument ⇄ React Flow mapping; inferred-edge styling + accept/reject; lock-on-edit; Excalidraw sketch canvas → PNG upload; graph persistence (`graphs` table, versions) | ✅ Done |
| **3. AI extraction** | XLSX parser (openpyxl: edge-list / adjacency layouts); `local` provider for Qwen2.5-VL-3B; synthetic data generator; Unsloth/PEFT/TRL LoRA fine-tune; evaluation harness; NL modifications as structured patch ops with approval for locked elements | Next |
| **4. Present, export, cloud** | Step-by-step animated presentation; PNG/SVG/Mermaid/JSON export; Bedrock provider (boto3) behind `aws_enabled` + explicit approval | Planned |

## Phase 2 checklist

- [x] `npm i @xyflow/react elkjs @excalidraw/excalidraw` (12.12.1 / 0.12.1 / 0.18.1; npm
      `overrides` pin patched `lodash-es` and `nanoid` pulled in by Excalidraw's Mermaid import)
- [x] `lib/graph-to-flow.ts` + tests (round-trip preserves ids, provenance, evidence).
      `GraphNode.position` is **absolute**; group boxes are derived from members.
- [x] ELK layout in a web worker; respect groups as compound nodes
      (`lib/elk-layout.ts`, `lib/layout.worker.ts`). Pinned locked nodes are never moved;
      their layout positions are offered as a proposal the user approves.
- [x] Inferred edges dashed + confidence badge; accept → `observed`/`user_corrected`
      (inline on the canvas and in the sidebar review list; reject removes the edge)
- [x] Any manual edit → `origin=user_corrected`, `locked=true` (`lib/graph-edits.ts`
      `applyUserEdit`; new user elements → `user_created` + locked)
- [x] Editor page `/graphs/[id]` (`components/GraphEditor.tsx`): drag, connect, rename,
      save with 409 conflict handling. Backend `POST /api/v1/uploads/{id}/extract`
      (mock provider; never overwrites an existing graph)
- [x] Deleting nodes/edges/groups (Backspace/Delete or inspector; deleting a group keeps its
      contents), adding nodes, changing node kind. Editing your own nodes keeps `user_created`.
- [x] Backend: `graphs` + `graph_versions` tables, `POST/GET/PUT /api/v1/graphs`
      (+ list, version history, optimistic concurrency via `base_version` → 409; TS client in `lib/api.ts`)
- [x] Excalidraw canvas exporting PNG into the existing upload flow (`/sketch`; export scaled so
      the short side is ≥512px; training consent opt-in as on the upload page)
- [x] Playwright e2e (`frontend/e2e/`, `npm run e2e`, CI job `e2e`): upload → validation →
      extract → review/accept → save → reload; mismatched-bytes rejection; sketch → editor

## Phase 3 checklist

- [x] XLSX import (`backend/app/services/xlsx_import.py`): edge lists, adjacency matrices,
      optional `Nodes` sheet for kinds and groups; formulas never evaluated. See
      `docs/architecture.md#spreadsheet-import-xlsx`.
- [ ] Synthetic data generator (rendered diagrams + ground-truth `GraphDocument`s)
- [ ] `local` provider: Qwen2.5-VL-3B served locally behind `InferenceProvider`
- [ ] LoRA fine-tune (Unsloth/PEFT/TRL) on consented + synthetic data
- [ ] Evaluation harness (`evaluations/`): node/edge precision-recall, inferred-edge calibration
- [ ] NL modifications as structured patch ops; ops on locked elements need approval
