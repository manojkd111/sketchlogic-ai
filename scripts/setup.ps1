# One-time setup on Windows (PowerShell). Run from the repo root:  .\scripts\setup.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "uv not found. Install it with:  winget install --id astral-sh.uv -e --source winget" -ForegroundColor Yellow
  exit 1
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Write-Host "Node.js not found. Install Node 20.19+ (LTS) from https://nodejs.org" -ForegroundColor Yellow
  exit 1
}

Push-Location "$root\backend"
try {
  if (-not (Test-Path .venv)) { uv venv --python 3.12 .venv }
  uv pip install --python .venv -e ".[dev]"
  if (-not (Test-Path .env)) { Copy-Item .env.example .env }
} finally { Pop-Location }

foreach ($pkg in @("ml", "evaluations")) {
  Push-Location "$root\$pkg"
  try {
    if (-not (Test-Path .venv)) { uv venv --python 3.12 .venv }
    uv pip install --python .venv -e ".[dev]"
  } finally { Pop-Location }
}

Push-Location "$root\frontend"
try {
  npm install
  if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
} finally { Pop-Location }

Write-Host "`nSetup complete. Start both servers with:  .\scripts\dev.ps1" -ForegroundColor Green
