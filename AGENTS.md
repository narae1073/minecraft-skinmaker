# Agent contract — skinmaker

Read `docs/handover.md` first. Two people work on this repo with coding agents;
this file is the shared contract.

## Commands

```bash
.venv/bin/python -m pytest -q          # full suite (~3 min). Never pipe to tail.
cd frontend && npm run lint            # required before frontend commits
cd frontend && npm test                # vitest (vitest run), required before frontend commits
cd frontend && npm run build           # production build (backend serves dist/)
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
./scripts/editor_dev.sh               # developer mask editor on 127.0.0.1:8765 (token in out/mask_editor/access_token)
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

The trusted collaborator runs the **Codex GUI on Windows** and adds the devbox
as a **remote project over SSH**. See `docs/devbox.md`.

- Workspace inside the container: `/home/dev/workspace` (a separate clone, not the
  production checkout). SSH: `ssh -p 2222 dev@<tailnet-ip>`; key-only.
- The Codex CLI is **not installed in the default image**, but this host runs
  with `INSTALL_CODEX=1` because the GUI's remote-project mode requires the
  remote CLI (`codex-cli 0.164.0`). If the GUI asks for auth, run
  `codex login --device-auth` inside `/home/dev/workspace`. The entrypoint
  starts the managed app-server (`codex app-server daemon bootstrap`/`start`);
  if the GUI reports a missing `app-server-control.sock`, run those two
  commands inside the container.
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
- After approval and green CI, enable auto-merge:
  ```bash
  gh pr merge --auto --rebase
  ```
  GitHub merges when the required checks pass; the host's deploy workflow then
  deploys automatically.
- **Owner-approved admin merge (2026-11-21).** When a merge is needed and the
  normal approval is unavailable, the repo owner has authorized
  `gh pr merge --admin --rebase`. Prefer the review path when it is available,
  and only bypass the missing approval — CI must still be green.
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

Deployment is **automatic on merge to `master`**: the self-hosted runner
`skinmaker-home` runs `/home/achi/Programming/skinmaker-release/scripts/deploy.sh`
(`push: master` → `.github/workflows/deploy.yml`). It pulls, installs, builds,
tests, restarts `skinmaker`, and health-checks.

Manual fallback on the host only:

```bash
cd /home/achi/Programming/skinmaker-release
./scripts/deploy.sh
```

Never deploy from a dev checkout. The DSH checkout
(`/home/achi/Programming/skinmaker`) and the Codex clone
(`/home/achi/Programming/skinmaker-codex`) are development only. Do not restart
`cloudflared-*` services while debugging the app.

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

## Browser QA (headless Chrome)

Used for editor/UI checks (`/edit/{id}`, `tools/mask_editor`, the main page).
Getting this wrong is the biggest time sink in a session — follow the order.

- **Probe first, script second.** `curl /json/version` → create a fresh target
  with `PUT /json/new?<url>` → send `Page.enable` and wait for a reply. Only
  then run the full script. Attaching to an existing `about:blank` tab can hang
  `Page.enable` forever.
- **Fresh port and fresh profile per run** (`--remote-debugging-port=93xx`,
  `--user-data-dir=/tmp/opencode/chrome-<topic>-<n>`). Leftover Chrome causes
  `bind() failed: Address already in use` and connections that go nowhere.
- **Stop exactly the port's PID** (`ss -ltnp | grep :93xx`). A broad
  `pkill -f <pattern>` also matches the shell command you are running.
- **`node --check` the QA script before running it**, and build in-page
  expressions with `JSON.stringify` instead of nested template literals
  (nested backticks silently eat quotes: `ReferenceError: L1 is not defined`).
- **Drive the app's own API instead of mouse coordinates** where possible
  (`window.maskEditor.paintTexel`, `setMobileTab`, `setBrush`, …). Coordinates
  break with zoom, layout and scroll.
- Every CDP wait needs a **timeout and a name**; a script that exits 124 costs
  as much as the bug it was meant to catch.
- The dev mask editor requires auth: `POST /api/auth {token}`, then reload. The
  token lives in `out/mask_editor/access_token`.
- Run the **focused** test files while iterating; run the full `pytest -q`
  (~4 min) once before merging. Budget ~10 min for CI (`test`,
  `test-windows`, `web`) plus deploy.
- **After deploying an editor change, open the real `/edit/{id}` and check it
  boots**: every `/edit/lib/*.js` the page imports must return 200 (the job
  route serves an allowlist, unlike the standalone dev server), and the console
  must be clean. A single 404 in that module graph leaves the atlas and the
  attribute panel blank with no visible error. `npm`/standalone checks do not
  cover this.

## Handoff

At the end of a session update `docs/handover.md` and put evidence (commands +
results, risks) in the PR description. If a policy or constant changes, include
a recorded A/B baseline.
