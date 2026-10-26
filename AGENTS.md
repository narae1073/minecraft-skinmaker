# Agent contract — skinmaker

Read `docs/handover.md` first. Two people work on this repo with coding agents;
this file is the shared contract.

## Commands

```bash
.venv/bin/python -m pytest -q          # full suite (~3 min). Never pipe to tail.
cd frontend && npm run lint            # required before frontend commits
cd frontend && npm run build           # production build (backend serves dist/)
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
```

Use `.venv/bin/python` (Windows: `.venv\Scripts\python.exe`) — not `python`, not `uv`.

### Windows

Native Windows is supported for development, **not deployment**.

- Prefer **WSL2** (then all commands in this file work unchanged) or run the
  `.sh` scripts from **Git Bash**; PowerShell/cmd cannot run them directly.
- Native venv: `py -3.12 -m venv .venv`, then `.venv\Scripts\python.exe`.
  `python -m venv .venv` works too if that is the 3.12 interpreter.
- Fetch models in Git Bash: `bash scripts/fetch_assets.sh --yunet-only`
  (add `--schp-only` for the 66 MB parser). All dependencies have Windows wheels.
  If `bash` is not on PATH, use `"C:\Program Files\Git\bin\bash.exe" scripts/fetch_assets.sh --yunet-only`.
- `npm ci` / `npm run lint` / `npm run build` work normally.
- To run the local UI without a Gemini key, put `SKINMAKER_TRANSPORT=mock` in
  `.env`; tests already use the mock transport.
- **Never run** `scripts/deploy.sh` or `scripts/cleanup_static.sh` on Windows;
  deployment and retention are host-only (Linux).
- A Windows CI job (`test-windows`) runs the suite on every PR.

## Codex devbox (second developer)

The trusted collaborator runs **Codex** inside a Docker container on this host.
See `docs/devbox.md`.

- Workspace inside the container: `/workspace` (a separate clone, not the
  production checkout). SSH: `ssh -p 2222 dev@<tailnet-ip>`; key-only.
- Codex is preinstalled. Log in with `codex login --device-auth` (or an API key);
  because the container is the sandbox, bypass Codex's nested sandbox if needed.
- GitHub auth is the collaborator's own account (`gh auth login`).
- No production `.env`, Docker socket, systemd, or cloudflared credentials are
  inside the container. Deploy from the host, not the container.
- Production access is allowed for this trusted person via
  `ssh achi@<tailnet-ip>`, but the Codex workspace remains a separate clone.

## Setup

- Fresh clone or worktree: `./scripts/dev_setup.sh` (add `--with-schp` for the 66 MB parser model).
- Models are gitignored: `scripts/fetch_assets.sh` downloads YuNet + SCHP. Tests only need YuNet.
- Copy `.env.example` to `.env` and add `GEMINI_API_KEY` if you need the real VLM; tests use the mock transport.
- `out/` is scratch space and gitignored. Committed test images live in `tests/fixtures/`.

## Branches and PRs

- **Never push to `master`.** Use `feat/<topic>` or `fix/<topic>`, open a PR, get one approval.
- Rebase on `origin/master` before opening/merging. Keep PRs small.
- Same machine, two agents: use separate worktrees and ports.
  ```bash
  git worktree add ../skinmaker-b -b feat/<topic> origin/master
  cd ../skinmaker-b && ./scripts/dev_setup.sh
  # backend 8002 + frontend VITE_API_TARGET=http://localhost:8002
  ```
- Separate machines: clone normally; CI is the source of truth.

## Never commit

`out/`, `backend/static/`, `frontend/dist/`, `.env`, `*.onnx`, `assets/*.task*`,
`__pycache__/`, logs, or generated screenshots. They are gitignored — do not
force-add them.

## Deploying

Only the host owner deploys, after the PR is merged:

```bash
./scripts/deploy.sh          # pull, install, build, test, restart systemd
```

Never deploy from a branch. Do not restart `cloudflared-*` services while
debugging the app.

## Public site

`https://skin.achijaser.date` is public and has no login. Do not add anything
that exposes the Gemini key client-side, and keep the upload/rate limits in
`backend/app.py` intact. Uploaded files are retained per
`SKINMAKER_RETENTION_DAYS`.

## Where things live

- Pipeline: `skinmaker/format.py` (UV truth) → `colors.py` → `attributes.py`/`classify.py` → `render.py` → `candidates.py`.
- API: `backend/app.py`. UI: `frontend/src/App.jsx` + `components/`.
- Tests: `tests/` (contract-style; `tests/fixtures/` are committed).
- Design history: `docs/superpowers/`, `docs/ledger/`.

## Handoff

At the end of a session update `docs/handover.md` and put evidence (commands +
results, risks) in the PR description. If a policy or constant changes, include
a recorded A/B baseline.
