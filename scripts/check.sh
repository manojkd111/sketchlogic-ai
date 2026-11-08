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

cd "$root/frontend"
npm run --silent typecheck
npm run --silent lint
npm run --silent format:check
npm run --silent test
npm run --silent build
echo "All checks passed."
