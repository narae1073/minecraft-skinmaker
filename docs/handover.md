# handover — skinmaker (2026-10-26, master)

## 1. Project in one paragraph

Photo → Minecraft 64×64 skin pipeline.
S0 quality/face detection (YuNet) → S1 colour measurement (white-balance + band/cascade) → SCHP human-parsing mask (colour localization for bottom/hair/shoes — default ON) → S2 classification (double query, uncertainty flags) → S3 parametric render (+ deterministic noise) → S4 candidates (1–3 variants from double-query disagreements) → web app (FastAPI + React 19 / three.js with 3D viewer and editor modal).

## 2. Current state (verified 2026-10-27)

- Tests: **628 passed** (`tests/fixtures/` committed; ~10 s without the SCHP model, ~3 min with it). Tests no longer need the 66 MB SCHP model: the jeans-rule tests stub a zero mask and `test_parsing` uses a dummy model path with a fake session.
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

- `test-windows` runs the same 628 tests on `windows-latest`; it is a required check.
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

- 2026-10-27 (Git 감사): #19–#23 머지 후 테스트 수 갱신 커밋(b40ad7f/d56ab99/6a1044d)이 일괄 문자열 치환으로 무관한 값을 오염시켰다 — `ED25519`→`ED25539`, 배포 run `40453371519`→`40453371539`, 과거 세션 실행값 516/535→539. 해당 값을 원복했고, 세션 기록의 실행값은 측정 시점 기준으로 유지한다(현재 수치는 §2/README만 갱신). 현재 628 는 `pytest --collect-only -q` 로 확인했다. 교훈: 수치 갱신은 문맥별로 하고 일괄 치환하지 않는다.

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

- 2026-10-28 (Phase 4, 하이브리드 구조):
  - VLM 스키마 확장: `closure_type`(none/zipper/buttons), `collar_type`(none/crew/v_neck/shirt/hood), `pocket_type`(none/patch), `symmetry`(symmetric/asymmetric), `pattern`+floral. top=none → 구조 필드 none 교차 규칙. 테스트 고정값/mock 기본 시나리오 갱신, Gemini 스키마/prompt 테스트 추가.
  - `skinmaker/structure.py`: 1px 지퍼(중앙 4열, 교대 이빨), 단추(u4 행 1/4/7/10 + placket u3), 칼라(crew/v/shirt/hood), 패치 주머니(1px 외곽). 크롭 천/패턴 위에, 긴 머리 드레이프 아래에 오버레이. VLM 태그가 없거나 none 이면 no-op; 셔츠 칼라+closure none 은 단추로 보수적 보정(지퍼 임의 추정 금지).
  - 크롭 개선: 창을 옷 bbox 중앙 35%로 고정(폰/손 오염 제거), 상의 크롭은 VLM pattern 복잡일 때만(흰 셔츠 주름 HF 10.2 오탐 방지), 하의는 HF 게이트 유지.
  - 실사진 A/B: 버튼 셔츠(연한 셔츠+placket/단추), 지퍼 재킷(1px 금속 지퍼), 블레이저(단추+패치 주머니), 플로럴 드레스(크롭 유지; 구조 태그 없음). 렌더는 `out/qa_structure_render2/`.
  - 테스트: `pytest -q` → **595 passed**. Phase 5: 277 재분류 **236 ok / 41 no-face / 0 error** → 236 렌더 + **236 스코어 / 0 error**. mean **5.87**, median **6.00** (head 5.81·top 5.84·bottom 6.07·overall 5.74), worst 2.25(images8/image142), best 8.75(141/146/161/169). `out/qa_scores.json`(gitignored) worst→best. 다음 우선순위: 피부톤 71·헤어색 63·안경 47·모자 ~28 이슈.

- 2026-10-29 (피부 톤): 아랫볼(수염·입술·긴머리) 표본이 피부를 어둡게 만들던 문제.
  - `measure_skin`: 코+윗볼(수염이 닿지 않는 영역)의 밝은 60% 중앙값을 영역별로 재고, **가장 밝은 유효 영역**을 선택. 난색 필터(R>G>B, 채도 0.035–0.60, 휘도 0.08–0.97)로 머리카락·장신구·회색 그림자를 거른다. 선택 휘도 <0.28(야간·역광)이면 기존 아랫볼 최빈색으로 폴백. WB 앵커는 기존 아랫볼 그대로(과보정 방지).
  - 표본 변화: messi5 `#8d7365→#b99692`, images10 `#b5756a→#de9b8f`, images15 `#e0b59d→#e9d6c5`, lena `#e27876→#ecb3aa`; 어두운 피부 images8 `#73635e→#6e5649`(난색 유지), image417/158(그늘·야간)은 기존값 유지.
  - A/B(10장 × 3회 중앙값): mean **4.38→4.62**, head **4.40→4.60**. images10 6.5→**8.0**(head 4→6), messi5 3.5→**4.25**(head 4→6), images15 3.25→**4.0**; images8/417/158/people/istock 유지. image141 8.75→8.0은 회귀(피부 외 요인 혼재).
  - 테스트: `pytest -q` → **598 passed**. 전체 236 재랭킹(동일 4축 rubric): mean **5.87→5.89**, head **5.81→5.90** (top 5.84→5.83·bottom 6.07→6.09·overall 5.74→5.75). 80 개선/74 악화/82 동일. skin 이슈 76→56, 'darker' 106→88, 'grey' 48→59. 표적: images10 8.0, messi5 4.25, images15 4.0. 회색/과보정 여지는 후속(채도/하이라이트 선택).

- 2026-10-29 (채도/하이라이트 패스): 밝기 최대 선택이 회색 하이라이트를 고르던 문제.
  - `measure_skin` 선택을 `0.5*lum + 1.5*chroma`(밝은 회색 감점)로 바꾸고, 채도 하한 0.05, 이마는 볼·코의 채도<0.10 또는 휘도<0.40일 때만 후보에 추가. 599 tests.
  - Full 236 3-state: mean old **5.87** / lightest **5.89** / sat **5.91**; head 5.81/5.90/5.90; bottom 6.07/6.09/6.18. sat vs lightest 57 개선/52 악화/127 동일. grey 48/59/**50**, skin 76/56/**60**, darker 106/88/**94**.
  - 표적: images10 8.0, messi 4.25, image410 5.0(light 4.25), ex3 4.75, image118 6.5; images15 3.25(light 4.0), lena 2.75, 417 3.25. 다음 우선순위는 여전히 헤어/안경/모자(이슈 다수).

- 2026-10-29 (헤어 L1/L2 구조 수정):
  - 원인: `render_head` 가 bottom 면을 항상 피부로 채움(205/236 스킨 bottom hair 0); `HairStencil.body_rows`/render cap 6, rule body_rows 0; L2 는 4열만 칠하는 sparse 셸이라 224/236 에서 인접 열 단차 8; L2 는 스타일 입력 없이 고정.
  - 수정: bottom 은 v0=앞(턱)·v7=뒤로 확인 후 뒤쪽 footprint 만 L1/L2 에 칠함(길이별 1/2/3/4행, 턱 피부 유지). `effective_hair_length`/`target_body_rows` 로 VLM long→6, very_long→10행(마스크 증거 최대 12), rule 폴백도 동일. L2 는 실루엣 전체를 채우는 solid 셸(알파 구멍 0), 세로 가닥 톤. 긴 머리 앞머리 2행 추가, body drape solid.
  - QA: `qarender --views hair` (front/back/bottom/right-side), `hairreport` 결정론 검사(bottom/구멍/점프/drape), `docs/qa-hair.md` 프롬프트. 10장 before/after: bottom 24/24, L2 holes 0(8/10), body long 6-12행; bald/dark-skin 2장은 리포트 한계/기존 bald 오류.
  - `pytest -q` → **608 passed**. Phase 4(스타일 스키마/드로어)는 다음 PR.

- 2026-10-29 (헤어 Phase 4, 스타일 스키마/드로어):
  - VLM 스키마 `hair_style`: short/pixie/bob/long_straight/long_wavy/curly/ponytail/bun. 값이 없거나 강제되면 길이에서 bob/long_straight/long_wavy 로 폴백(성별 추론 없음). mock/fixture/prompt/schema 테스트 갱신.
  - 스타일 드로어: short/pixie 0행 드레이프·2행 프린지, bob 3행 프린지·0행, long_straight 6행, long_wavy 8행+열별 1행 웨이브, curly 5행, ponytail 0행+뒤 중앙 2×5 strip, bun 0행+뒤통수 4×3 밝은 번. L2 solid/구멍 0 유지.
  - 실사진 10장 VLM 태그: long_straight 4·short 1·curly 1·long_wavy 1·ponytail 1·bun 2. 4-view 렌더 `out/qa_style_views/`. 테스트 **610 passed**. PR #28 위 스택(PR #29), merge 순서 28→29.

- 2026-10-29 (헤어 bang/front-back 재수정):
  - 원인: ① mask front 내부 1px 피부 구멍(ex5 row1) ② hairline row3 피부선(images18) ③ body_rows 하나를 앞/뒤가 공유, 앞은 2행 고정 ④ mask body_rows 12가 style 목표를 덮어 전신 back.
  - 수정: `close_front_holes`; full-fringe 스타일은 3-4행 전체를 채움(bob/long/curly 4, short/pixie 3, ponytail/bun 2). `style_drape` front/back 분리(long_straight 5/5, long_wavy 5/6, curly 3/4), back cap 6, 마스크 증거는 +1만·rule stencil 은 증거 아님. 앞 chest 는 바깥 2열 full, 안쪽 1열 −1.
  - A/B 10장: front holes 0(3장 4→0), row3 0→8, front chest 2→C-taper 5(long), back 10-12→5/6. hairreport 9/10 clean; people-2562408 만 dark-skin false positive(chin/holes).
  - `pytest -q` → **613 passed**. 4-view contacts `out/qa_hair_fix_views/`.

- 2026-10-29 (코드 무결성/UI 감사):
  - 문서: README/handover §2 의 현재 테스트 수를 **613**(실측 `pytest --collect-only -q`)으로, S2 필드를 8→**13**으로 수정. handover 169행의 539는 PR #19–21 시점의 역사값이라 유지(감사 기록 참고).
  - `texture.py` 의 shadowed `_complexity` 중복(첫 정의가 없는 `_dominant_colors` 참조) 제거. 동작 변화 없음.
  - `CategoryPanel.jsx`: 5필드→13필드 칩/표. hair_style/closure/collar/pocket/symmetry/beard/inner/neckwear 번역 추가, `pattern=floral` 추가. `derived` 파싱을 `=`→`:`로 수정(교차 규칙 `field:old->new`).
  - UI: 배경을 `html:root` 캔버스에 깔고 `min-height`+`background-attachment: scroll` 로 바꿔 긴 페이지 하단까지 덮음(1440x1886 풀페이지 확인). 모바일 upload-section/pannel 의 specificity 문제를 고쳐 세로 스택·버튼 full width 정렬. 원본 사진 다운로드 버튼은 후보 카드와 같은 `.card-actions` 로 중앙 정렬(사진/버튼 center 579px). 390x844/2000, 1440x1886 스크린샷 확인.
  - pose: `mediapipe` 선택 import, requirements 에 없음 — 휴면 상태 유지(의도). :8002 는 dist 를 현재 빌드로 갱신(정적 자산 현재); 백엔드 프로세스는 2일 전 mock 이라 재시작은 별도.
  - 검증: `pytest --collect-only -q` 613, `npm run lint`/`npm run build` green, `git diff --check` clean.

- 2026-10-31 (헤어 좌우 UV): right face 는 u7=앞, left face 는 u0=앞인데 두 side profile 을 같은 u0..7 순서로 써서 viewer-left 옆머리가 앞머리와 거꾸로 붙던 문제.
  - `side_profiles_from_front`: left 는 heights[7]→back 을 u0..7, right 는 heights[0]→back 을 뒤집어 u0..7. rule(상수) 경로는 불변.
  - 테스트: 코너 연속성, 비대칭 프로파일, right 미러. **614 passed**. A/B: `out/qa_hair_side_frontleft.png` (ex5/images28 front-left, before/after).

- 2026-10-31 (헤어 L2 세로 줄무늬 제거): `_l2_color` 가 `u%2` 로 1.20/1.10(정수리 1.12/1.06) 두 톤을 칠해 모든 머리에 규칙적인 세로 줄무늬를 만들던 것을, 균일 `L2_LIFT=1.05` 한 톤으로 교체. L1·L2 실루엣/볼륨은 유지, 색 줄무늬만 제거.
  - 골든 4개 재기록, no-stripe 회귀 테스트 추가. **615 passed**. A/B: `out/hair_stripe_compare.png` (uniform +2%/+5%, L1 match), 실제 렌더 `out/qa_hair_stripe_views/`.

- 2026-10-31 (reference pack — hair L2/eyes/hood): 사용자 제공 64×64 스킨 682장(긴머리 218·짧은머리 319·hood_up 100·hood_down 11; hat 34 제외, full-crown 24만 hood mask)에서 파생 패턴 팩 `assets/reference_pack.json`(22KB)을 만들었다. 원본 픽셀은 커밋하지 않고 라이선스 확인된 tone map/eye mask/hood mask만 저장.
  - Hair L2: 참조별 L2 톤을 열 평균으로 압축(2D 사각 패치 방지)해 damped column tone 적용. 기존 uniform fallback 유지.
  - Eyes: 좌안 template을 우안에 미러, sclera 2–4/iris 2–4만 채택(3 templates). 사진 iris 색으로 recoloring.
  - Hood: `hood` enum `none|up|down` 추가(14필드). up은 full-crown reference 24장에서 만든 **solid** L2 후드(정수리/뒤/옆 full, front 0–2 brim, 3–7 얼굴 opening)에 crown seam·highlight·brim shadow·side frame·shoulder cowl·drawstrings 디테일 + top_alt 트림 + snug/oversized/fur-lined 3 variants (fur는 crown ring 대신 front brim 전체 폭의 연속 band로 제한 — 큐브 edge sliver 제거. 원인은 후드가 아니라 **후드 뒤에 적용되는 noise pass**: 1-3px block noise가 solid crown을 4x4 grid로 보이게 했다. hood overlay를 noise 뒤로 이동해 crown을 solid로 유지. QA subagent가 놓친 이유: QA 렌더에 noise_seed가 없었고 prompt에 pixel hygiene/noise 조건이 없었다. `docs/qa-hair.md` G(pixel hygiene, noise0+50) 추가. pixel QA: front brim 8px 단일 성분, top/side/back light 0); sparse hair mask는 버린다. down은 body L2 cowl. 참조 팩 4 up/2 down.
  - 한계: 참조가 unpaired(사진→스킨 매핑 없음), 코퍼스가 anime/costume 편중, eye/hood 패턴은 1차 근사. VLM/score 재랭킹은 미실행. 테스트 **628 passed**, frontend lint/build green.
