#!/usr/bin/env bash
# Run every automated check (same as CI).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"

cd "$root/backend"
py=.venv/bin/python
$py -m ruff check .
$py -m ruff format --check .
$py -m mypy app scripts
$py -m pytest

for pkg in ml evaluations; do
  cd "$root/$pkg"
  mod=$([ "$pkg" = ml ] && echo sketchlogic_ml || echo sketchlogic_eval)
  .venv/bin/python -m ruff check .
  .venv/bin/python -m ruff format --check .
  .venv/bin/python -m mypy "$mod"
  .venv/bin/python -m pytest -q
done

cd "$root/frontend"
npm run --silent typecheck
npm run --silent lint
npm run --silent format:check
npm run --silent test
npm run --silent build
echo "All checks passed."
