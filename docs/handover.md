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
- Deployment: **live** at `https://skin.achijaser.date` (public, no auth). Production runs from the **release clone** `/home/achi/Programming/skinmaker-release` (systemd `skinmaker`); dev checkouts are the DSH checkout and the Codex clone. Tunnel `skinmaker` UUID `866fd5b7-5046-4fd7-80a1-2f7b0ae30502`; `cloudflared-skinmaker` and `skinmaker-cleanup.timer` active + enabled.
- CI/CD: self-hosted runner `skinmaker-home` (label `skinmaker-deploy`) runs `.github/workflows/deploy.yml` on every merge to `master`; auto-merge is enabled after 1 approval (`gh pr merge --auto --rebase`).
- Codex devbox: Docker container `skinmaker-codex`, SSH on tailnet `100.110.156.108:2222`, separate workspace `/home/achi/Programming/skinmaker-codex`; verified 513 tests + app health. The GUI's remote-project mode requires the remote CLI, so the host runs with `INSTALL_CODEX=1` (`codex-cli 0.164.0`); auth is pending. Partner key/Tailscale invite and the GUI connection are pending user actions.
- 2026-10-27: 메인 화면 `<h1>` 을 `환영합니다!` 로 변경 (PR #13, `frontend/src/App.jsx`). 로컬 프리뷰는 이 체크아웃에서 `.venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8002` (mock `.env`, 8001 은 프로덕션 릴리스 클론) 또는 `cd frontend && npm run dev -- --host` (5173, ufw 허용됨).
- Git: `master` has hygiene (PR #1), CI/agent workflow (PR #2), deployment hardening (PR #3), live docs (PR #4), Windows support (PR #5), Windows docs (PR #6), devbox (PR #7), no-CLI cleanup (PR #8), Codex CLI enabled (PR #9), persistent SSH host keys (PR #10), workspace move (PR #11), and auto-deploy (PR #12). Branch protection requires `test`, `test-windows`, `web`, 1 approval, linear history; admins can bypass for ops. `opencode.jsonc` is deleted and gitignored by the user.

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

## 7. Codex devbox (PR #7; CLI enabled on this host)

- `deploy/dev/`: Python 3.12 + Node 24 + git/gh/rsync/sshd. Default `INSTALL_CODEX=0`; **this host runs `INSTALL_CODEX=1`** because the Codex GUI's remote-project mode requires the remote CLI (`codex-cli 0.164.0` at `/usr/bin/codex`).
- Separate clone `/home/achi/Programming/skinmaker-codex` mounted at `/home/dev/workspace`; **not** the production checkout. Container has no production `.env`, Docker socket, systemd, or cloudflared credentials.
- SSH is key-only on `100.110.156.108:2222` (tailnet only); 4 GB / 2 CPU / 1024 pids; `no-new-privileges`.
- Host setup: `./scripts/devbox_setup.sh --key /path/to/codex.pub` (clone, `.env` mock, bootstrap inside the container, compose up). It preserves `INSTALL_CODEX`; re-run if `tailscale ip -4` changes.
- Verified: SSH, `codex-cli 0.164.0`, `pytest -q` 513 passed (5.5 min with SCHP), `npm run build`, uvicorn health `ok` / root 200 with mock, port/limits.
- Pending user actions: add the partner's public key (a test key is currently authorized); partner adds the remote project in the Codex GUI and runs `gh auth login`; if the GUI asks for remote auth, `codex login --device-auth`.
- Production access is intentionally allowed for this trusted person via `ssh achi@<tailnet>`; deployment still happens on the host.

## 8. Auto-merge + auto-deploy (PR #12, 2026-10-27)

- **Release clone**: `/home/achi/Programming/skinmaker-release` (separate from DSH `/home/achi/Programming/skinmaker` and Codex `/home/achi/Programming/skinmaker-codex`). Own venv, `.env`, `backend/static`, `out/models`, `assets`, `frontend/dist`; systemd `skinmaker` runs here. The DSH checkout now has a mock `.env`.
- **Self-hosted runner**: `/home/achi/actions-runner`, service `actions.runner.narae1073-minecraft-skinmaker.skinmaker-home`, labels `self-hosted, linux, skinmaker-deploy`; online. It runs only `.github/workflows/deploy.yml` (`push: master`, `workflow_dispatch`), which calls the release `scripts/deploy.sh` (pull → pip → npm ci/build → pytest → restart → health).
- **Auto-merge**: repo setting `allow_auto_merge=true`; PRs need 1 approval + CI. Agents run `gh pr merge --auto --rebase` after opening; the other person/agent approves; GitHub merges and the deploy workflow runs.
- **Manual fallback**: `cd /home/achi/Programming/skinmaker-release && ./scripts/deploy.sh`.
- **Verified**: production switched to release; public `/` and health 200; runner online. The first auto-deploy is the merge of PR #12.
- **Security note**: the runner is persistent on a public repo. Only workflows merged to `master` can use the `skinmaker-deploy` label; no PR workflow targets it. Branch protection + 1 approval remain the gate.

## 9. Known issues / backlog

- Pose path is dormant (model disabled, mediapipe removed). Re-enable deliberately: install `mediapipe`, restore `assets/pose_landmarker_lite.task`, re-add `requirements-pose.txt`.
- S2 `top_garment` distinction (polo/shirt/tank) remains the weakest field.
- Editor expansion (live re-render, outfit/skin-tone options) is deferred; the option seam is in `SkinEditor.jsx`.
- Deferred minors from the 2026-10-13 review (sidebar steps image, flatUrl guard, hard |Δ| in jeans test, eval tolerance) still apply.
- Public no-auth deployment: rate limit + upload cap + retention are the mitigations. Revisit Cloudflare Access if abuse appears. The Cloudflare WAF outer rate-limit rule is still manual.
- Branch protection requires 1 approval; admins can bypass (`enforce_admins=false`) for bootstrap/ops. Use `gh pr merge --admin` only for setup/ops, not feature work.
- Old held-out photos remain in public git history; revisit only with a coordinated history rewrite.
- Codex devbox: the GUI's remote-project mode requires the remote CLI; this host runs `INSTALL_CODEX=1` with `codex-cli 0.164.0`. Auth is not configured yet; if the GUI asks, run `codex login --device-auth`. SSH host keys persist in the `skinmaker-codex-ssh` volume (ED25519 `SHA256:RG3rzByQ6WVLf5Li6xr+KMgzJQvm0t6SUUPCpVFGTps`), so rebuilds no longer change the fingerprint; delete that volume only if you accept a new host key. The workspace `.venv` is container-specific; do not run host `dev_setup.sh` on that clone. A test key is currently in the authorized_keys file; add the partner's key with `scripts/devbox_setup.sh --key`.

## 10. Working norms (do not violate)

- TDD: fail first → minimal implementation → green. Run commands unpiped and check exit codes.
- `npm run lint` before frontend commits.
- Policy/constant changes need a recorded A/B baseline.
- Generated files, `.env`, and models are never committed.
- Short-lived branches + PRs; never push `master` after protection is enabled.
- Update this document at the end of a session; put task evidence in the PR description.

## 11. Records map

- Design specs/plans: `docs/superpowers/specs/`, `docs/superpowers/plans/`
- Ledger: `docs/ledger/`
- Screenshots: `docs/assets/screenshots/`
- Design mockups: `docs/design/mockups/`
- Deployment: `docs/deployment.md`
- Codex devbox: `docs/devbox.md`
- This document: `docs/handover.md`

## 12. Session update (2026-10-27)

- GitHub authentication completed; branch `feat/camera-upload-preview` pushed and PR #16 created: https://github.com/narae1073/minecraft-skinmaker/pull/16 . Frontend lint/build passed; full local pytest final output could not be recovered after the process session disappeared, so required CI must establish the suite result. Device/browser checks remain manual. Deployment awaits one review approval, green CI, and merge; do not bypass protection.

- Upload attempt: changes committed on `feat/camera-upload-preview` and rebased on `origin/master` (`98836b6`). User explicitly approved pushing to public `narae1073/minecraft-skinmaker`, but push failed because GitHub credentials are absent; `gh pr status` also requires `gh auth login`. No remote branch/PR/deployment was created. Final frontend lint/build passed; full `.venv/bin/python -m pytest -q` was started and remains pending at this handoff. After authentication, finish checking the suite, push, create/attach PR with evidence, and follow required approval/CI before auto-merge.

- Made setting labels bold to distinguish control names from help text; inline checkbox help remains normal weight, as do detailed `.config-help` paragraphs. Validation: frontend lint/build.

- Refined upload-panel alignment with shared CSS subgrid rows: camera guidance and file-picker controls center vertically in the same top row, while both action buttons stretch across the same bottom row. Replaces independent flex layouts so wrapped camera guidance cannot shift one button independently. Validation: frontend lint/build and whitespace check.

- Aligned camera/conversion action buttons at the bottom of their equal-height upload panels and added “PC 웹캠 또는 모바일 카메라로 촬영할 수 있어요.” above the camera button. Both buttons share a minimum height (48px desktop / 72px narrow layouts). Verification: frontend lint/build and whitespace check.

- Corrected file-picker centering: replaced visible native file input (with browser-dependent trailing space) with a centered button/filename group backed by a hidden native input. Long names truncate inside the panel; the full filename and thumbnail remain below. Frontend lint/build validation recorded with this change.

- Added `SelectedPhoto.jsx` to display a 56×56, uncropped original-photo thumbnail immediately left of the selected filename. Works with file picker and camera photos using local object URLs; URLs are revoked on replacement/unmount. Frontend lint/build passed (existing bundle warning); browser visual check remains manual.

- Added `SkinPreview.jsx`: successful generation opens a native modal with a rotatable 3D result, candidate selector when multiple skins exist, explicit PNG download link, and a no-download close action. Escape closes; results/history remain available, with a reopen button. Underlying result viewers mount after the preview closes to avoid duplicate active 3D canvases. Shared generation flow also covers camera photos. Frontend lint/build passed; physical/browser interaction has not been exercised here.

- Reworded four generation settings with visible, `aria-describedby`-linked Korean help: 노이즈 강도 → 픽셀 질감, 머리 형태 → 헤어스타일 표현, 머리 대칭 → 머리 좌우 모양, L2 머리 → 머리카락 볼륨. Simplified option labels, documented mask fallback and symmetry applicability, and allowed controls to wrap on narrow screens. Behavior/defaults/API values remain unchanged. Verified descriptions against `render.py` and `hairstencil.py`; frontend lint/build passed (existing chunk warning).

- Added a mobile-access QR/link beside the title using locally rendered `qrcode.react` SVG with a four-module margin. User chose the production site as destination. URL baseline A: no QR. B: Vite development or loopback host → `https://skin.achijaser.date`; deployed non-loopback host → `window.location.origin`, refreshed on page load so scheme/hostname/port changes are reflected without rebuilding. Development localhost URLs are never encoded. This does not establish network reachability for arbitrary hosts.
- QR verification: `npm run lint`, `npm run build`, and `git diff --check` passed; real phone scanning has not been exercised. `npm audit --omit=dev --json` reports zero vulnerabilities; full audit reports one high-severity advisory in existing dev-only `zod` (unrelated to the added QR dependency). Existing bundle-size warning remains.

- Centered the file picker horizontally within the right upload panel using intrinsic width and `align-self: center`, retaining the panel-width cap.

- Desktop camera support: `CameraCapture.jsx` opens a native modal dialog, requests video only, shows webcam preview, and captures a JPEG into the existing selected-file state. Mobile keeps the native capture input. Closing/capturing/unmounting releases camera tracks, including late permission responses; denied permissions/missing devices show a file-selection fallback.
- Webcam verification: frontend lint/build and `git diff --check` passed (existing chunk-size warning). Physical camera capture and browser permission UI have not been exercised in this remote container. Webcam requires HTTPS or localhost; test using Chrome on the user's PC, allow camera, capture, then convert. Also check deny permission, close/Escape, and mobile native capture.

- Follow-up upload layout: split the upload controls into two equal-width dashed panels, camera on the left and file picker plus conversion button on the right. Selected filename remains below both panels.

- Added “카메라로 사진 찍어 업로드” immediately left of the conversion button, with equal-width action buttons. A separate hidden image input requests the rear camera (`capture="environment"`) on supporting mobile browsers and feeds the existing file selection/upload flow. The selected filename is shown for both upload sources; conversion remains a separate user action.
- Camera button verification: `cd frontend && npm run lint` and `npm run build` passed; `git diff --check` passed. Existing large-chunk build warning remains. Physical mobile camera behavior has not been verified and depends on browser support (desktop falls back to file selection).

- Updated the main webpage heading in `frontend/src/App.jsx` to “마인크래프트 스킨 메이커”. Replaced the current “환영합니다!” heading with the requested title after rebasing on the latest `origin/master`.
- Verification: `cd frontend && npm run lint` passed; `cd frontend && npm run build` passed (Vite emitted the existing large-chunk warning).
- Risk: none identified; frontend build output remains generated and gitignored.
