# handover — skinmaker (2026-10-26, master)

## 1. Project in one paragraph

Photo → Minecraft 64×64 skin pipeline.
S0 quality/face detection (YuNet) → S1 colour measurement (white-balance + band/cascade) → SCHP human-parsing mask (colour localization for bottom/hair/shoes — default ON) → S2 classification (double query, uncertainty flags) → S3 parametric render (+ deterministic noise) → S4 candidates (1–3 variants from double-query disagreements) → web app (FastAPI + React 19 / three.js with 3D viewer and editor modal).

## 2. Current state (verified 2026-10-26)

- Tests: **513 passed** (`tests/fixtures/` committed; ~10 s without the SCHP model, ~3 min with it). Tests no longer need the 66 MB SCHP model: the jeans-rule tests stub a zero mask and `test_parsing` uses a dummy model path with a fake session.
- Frontend: `npm run lint` clean, `npm run build` green (Vite 8 / Node 24).
- Python 3.12.3 venv at `.venv`; do **not** use `python` or `uv`.
- Parsing model: `out/models/schp-atr-18-int8-static.onnx` (66 MB, gitignored). YuNet: `assets/face_detection_yunet_2023mar.onnx` (228 KB, gitignored). Both fetched by `scripts/fetch_assets.sh`.
- `mediapipe` was removed from requirements: the pose model is `assets/pose_landmarker_lite.task.disabled`, so `detect_pose()` always returns `None` and pose bands/cover measurement are dormant (code and tests remain).
- Deployment: **live** at `https://skin.achijaser.date` (public, no auth). Tunnel `skinmaker` UUID `866fd5b7-5046-4fd7-80a1-2f7b0ae30502`; config in `~/.cloudflared/skinmaker.yml` (not git); services `skinmaker`, `cloudflared-skinmaker`, `skinmaker-cleanup.timer` active + enabled.
- Codex devbox: Docker container `skinmaker-codex`, SSH on tailnet `100.110.156.108:2222`, separate workspace `/home/achi/Programming/skinmaker-codex`; verified 513 tests + app health. The image has **no Codex CLI** by default — the Windows Codex GUI adds the remote project. Partner key/Tailscale invite and the GUI connection are pending user actions.
- Git: `master` has hygiene (PR #1), CI/agent workflow (PR #2), deployment hardening (PR #3), live docs (PR #4), Windows support (PR #5), Windows docs (PR #6), and the devbox (PR #7) merged; the no-CLI cleanup is PR #8. Branch protection requires `test`, `test-windows`, `web`, 1 approval, linear history; admins can bypass for ops. `opencode.jsonc` is deleted and gitignored by the user.

## 3. Repo hygiene that landed (PR #1)

- Untracked **253 generated skin PNGs** under `backend/static/` (the folder is gitignored; the app recreates it). Local `backend/static` was purged (~547 MB).
- Untracked **70 held-out photos** (public repo) and moved them to `out/heldout-photos/` (gitignored). History was **not** rewritten; old commits still contain them.
- Removed `app.log`; added `*.log` to `.gitignore`.
- Moved `website_output_images/` → `docs/assets/screenshots/`; moved `frontend/public/mockups/` → `docs/design/mockups/` (not referenced; no longer shipped in `dist`).
- Moved `handover.md` → `docs/handover.md`; moved the one tracked ledger to `docs/ledger/`.
- `requirements.txt` is runtime only; `requirements-dev.txt` adds pytest/httpx; `requirements-parsing.txt` was merged (onnxruntime is runtime).
- Added `.env.example` and `tests/fixtures/README.md`.
- Deleted the broken Pages workflow and disabled GitHub Pages (it deployed the repo root, not the app, and 404'd).
- Deleted the two `ci-sync-*` branches that contained a secret-dumping workflow (runs were blocked; no secrets existed).

## 4. CI + agent workflow (PR #2, merged)

- `.github/workflows/ci.yml`: `test` (Python 3.12, `requirements-dev.txt`, YuNet only, `pytest -q`) and `web` (`npm ci`, lint, build). Tests run in ~10 s without the SCHP model.
- `AGENTS.md` + `.github/pull_request_template.md`: branch/PR rules, never-commit list, worktree/port guidance, deploy rules.
- `scripts/dev_setup.sh`: fresh clone/worktree setup (symlinks `.env`, `out/s0_photos`, `out/models` from the main checkout; fetches YuNet; optional `--with-schp`).
- `vite.config.js`: `VITE_API_TARGET` override for a second local backend port.
- Two tests were made model-independent: the jeans-rule backend tests stub a zero mask; `test_parsing` uses a dummy model path with a fake session.
- Branch protection is enabled on `master`: PR + 1 approval + required `test`/`test-windows`/`web`, linear history, no force-push. Admins can bypass for bootstrap/ops (`enforce_admins=false`).

### Windows development (PR #5)

- `test-windows` runs the same 513 tests on `windows-latest`; it is a required check.
- Native Windows: `py -3.12 -m venv .venv`, `.venv\Scripts\python.exe`; `.sh` scripts require Git Bash (or WSL2, recommended).
- Upload temp file now uses `mkstemp` + close before `inspect` (`NamedTemporaryFile` cannot be reopened on Windows); `test_render` reads JSX as UTF-8; `.gitattributes` forces LF.
- For local UI without a Gemini key: `SKINMAKER_TRANSPORT=mock` in `.env`.
- Windows users open PRs and never deploy; deployment/retention stay on the Linux host.

## 5. Deployment hardening (PR #3, merged)

- `backend/limits.py` + `backend/app.py`: 15 MB upload cap (413) and 6/min/IP in-process limiter (429); `CF-Connecting-IP` is trusted only from loopback. Tests: `tests/test_limits.py`, two backend contract tests, `tests/conftest.py` disables the limiter for the rest of the suite.
- `deploy/`: `skinmaker.service` (uvicorn on `127.0.0.1:8001`), `cloudflared-skinmaker.service` (tunnel `skinmaker`), `skinmaker-cleanup.service`/`.timer` (weekly retention), `skinmaker.yml.example`.
- `scripts/deploy.sh` (master-only pull → pip → build → test → restart → health) and `scripts/cleanup_static.sh` (retention).
- `docs/deployment.md`; footer notice for the public demo and retention. 513 tests.

## 6. Host setup (done 2026-10-26)

- Tunnel `skinmaker` created; DNS `skin.achijaser.date` points at it. Config `~/.cloudflared/skinmaker.yml` (mode 600) → `http://127.0.0.1:8001`.
- **Gotcha:** `cloudflared tunnel route dns/info/validate` read the default `~/.cloudflared/config.yml` (`quartz-me`) unless `--config` is passed **before** the subcommand. The first DNS route went to `quartz-me`; fixed with `cloudflared tunnel --config ~/.cloudflared/skinmaker.yml route dns --overwrite-dns skinmaker skin.achijaser.date`. Documented in `docs/deployment.md`.
- Units installed and enabled: `skinmaker`, `cloudflared-skinmaker`, `skinmaker-cleanup.timer`.
- Verified: root/health 200, real upload 200 with skin/input/steps URLs, public static assets 200, no-face 422, 16 MB 413, 429 after the 6/min limit (restart resets the in-memory limiter). `scripts/deploy.sh --no-pull --skip-tests` verified.
- Not done: Cloudflare WAF rate-limit rule (dashboard-only; no API token used), and a reboot test (services are `enabled`; reboot and recheck when convenient).

## 7. Codex devbox (PR #7; no CLI by default after PR #8)

- `deploy/dev/`: Python 3.12 + Node 24 + git/gh/rsync/sshd image. The Codex CLI is **not installed by default**; the Windows Codex GUI adds the container as a remote project over SSH. `INSTALL_CODEX=1` is an opt-in fallback if the GUI asks for a remote helper.
- Separate clone `/home/achi/Programming/skinmaker-codex` mounted at `/workspace`; **not** the production checkout. Container has no production `.env`, Docker socket, systemd, or cloudflared credentials.
- SSH is key-only on `100.110.156.108:2222` (tailnet only); 4 GB / 2 CPU / 1024 pids; `no-new-privileges`.
- Host setup: `./scripts/devbox_setup.sh --key /path/to/codex.pub` (clone, `.env` mock, bootstrap inside the container, compose up). It preserves `INSTALL_CODEX`; re-run if `tailscale ip -4` changes.
- Verified: SSH, no `codex` binary, `pytest -q` 513 passed (5.5 min with SCHP), `npm run build`, uvicorn health `ok` / root 200 with mock, port/limits.
- Pending user actions: invite partner to Tailscale; add their public key (a test key is currently authorized); partner adds the remote project in the Codex GUI and runs `gh auth login`.
- Production access is intentionally allowed for this trusted person via `ssh achi@<tailnet>`; deployment still happens on the host.

## 8. Known issues / backlog

- Pose path is dormant (model disabled, mediapipe removed). Re-enable deliberately: install `mediapipe`, restore `assets/pose_landmarker_lite.task`, re-add `requirements-pose.txt`.
- S2 `top_garment` distinction (polo/shirt/tank) remains the weakest field.
- Editor expansion (live re-render, outfit/skin-tone options) is deferred; the option seam is in `SkinEditor.jsx`.
- Deferred minors from the 2026-10-13 review (sidebar steps image, flatUrl guard, hard |Δ| in jeans test, eval tolerance) still apply.
- Public no-auth deployment: rate limit + upload cap + retention are the mitigations. Revisit Cloudflare Access if abuse appears. The Cloudflare WAF outer rate-limit rule is still manual.
- Branch protection requires 1 approval; admins can bypass (`enforce_admins=false`) for bootstrap/ops. Use `gh pr merge --admin` only for setup/ops, not feature work.
- Old held-out photos remain in public git history; revisit only with a coordinated history rewrite.
- Codex devbox: the partner's GUI remote-project connection is the remaining acceptance gate. The image intentionally has no Codex CLI; if the GUI asks for a remote helper, set `INSTALL_CODEX=1` in `deploy/dev/.env` and rerun `./scripts/devbox_setup.sh --no-bootstrap`. Rebuilding the image changes the container SSH host key — `ssh-keygen -R "[100.110.156.108]:2222"`. The workspace `.venv` is container-specific; do not run host `dev_setup.sh` on that clone. A test key is currently in the authorized_keys file; add the partner's key with `scripts/devbox_setup.sh --key`.

## 9. Working norms (do not violate)

- TDD: fail first → minimal implementation → green. Run commands unpiped and check exit codes.
- `npm run lint` before frontend commits.
- Policy/constant changes need a recorded A/B baseline.
- Generated files, `.env`, and models are never committed.
- Short-lived branches + PRs; never push `master` after protection is enabled.
- Update this document at the end of a session; put task evidence in the PR description.

## 10. Records map

- Design specs/plans: `docs/superpowers/specs/`, `docs/superpowers/plans/`
- Ledger: `docs/ledger/`
- Screenshots: `docs/assets/screenshots/`
- Design mockups: `docs/design/mockups/`
- Deployment: `docs/deployment.md`
- Codex devbox: `docs/devbox.md`
- This document: `docs/handover.md`
