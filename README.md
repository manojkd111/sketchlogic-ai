# SketchLogic AI

Turn messy Google Sheets screenshots, whiteboard photos, hand-drawn flows and `.xlsx` files into
clean, editable system-architecture and process diagrams.

**Status: Phase 1 (foundation).** Upload + validation, versioned graph schema, health API,
initial UI. See [docs/roadmap.md](docs/roadmap.md).

## Quick start (Windows PowerShell)

```powershell
winget install --id astral-sh.uv -e --source winget   # once; then open a new terminal
.\scripts\setup.ps1
.\scripts\dev.ps1          # UI http://localhost:3000 · API http://127.0.0.1:8000/docs
.\scripts\check.ps1        # all lint/type/test/build checks
```

WSL2 / Linux / macOS: `./scripts/setup.sh && ./scripts/dev.sh`. The full guide, including
TLS-proxy and OneDrive notes, is in [docs/setup-windows-wsl.md](docs/setup-windows-wsl.md).

## Layout

```
frontend/      Next.js 16 · React 19 · Tailwind 4 · Vitest
backend/       FastAPI · Pydantic v2 · SQLite · NetworkX · pytest
shared/        graph.v1.json (generated JSON Schema) + example documents
ml/            Qwen2.5-VL-3B fine-tuning & local serving (Phase 3)
data/          datasets (git-ignored, consent policy)
evaluations/   extraction metrics (Phase 3)
docs/          architecture, schema, setup, roadmap, ADRs
scripts/       setup / dev / check (.ps1 + .sh)
```

## Docs

- [Architecture & API](docs/architecture.md)
- [Graph schema v1](docs/graph-schema.md)
- [Windows / WSL2 setup](docs/setup-windows-wsl.md)
- [ADR 0001: foundation decisions](docs/adr/0001-foundation.md)
- [CLAUDE.md](CLAUDE.md): conventions and hard rules for contributors and AI agents
