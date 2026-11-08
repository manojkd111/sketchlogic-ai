# Start backend (:8000) and frontend (:3000) in separate windows. Run from repo root: .\scripts\dev.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Start-Process powershell -WorkingDirectory "$root\backend" -ArgumentList @(
  "-NoExit", "-Command", ".\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
)
Start-Process powershell -WorkingDirectory "$root\frontend" -ArgumentList @(
  "-NoExit", "-Command", "npm run dev"
)

Write-Host "Backend:  http://127.0.0.1:8000/docs"
Write-Host "Frontend: http://localhost:3000"
