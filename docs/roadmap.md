# Roadmap

| Phase | Scope | Status |
| --- | --- | --- |
| **1. Foundation** | Monorepo, Next.js shell, FastAPI, health, upload + validation, graph schema v1, SQLite, dev scripts, tests, CI | ✅ Done |
| **2. Editor & canvas** | React Flow editor with ELK.js layout; GraphDocument ⇄ React Flow mapping; inferred-edge styling + accept/reject; lock-on-edit; Excalidraw sketch canvas → PNG upload; graph persistence (`graphs` table, versions) | Next |
| **3. AI extraction** | XLSX parser (openpyxl: edge-list / adjacency layouts); `local` provider for Qwen2.5-VL-3B; synthetic data generator; Unsloth/PEFT/TRL LoRA fine-tune; evaluation harness; NL modifications as structured patch ops with approval for locked elements | Planned |
| **4. Present, export, cloud** | Step-by-step animated presentation; PNG/SVG/Mermaid/JSON export; Bedrock provider (boto3) behind `aws_enabled` + explicit approval | Planned |

## Phase 2 checklist

- [ ] `npm i @xyflow/react elkjs @excalidraw/excalidraw` (`@xyflow/react` 12.12.1 done)
- [x] `lib/graph-to-flow.ts` + tests (round-trip preserves ids, provenance, evidence).
      `GraphNode.position` is **absolute**; group boxes are derived from members.
- [ ] ELK layout in a web worker; respect groups as compound nodes
- [ ] Inferred edges dashed + confidence badge; accept → `observed`/`user_corrected`
- [ ] Any manual edit → `origin=user_corrected`, `locked=true`
- [x] Backend: `graphs` + `graph_versions` tables, `POST/GET/PUT /api/v1/graphs`
      (+ list, version history, optimistic concurrency via `base_version` → 409; TS client in `lib/api.ts`)
- [ ] Excalidraw canvas exporting PNG into the existing upload flow
- [ ] Playwright e2e: upload → see validation → open editor
