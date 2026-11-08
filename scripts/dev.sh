#!/usr/bin/env bash
# Start backend (:8000) and frontend (:3000); Ctrl+C stops both.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"

(cd "$root/backend" && .venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) &
backend=$!
trap 'kill $backend 2>/dev/null' EXIT
cd "$root/frontend" && npm run dev
