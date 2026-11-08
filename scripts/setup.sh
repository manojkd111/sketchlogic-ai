#!/usr/bin/env bash
# One-time setup on WSL2 / Linux / macOS. Run from the repo root: ./scripts/setup.sh
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"

command -v uv >/dev/null || { echo "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
command -v node >/dev/null || { echo "Install Node 20.19+ (e.g. via nvm)"; exit 1; }

cd "$root/backend"
[ -d .venv ] || uv venv --python 3.12 .venv
uv pip install --python .venv -e ".[dev]"
[ -f .env ] || cp .env.example .env

cd "$root/frontend"
npm install
[ -f .env.local ] || cp .env.example .env.local

echo "Setup complete. Start with: ./scripts/dev.sh"
