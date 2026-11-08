# Running SketchLogic on Windows and WSL2

Requirements: **Node.js 20.19+** (tested on 26.13), **uv** (provides Python 3.12; tested with
CPython 3.12.16). Git is recommended.

## Option A: native Windows (PowerShell)

```powershell
# 1. Install tools (once)
winget install --id astral-sh.uv -e --source winget
winget install --id OpenJS.NodeJS.LTS -e --source winget    # if Node isn't installed
winget install --id Git.Git -e --source winget              # recommended
# Open a NEW terminal so PATH updates apply.

# 2. From the repo root
.\scripts\setup.ps1     # backend venv + deps, frontend npm install, copies .env files
.\scripts\dev.ps1       # opens two windows: API on :8000, UI on :3000
.\scripts\check.ps1     # lint, typecheck, tests and build, as in CI
```

If PowerShell blocks scripts, allow them for your user once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Manual equivalent:

```powershell
cd backend
uv venv --python 3.12 .venv
uv pip install --python .venv -e ".[dev]"
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# second terminal
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 (UI) and http://127.0.0.1:8000/docs (API docs).

### TLS errors from uv (`invalid peer certificate: UnknownIssuer`)

Antivirus or a corporate proxy that inspects HTTPS replaces certificates with its own root CA,
which uv's bundled certificate list doesn't include. Tell uv to use the Windows certificate store:

```powershell
$env:UV_SYSTEM_CERTS = "1"          # this session
setx UV_SYSTEM_CERTS 1              # future sessions
```

### OneDrive

If the repo is inside a OneDrive folder (for example `Desktop` when Desktop backup is on), OneDrive
tries to sync `node_modules/` and `.venv/`. That slows installs and can lock files. Either
right-click the project folder → *Free up space* / pause syncing while developing, or keep the
repo outside OneDrive (e.g. `C:\dev\sketchlogic-ai`).

## Option B: WSL2 (recommended for ML work in Phase 3)

GPU training with Unsloth/PyTorch works best on Linux, and WSL2 supports CUDA on NVIDIA GPUs.

```powershell
# PowerShell (admin), once; then reboot
wsl --install -d Ubuntu-24.04
```

Inside Ubuntu:

```bash
sudo apt update && sudo apt install -y build-essential git curl
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
exec $SHELL && nvm install --lts

# Clone/copy the repo into the Linux filesystem, NOT /mnt/c (much faster I/O):
mkdir -p ~/projects && cp -r /mnt/c/Users/<you>/OneDrive/Desktop/projects/sketchlogic-ai ~/projects/
cd ~/projects/sketchlogic-ai
rm -rf backend/.venv frontend/node_modules     # Windows builds don't work on Linux
./scripts/setup.sh
./scripts/dev.sh
./scripts/check.sh
```

WSL2 forwards `localhost`, so open http://localhost:3000 in your Windows browser.
For GPU later, install the NVIDIA Windows driver only (not a Linux driver), then check with `nvidia-smi` inside WSL.

## Ports & config

| Service | URL | Config |
| --- | --- | --- |
| API | http://127.0.0.1:8000 | `backend/.env` (`SKETCHLOGIC_*`, see `.env.example`) |
| UI | http://localhost:3000 | `frontend/.env.local` (`NEXT_PUBLIC_API_BASE_URL`) |

If you change the UI origin/port, add it to `SKETCHLOGIC_CORS_ORIGINS`.
