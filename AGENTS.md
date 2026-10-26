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

Use `.venv/bin/python` — not `python`, not `uv`.

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
