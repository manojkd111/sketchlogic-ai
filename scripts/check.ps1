# Run every automated check (same as CI). Run from repo root: .\scripts\check.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$failed = @()

function Step([string]$name, [scriptblock]$cmd) {
  Write-Host "`n=== $name ===" -ForegroundColor Cyan
  & $cmd
  if ($LASTEXITCODE -ne 0) { $script:failed += $name }
}

Push-Location "$root\backend"
try {
  $py = ".\.venv\Scripts\python.exe"
  Step "backend: ruff lint"   { & $py -m ruff check . }
  Step "backend: ruff format" { & $py -m ruff format --check . }
  Step "backend: mypy"        { & $py -m mypy app scripts }
  Step "backend: pytest"      { & $py -m pytest }
} finally { Pop-Location }

foreach ($pkg in @("ml", "evaluations")) {
  Push-Location "$root\$pkg"
  try {
    $py = ".\.venv\Scripts\python.exe"
    $mod = if ($pkg -eq "ml") { "sketchlogic_ml" } else { "sketchlogic_eval" }
    Step "${pkg}: ruff lint"   { & $py -m ruff check . }
    Step "${pkg}: ruff format" { & $py -m ruff format --check . }
    Step "${pkg}: mypy"        { & $py -m mypy $mod }
    Step "${pkg}: pytest"      { & $py -m pytest -q }
  } finally { Pop-Location }
}

Push-Location "$root\frontend"
try {
  Step "frontend: typecheck" { npm run --silent typecheck }
  Step "frontend: lint"      { npm run --silent lint }
  Step "frontend: prettier"  { npm run --silent format:check }
  Step "frontend: vitest"    { npm run --silent test }
  Step "frontend: build"     { npm run --silent build }
} finally { Pop-Location }

if ($failed.Count) {
  Write-Host "`nFAILED: $($failed -join ', ')" -ForegroundColor Red
  exit 1
}
Write-Host "`nAll checks passed." -ForegroundColor Green
