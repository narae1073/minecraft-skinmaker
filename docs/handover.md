# handover — skinmaker (2026-10-26, master)

## 1. Project in one paragraph

Photo → Minecraft 64×64 skin pipeline.
S0 quality/face detection (YuNet) → S1 colour measurement (white-balance + band/cascade) → SCHP human-parsing mask (colour localization for bottom/hair/shoes — default ON) → S2 classification (double query, uncertainty flags) → S3 parametric render (+ deterministic noise) → S4 candidates (1–3 variants from double-query disagreements) → web app (FastAPI + React 19 / three.js with 3D viewer and editor modal).

## 2. Current state (verified 2026-10-27)

- Tests: **539 passed** (`tests/fixtures/` committed; ~10 s without the SCHP model, ~3 min with it). Tests no longer need the 66 MB SCHP model: the jeans-rule tests stub a zero mask and `test_parsing` uses a dummy model path with a fake session.
- Frontend: `npm run lint` clean, `npm run build` green (Vite 8 / Node 24).
- Python 3.12.3 venv at `.venv`; do **not** use `python` or `uv`.
- Parsing model: `out/models/schp-atr-18-int8-static.onnx` (66 MB, gitignored). YuNet: `assets/face_detection_yunet_2023mar.onnx` (228 KB, gitignored). Both fetched by `scripts/fetch_assets.sh`.
- `mediapipe` was removed from requirements: the pose model is `assets/pose_landmarker_lite.task.disabled`, so `detect_pose()` always returns `None` and pose bands/cover measurement are dormant (code and tests remain).
- Deployment: **live** at `https://skin.achijaser.date` (public, no auth). Production runs from the **release clone** `/home/achi/Programming/skinmaker-release` (systemd `skinmaker`); dev checkouts are the DSH checkout and the Codex clone. Tunnel `skinmaker` UUID `866fd5b7-5046-4fd7-80a1-2f7b0ae30502`; `cloudflared-skinmaker` and `skinmaker-cleanup.timer` active + enabled.
- CI/CD: self-hosted runner `skinmaker-home` (label `skinmaker-deploy`) runs `.github/workflows/deploy.yml` on every merge to `master`; auto-merge is enabled after 1 approval (`gh pr merge --auto --rebase`).
- Codex devbox: Docker container `skinmaker-codex`, SSH on tailnet `100.110.156.108:2222`, separate workspace `/home/achi/Programming/skinmaker-codex`; verified 513 tests + app health. The GUI's remote-project mode requires the remote CLI, so the host runs with `INSTALL_CODEX=1` (`codex-cli 0.164.0`); auth is pending. Partner key/Tailscale invite and the GUI connection are pending user actions.
- 2026-10-27: 메인 화면 `<h1>` 은 `마인크래프트 스킨 메이커` (PR #13 에서 `환영합니다!` 로 바꿨다가 이후 커밋에서 대체됨). 로컬 프리뷰는 `uvicorn` 이 저장소 루트 `.env` 를 자동으로 읽으므로(실제 환경변수 우선, pytest 제외) `set -a` 없이 `.venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8002` (8001 은 프로덕션 릴리스 클론) 또는 `cd frontend && npm run dev -- --host` (5173, ufw 허용됨).
- 2026-10-27: `SKINMAKER_TRANSPORT=mock` 만으로 로컬 생성이 끝까지 동작하도록 mock 기본 시나리오 추가 (PR #18, `skinmaker/vlm/mock.py` 의 `DEFAULT_SCENARIO` + `get_transport()` 주입; 테스트 주입 경로는 불변).
- 2026-10-27: 요청 경로 견고성 (PR #19) — `TransportError`(키 누락)를 500 대신 503 `ai_unavailable` 로 구조화, health 는 네트워크 프로브 없이 `configured()` 만 사용, RateLimiter 가 창당 1회 sweep 으로 만료 키 제거, YuNet 안내 메시지의 `None`/mkdir 부작용 제거, `measure` 독스트링 오타 수정.
- 2026-10-27: `.env` 자동 로드 + `frontend/dist` 상시 마운트 (PR #20) — `python-dotenv` 명시 의존성, 빌드 전에는 404·빌드 후 재시작 없이 서빙. `:8765` 수동 스모크에서 `set -a` 없이 health mock + 생성 200.
- 2026-10-27: 웹 slim 체형 (PR #21) — `skin_model=classic|slim` 폼/응답, `build`·`steps_sheets`·3D 뷰어 지오메트리 배선, UI 선택. 잘못된 값은 400 `bad_model`. 포즈는 계속 휴면.
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

- `test-windows` runs the same 539 tests on `windows-latest`; it is a required check.
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
- QA render: `docs/qa-render.md`
- This document: `docs/handover.md`

## 12. Session update (2026-10-27)

- 2026-10-27 (seven-issue cleanup, PR #19–#21): combined integration branch (PR #19 + #20 + #21) `pytest -q` → **534 passed in 191.52s** (통합 브랜치 당시 측정; 개별 PR 머지 후 master 535); `npm run lint` exit 0 and `npm run build` green (existing chunk warning). Manual uvicorn on `127.0.0.1:8766` with `SKINMAKER_TRANSPORT`/`SKINMAKER_PARSING` unset (no `set -a`) returned health `{"status":"ok","transport":"mock (오프라인)"}` and a slim generation HTTP 200 (`skin_model=slim`; 0 slim validation problems, 41 classic problems proving the 3px geometry). Risks: slim viewer mesh dimensions have no browser/phone visual check in this container; `/health` now reports configuration, not upstream reachability; merge order 19 → 20 → 21 expected, with handover updated in #21 after a combined run.

- PR #17 follow-up: explicitly center camera/conversion button text horizontally and vertically at widths ≤720px using flex alignment and centered multiline text. Reduce horizontal padding and allow long words to wrap so labels fit narrow panels. Frontend lint/build and whitespace check validate the change; phone visual check remains manual.

- PR #17 follow-up: use the user-supplied 1080×1920 PNG (`frontend/public/wallpaper-mobile.png`) as the mobile background at widths ≤720px, keeping the desktop wallpaper. Original attachment copied without editing; existing cover/center behavior applies. A/B: previously all widths used `/wallpaper.png`; now mobile uses `/wallpaper-mobile.png`. Frontend lint/build and whitespace check validate the change; phone visual check remains manual.

- PR #16 merged and deployed successfully (deployment run 40453371519); required test/test-windows/web checks passed and public health returned ok. Follow-up mobile UI: at viewport widths up to 720px, hide the site QR link and stack the filename below the centered file-selection button. Above 720px retain the desktop layout. A/B: QR previously visible and picker inline at all widths; now the two requested mobile-only changes apply. Verification: frontend lint/build and whitespace check; physical phone visual verification remains manual.

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

- 2026-10-27: mock 기본 시나리오 드리프트 수정 + 테스트 수 갱신. `DEFAULT_SCENARIO` 가 `beard`/`inner_top`/`neckwear` 를 빠뜨려 `SKINMAKER_TRANSPORT=mock` 실행마다 `uncertain=(beard, inner_top, neckwear)` 가 보고됐다 (주석은 플래그가 없다고 서술). 세 필드를 `none` 으로 채우고 회귀 테스트 `tests/test_s2.py::test_default_scenario_has_no_uncertain_fields` 를 추가했다 — 수정 전 시나리오에서 실패하고, `is_uncertain(validate(DEFAULT_SCENARIO)) == ()` 와 이중 질의 `classify` 의 `uncertain == ()` 를 함께 고정한다. 테스트 수는 이 브랜치(origin/master + 이 수정) 기준 **516** — README 의 513 은 PR #18 이후 두 테스트 뒤처져 있었고 handover 의 515 는 master 값이었다. `integration/seven-issues`(PR #19–#21 포함) 에서는 535 이므로, 그 PR 들이 머지되면 수치를 다시 갱신한다. 검증: `.venv/bin/python -m pytest -q` → **516 passed** (2:59).
- 2026-10-27: L2(오버레이) 헤어를 실루엣 복제에서 연결된 테이퍼 셸로 개정. 기존 L2 는 L1 머리 실루엣을 그대로 복제해 3D 에서 머리 전체가 불투명 블록으로 보였다. 이제 L1 이 실루엣 전체를 담당하고 L2 는 (a) 정수리 캡, (b) 앞면 크라운 밴드+사이드록+눈 위 가닥, (c) 옆/뒤 2행 캡 + 면별 4개 가닥(열마다 0-2행 짧아져 끝단이 불규칙), (d) 몸통 성긴 드레이프만 그린다. 모든 L2 픽셀은 같은 면의 이웃과 4-연결이라 떠 있는 1px 블록이 없고, 눈(4-5행)은 덮지 않는다. 톤은 L1 대비 밝게(1.10, 정수리 1.06) 해 층이 읽히게 했다.
- 공유 지오메트리: `frontend/src/skinModel.js` 로 UV rect/박스 생성을 추출 — 3D 뷰어와 QA 하네스가 같은 모델을 쓴다(기존 `test_viewer_js_uv_rects_match_layout` 검사 대상도 이 파일). 뷰어의 자동 회전/조명/머티리얼은 불변.
- QA 도구: `skinmaker/qarender.py` (+`frontend/qa/render.{html,js}`) — 헤드리스 Chrome 으로 약한 원근(fov 12°, 거리 24) front-right(+24° yaw/+30° pitch)와 back-right(+204°/+30°)를 렌더해 `front_right.png`, `back_right.png`, `contact_sheet.png`, `render.json` 을 쓴다. 사용법/카메라 계약은 `docs/qa-render.md`. 로컬 바이너리 스모크 테스트는 CI 에서 skip.
- 서브에이전트 시각 QA: 위 두 이미지로 1회전 — PASS. 보고서는 "L2 실루엣은 여전히 solid"라고 관찰했는데, 이는 L2 틈으로 같은 색의 L1 이 보이기 때문이고 텍스처 수준에서는 L2 137 vs L1 736 불투명 픽셀(약 19%)이다. 지적된 것은 기존 렌더러의 sub-pixel AA 이음새뿐이며 헤어 레이어 결함은 없다고 판정했다.
- A/B: 같은 사진/시나리오에서 수정 전에는 머리 전체가 단색 셸(정면 이목구비만 노출), 수정 후에는 정수리 볼륨 + 불규칙 끝단/가닥이 보이고 L1 이 아래에서 비친다. 골든 해시 재기록(2026-10-27). 검증: `pytest -q` → 539 passed(로컬, 브라우저 스모크 포함), `npm run lint`/`npm run build` green, `git diff --check` clean. 이 브랜치는 PR #19–#21 병합 후 `master` 기준이며 539 passed.

- 2026-10-27 (Git 감사): #19–#23 머지 후 테스트 수 갱신 커밋(b40ad7f/d56ab99/6a1044d)이 일괄 문자열 치환으로 무관한 값을 오염시켰다 — `ED25519`→`ED25539`, 배포 run `40453371519`→`40453371539`, 과거 세션 실행값 516/535→539. 해당 값을 원복했고, 세션 기록의 실행값은 측정 시점 기준으로 유지한다(현재 수치는 §2/README만 갱신). 현재 539 는 `pytest --collect-only -q` 로 확인했다. 교훈: 수치 갱신은 문맥별로 하고 일괄 치환하지 않는다.

- 2026-10-28: 하체 생성 정책 개편(jeans 기본·드레스·치마 밑단) + 배치 QA 도구.
  - 원인: 상반신 jeans 기본은 있었지만 (a) VLM bottom 결측 시 파서가 '하체 옷'과 '맨다리'를 구분하지 못해 `lower_body_seen=True` 하나로 뭉뚱그렸고, (b) `top_garment=dress` 는 명시적 가드로 `none`(맨다리), (c) 치마는 `BOTTOM_ROWS["skirt"]=(1,9)` 고정 1행이었다.
  - 증거/정책: `ObservedColors` 에 `lower_body_clothed`(5/6/7), `lower_body_bare`(12/13), `fullbody`(`quality.is_fullbody`), `skirt_hem_rows`, `skirt_sample`(5), `dress_sample`(7) 추가. `resolve_bottom_ex`: dress→`dress`(전체 다리), bottom 결측/빈값/null/none → clothed면 측정 바지, bare면 맨다리(D3 유지), 상반신/판단불가면 **jeans 기본**, fullbody+판단불가면 `none`. skirt→측정 hem, 유효 skirt/jeans/pants/shorts는 그대로.
  - 렌더: dress 는 0-8행을 드레스 색/패턴(몸통에서 v+12 연속)으로 채우고 hem 음영; skirt 는 측정 hem까지 치마색(마스크 색 우선)+hem 음영, 그 아래 피부; jeans/pants/shorts 경로 불변. hem 은 신발 시작선으로 정규화(발끝 기준이면 미디가 허벅지로 잘림)하고 skirt 픽셀이 옷의 20% 미만이면 옷 전체(Pants/Dress 오분류) 밑단을 쓴다.
  - 배치 도구: `skinmaker/batch.py` — 재귀 수집, resume, `--single`, `--replay`(저장된 VLM JSON 재처리, API 0회), `--render`, `result.json`/manifest/`qa_selection.json`, `compare.png`([원본|front|back]). 사용법은 `docs/qa-render.md` 확장.
  - Curated QA(37장 = 25 skirt + fixed10 + extras, Gemini 3.1 double): 33 ok / 4 no-face. 서브에이전트 3청크: upper-body jeans PASS, skirt 커버리지 PASS. 1차에서 미디 3장(401/404/419)이 짧게 렌더 → 신발선 정규화 후 5장 재검 **HEMS PASS**. dress 실사진 쌍은 없음(VLM이 dress 로 분류한 사진 0) — dress 는 unit/API 테스트로 고정.
  - General accuracy: 서브에이전트 FAIL — whites/creams 회색화, 피부 톤 어둡게, floral/plaid 소실·오배치(image413/421). 이는 하체 정책이 아니라 기존 색 측정/패턴 스키마(패턴 필드 1개)의 한계다. 후속 과제로 남긴다.
  - Full validation(2026-10-28, 277장 single query, Gemini 3.1, quota top-up 후): **236 ok / 41 no-face / 0 error**. 결정론 감사 0 실패 — default jeans 22장(모든 다리 9행 jeans), dress 5장(전 다리 커버, 렌더 육안 확인), skirt 33장(밑단 위 천/아래 피부). 신규 skirt 12장도 렌더 확인. image315(VLM skirt 인데 Skirt 픽셀 0·Dress 15%)는 knee fallback(6행)으로 보정. General accuracy 한계(색/패턴)는 별도 과제로 유지. (release `.env` 키는 환경변수로만 사용, 출력/커밋 없음.)
  - 검증: `pytest -q` → **567 passed**(3:22, 로컬). 프론트 변경 없음. 테스트: resolver/evidence/hem/render/batch/backend 계약.

- 2026-10-28 (패턴 충실도·크롭 천·유사도 스코어링, Phase 1–3):
  - graphic: 세부 정보 없는 graphic 태그가 그리던 `#f2f2f2` 4x4 사각형 제거. 크롭 천이 있으면 앞면에 적용하고, 없으면 측정 상의색 plain.
  - 두께: stripe/check/plaid 의 고정 2px 주기를 **1px 기본**으로 바꾸고, 몸통 run-length 로 측정한 `stripe_px`(1–3) 를 적용. 측정 불가는 1px.
  - 크롭 천(`skinmaker/texture.py`): SCHP 마스크 → 마스크 밀도×분산 최적 패치 → 8x12/4x12 → 12색 median-cut. HF 복잡도 게이트(플로럴 23.5·플레이드 20.1·흰 티 7.2·청바지 3.4, 임계 10). 상의는 VLM 복잡 pattern 또는 HF≥10, 하의는 HF≥10. 캔버스 미러가 좌우 팔다리 대칭을 유지. `ObservedColors.top_texture/bottom_texture`.
  - 스코어링(`skinmaker/score.py`): compare.png 를 VLM 에 보내 head/top/bottom/overall 1–10 + issues, worst→best ranking, resume/--jobs/--repeat, `out/qa_scores.json`. 문서는 `docs/qa-render.md`.
  - A/B(3-worst): image413 4.75→**6.0**(bottom 2→5), image421 4.5→**5.5**(bottom 3→4), floral dress 306 4.75→**6.0**(top 3→6, overall 4→6). 테스트 **588 passed**.
  - Phase 4(구조 태그 스키마 + zipper/button/collar/pocket 드로어)는 다음 단계.
