# handover — skinmaker (2026-10-26, master)

## 1. Project in one paragraph

Photo → Minecraft 64×64 skin pipeline.
S0 quality/face detection (YuNet) → S1 colour measurement (white-balance + band/cascade) → SCHP human-parsing mask (colour localization for bottom/hair/shoes — default ON) → S2 classification (double query, uncertainty flags) → S3 parametric render (+ deterministic noise) → S4 candidates (1–3 variants from double-query disagreements) → web app (FastAPI + React 19 / three.js with 3D viewer and editor modal).

## 2. Current state (verified 2026-11-04)

- Tests: **728 passed** (`tests/fixtures/` committed; 124 s on 2026-11-04 with the local SCHP model; ~10 s without it). Tests no longer need the 66 MB SCHP model: the jeans-rule tests stub a zero mask and `test_parsing` uses a dummy model path with a fake session.
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
- 2026-11-04: "스킨 변환하기" 버튼이 요청을 아예 보내지 않던 버그 수정 — `onClick={handleGenerate}` 가 클릭 이벤트를 `cropBox` 로 넘겨 `JSON.stringify` 가 try 밖에서 던졌고, 가짜 진행 타이머만 92% 를 향해 기어갔다. 이제 진행바는 SSE 실제 진행률만 쓰고, SSE 에러 객체 메시지·`no_face` 크롭 모달도 처리한다. 업로드 전 1600px 로 축소(`shrinkImage`).
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

- `test-windows` runs the same 657 tests on `windows-latest`; it is a required check.
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

- 2026-10-27 (Git 감사): #19–#23 머지 후 테스트 수 갱신 커밋(b40ad7f/d56ab99/6a1044d)이 일괄 문자열 치환으로 무관한 값을 오염시켰다 — `ED25519`→`ED25539`, 배포 run `40453371519`→`40453371539`, 과거 세션 실행값 516/535→539. 해당 값을 원복했고, 세션 기록의 실행값은 측정 시점 기준으로 유지한다(현재 수치는 §2/README만 갱신). 현재 657 는 `pytest --collect-only -q` 로 확인했다. 교훈: 수치 갱신은 문맥별로 하고 일괄 치환하지 않는다.

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
  - 한계: 참조가 unpaired(사진→스킨 매핑 없음), 코퍼스가 anime/costume 편중, eye/hood 패턴은 1차 근사. VLM/score 재랭킹은 미실행. 테스트 **657 passed**, frontend lint/build green.

- 2026-10-31 (수염 렌더 제거): 사용자 지시 "don't draw beard". `render_head` 의 beard full/stubble 페인트 블록 삭제. `beard` 분류 필드는 API/스키마 호환을 위해 유지하지만 픽셀은 그리지 않는다. `test_beard_is_not_drawn` 추가, full/stubble 모두 턱 6-7행이 피부. **627 passed**.

- 2026-10-31 (production benchmark/roadmap): 원안의 "holdout 스킨 유사도"는 unpaired라 photo→skin 품질 게이트로 부적합하다고 판정. `docs/production-roadmap.md`에 재정의한 goal/gates와 Phase 0–5 기록.
  - `skinmaker/reference_qa.py` + `scripts/build_reference_benchmark.py`: 결정론적 stratified split **550 train / 98 holdout**(hat 34 제외), template shape/structural QA, holdout style-coverage baseline.
  - committed pack을 train-only(550)로 재빌드하고 split metadata를 기록; 98 holdout은 unseen. train-only coverage: hair n=98 mean0.061 p90 **0.080**; eyes n=3·hood_up n=3·hood_down n=0 → 샘플 부족; paired photo→skin benchmark 없음.
  - **630 passed**. 다음: eye/hood extraction 확대, train-only production pack, 30–50 paired pilot.

- 2026-11-01 (Phase 2 eye-quality gate): eye extractor를 완화하면 holdout coverage가 n=3→93으로 뛰었지만 zero-sclera iris-only template이 대량 생성됐다(품질 악화). 이를 **metric gaming**으로 판정해 완화 extractor를 되돌리고 `reference_qa`에 `quality_ok`/`template_quality` gate를 추가했다. zero-sclera eye를 거부하는 회귀 테스트 추가. **631 passed**. 다음: 수동/seed label 기반 eye template curation, hood_down 보강.

- 2026-11-01 (paired benchmark scaffold): `skinmaker/paired_benchmark.py` + `scripts/check_paired_benchmark.py` + `docs/paired-benchmark.md`. Hand-approved pairs only; unapproved candidates do not count. 10-photo current-output pilot seeded in `out/paired_benchmark` (0 approved, accepted=false — honest). Tests **633 passed**. Next: 30–50 approved pairs and human preference scoring.

- 2026-11-01 (paired review workflow): `scripts/build_pair_review.py`가 [photo | front | back] 10-pair sheet(`out/paired_benchmark/review_sheet.png`)를 생성; `set_approval`/`review_pairs.py`로 human approve/reject. Pilot 10장은 모두 approved=false(현재 출력은 hand-approved ground truth가 아님). **634 passed**.

- 2026-11-01 (deterministic production QA matrix): `skinmaker/production_qa.py` + `scripts/run_production_qa.py` + `docs/production-qa.md`. 49 cases (8 styles × 3 hoods × noise 0/50 + beard full) check validate_image, beard absence (side hair allowed, noise tolerance), both eyes, hood-up isolated-pixel islands, eye-row hood coverage. **636 passed**, matrix ok.

- 2026-11-01 (template review queue): eye/hood candidate gallery(`out/production_benchmark/template_gallery.png`) + `scripts/review_templates.py`/approval manifest. Train-only **19 eye, 1 hood-up, 3 hood-down** candidates; all unapproved. Production pack stays strict/quality-gated. Tests **637 passed**.

- 2026-11-01 (production gate): `skinmaker/production_status.py` + `scripts/production_status.py` aggregate all gates fail-closed. Current status ready=false, blockers: eye/hood holdout n, 0 approved templates, 0 approved paired examples. **639 passed**. Release gate is not wired to CI while human approvals are zero.

- 2026-11-01 (approval→pack integration): `apply_template_approvals` + `build_reference_pack --candidates/--approvals`; only human-approved eye/hood candidates replace pack patterns (none approved yet, so pack unchanged). **640 passed**.

- 2026-11-01 (eye candidate shortlist): train-only 19 eye candidates ranked by objective readability (both eyes, sclera/iris support, adjacency). 6 `recommended=true` **shortlist only**, not approval; gallery/JSON updated. **641 passed**. Gate still blocked on human approvals.

- 2026-11-01 (eye preview): shortlisted eye candidates rendered on a neutral face (`out/production_benchmark/eye_preview.png`) beside mask gallery. Still review-only, 0 approved. **642 passed**.

- 2026-11-01 (user approvals + eye placement): user approved 4 eyes (including 2 zero-sclera anime eyes). Pack rebuilt from approvals; `quality_ok` now allows only explicitly approved zero-sclera templates. All eyes moved to rows **5–6** (one row above chin row7); hooded renders initially selected only non-hood reference eye templates; this was later replaced by weighted all-approved eye selection (c252 ~60%). Beard remains undrawn. **645 passed**.

- 2026-11-01 (eye frequency): all approved eyes eligible for hooded/non-hooded; weighted eye selection `assets/eye_weights.json` makes **c252 ~60%**, 463 20%, 0eb/7de 10% each. This replaces the hood-source filter that left only 463 on hooded renders. Goldens updated, 645 passed.

- 2026-11-01 (L1/L2 bangs policy): current hair shape is still VLM style + SCHP/rule stencil; reference pack supplies tones but not shape. Implemented bounded eyebrow-cover policy: loose bob/long_straight/long_wavy/curly get 5-row fringe covering eyebrow row4 (eyes rows5-6 stay visible), short/pixie stay 3 rows, tied-up ponytail/bun 2 rows. Production QA now enforces loose-vs-exposed policy. **645 passed**. Reference-pixel bang-depth extraction was too noisy; a labeled bang benchmark is needed next.

- 2026-11-01 (L2 hair depth): increased reference column-tone contrast (0.55→0.80, clamp 85–115) and added a connected 1px L2 edge outline at face-opening/silhouette boundaries (colour only, no alpha holes). Hair still covers eyebrow row for loose styles; eyes rows5-6 visible. Goldens updated, **645 passed**.

- 2026-11-01 (limited L2 eye fringe): loose no-hood outputs may now add a 1px L2 fringe over the **top** eye row (row5) for u1/6, seeded ~1/3; bottom eye row6 is always protected. This follows the user allowance for slight L2 eye coverage. Goldens/tests updated; **646 passed**.

- 2026-11-01 (exposure-aware short bangs): short/pixie now become a 5-row eyebrow-covering fringe only when the SCHP/rule front hairline visibly has bangs at rows3-4 center; otherwise they stay 3-row/exposed. Loose and tied-up rules unchanged. **647 passed**.

- 2026-11-01 (reference bang tips): pack now stores the three most frequent reference L2 row4 patterns (dominant `11011011`). Loose 5-row fringes use the selected tip mask as transparent L2 notches, revealing L1 hair (not skin). Goldens updated; **648 passed**.

- 2026-11-01 (bang benchmark): train-only 60-head bang/exposure review sheet (`out/production_benchmark/bang_review_sheet.png`) + label tool. Automatic reference bang classification was too noisy; no renderer policy will be tuned until manual labels exist. **649 passed**.

- 2026-11-01 (fringe profile): replaced the flat fringe block with a per-column profile `(4,5,5,5,5,5,5,4)` for loose/visible bangs; all inner columns cover eyebrow row4, outer corners shorter. Short exposed `(0,3,3,...)`, tied `(0,2,2,...)`. Goldens/tests updated; **650 passed**.

- 2026-11-01 (bang label guard): `label_quality` rejects collapsed label sets; agent labels 19/20 depth5+covered are unusable, so no prior was fitted. **651 passed**. Human/proper labels still required.

- 2026-11-01 (eye reference blocklist + bang labels): five reference sources with 3px/asymmetric pupils (c5e01…, fc8b…, dd3d…, 02ac…, 5d742…) are blocklisted from eye-template extraction only; hair/bang data stays. 60 bang labels are present but the depth distribution is 54/60 at depth5, so `label_quality` still marks them unusable for a prior. **652 passed**.

- 2026-11-01 (long-bang prior accepted): 60 human labels are 90% depth5; guard now allows a dominant style, rejecting only >95% collapse or >20% depth/exposure contradictions. `assets/bang_prior.json` records median5 for long and short. No forced depth-4 variety (only 1/60 reference). **654 passed**.

- 2026-11-01 (reference edge notches): pack stores dominant L2 outer-edge patterns for right/left/back; renderer removes L2 cells only at lower silhouette edges (v>=4), revealing L1 hair. `hairreport` now separates intentional `strand_notches` from defect holes. 60-label long-bang prior accepted (median5). **655 passed**.

- 2026-11-01 (prior-driven depth): `STYLE_BANGS` now loads the long/short median from `assets/bang_prior.json` instead of hardcoding 5. Current median is 5, so goldens are unchanged. SCHP/exposure exceptions still override for short/pixie. **656 passed**.

- 2026-11-01 (interior tone strand): one reference-derived accent column per head face (largest column-tone residual, seeded among top two) is darkened 10% on rows2+ on L2. Colour-only: no alpha holes, no eye/QA changes. Goldens updated; **656 passed**.

- 2026-11-01 (length-specific edge masks): `edge_masks_by_length` stores long/short L2 outer-edge patterns; renderer selects by effective length. Top patterns match the prior aggregate, so goldens are unchanged. **657 passed**.

- 2026-11-01 (hair A/B + highlight): added `scripts/build_hair_ab.py` and read the sheet: center depth5 is right, L2 is mostly solid (no supported interior alpha holes), current is still flatter/darker. Tapered outer corners to `(3,4,5,5,5,5,4,3)` and added one reference-tone dark + light accent column per face. **657 passed**.

- 2026-11-01 (A/B bug + accent): A/B script originally cropped L1 only, hiding L2; fixed composite. Forced one seeded dark accent on flat front/top patterns and strengthened dark/light to 0.85/1.12; loose corners taper to (3,4,5,5,5,5,4,3). Corrected A/B shows L2 highlights/notches; still flatter than refs. 657 tests.

- 2026-11-01 (rejected silhouette clear): clearing stencil front side hair outside the bang profile created bald temple gaps; reverted. Profile remains additive over photo-derived side hair. No code change; 657 tests.

- 2026-11-01 (additive side locks): bob/long loose no-hood fronts get one L2 hair column at u0/u7 rows3-6 when the edge is empty; adds side volume without erasing SCHP hair or touching eyes. Bob golden changed. 657 tests.

- 2026-11-01 (body-drape accents): the reference dark/light accent columns now also apply to long-style body hair (v>=1), not only the head. Head goldens for long/very_long changed; no eye/QA change. 657 tests.

- 2026-11-01 (side/back A/B + flat accents): side/back sheet added; flat reference tone maps on side/back now get one dark + one light accent. Only very_long golden changed; side/back remain dark. 657 tests.

- 2026-11-01 (L2 hair = reference sculpt, branch `feat/hair-l2-masks`, stacked on #34): measured all 537 long/short reference skins. Reference L2 is **sparse**, not a silhouette copy — median L2 coverage top 0.12 / right 0.20 / back 0.38 / front 0.45; no reference face ≥0.95; ~35% of front L2 sits over skin (fringe/temple locks extend past L1); L2 colour = L1 colour underneath (ratio 1.00, fringe ~1.02–1.12). Our solid shell was top 1.00 / sides 0.75–0.98. The earlier "refs are mostly solid" note (A/B entry above) came from front composites only and is wrong.
  - Pack: `hair_masks` = whole-head L2 masks (hair-coloured cells only; bows/clips rejected) → deterministic Hamming k-medoids → per-cluster majority vote; clusters <10 members dropped. Train-only rebuild is otherwise byte-identical. Long 131/45, short 234/19.
  - Renderer: `_template_head_l2` draws the template clipped to photo hair (top/sides/back/bottom only over L1 hair; front over L1 hair, inside style bang depth, or loose-style temple columns; eye rows 5–6 u1–6 never). Same colour as L1 (+4% fringe). Old head code is `_legacy_head_l2` (pack without masks only). Head edge-darkening pass now body-only on the template path. Body drape unchanged.
  - QA: `hairreport` no longer counts uncovered L1 under L2 as a problem; flags `solid L2 shell` (any of top/sides/back ≥90%) instead.
  - After: top 0.12, front 0.16–0.38, sides 0.06–0.12, back 0.12–0.28. A/B: `out/hair_l2_masks/` (`ba3d.png` 3D before/after/ref, `ours.png`, `masks.png`, scripts).
  - Findings for next steps: (1) density-tercile consensus collapses to the same skeleton — the references hold **one** shared L2 shape, not per-style shapes; style differences must come from L1 / body / labelled extras. (2) Reference L1 holds the strand shading (5–7 tones on sides); our L1 is flat → next step. (3) SCHP 8×8 projection gives 1-row forehead and ragged 4–8-row sides vs refs' 3-row L1 front and full sides; consider SCHP for colour/length/bangs only. (4) Body drape L2 is still a solid copy (refs body-back L2 median 0.33).

- 2026-11-01 (L1 hair = reference shading, step 3 on `feat/hair-l2-masks`): reference L1 hair is shaded, not flat — sides/back: sheen band rows 2-3 (+4%) darkening to −12% at row 7 (row variance share 0.47-0.58) plus alternating 1-2px strand columns (±5%); 11-14 colours per face. Artists keep **absolute** spread ~constant (side p10-p90 luma span 14 for near-black hair → 28 for light; relative 0.84 vs 0.13), so ratios would vanish on dark hair (113 refs are near-black).
  - Pack: `hair_l1_tones` = whole-head luma-delta maps (top/front/right/left/back; skins with ≥85% hair sides only), k-medoids, **medoid itself** kept (averaging blurs strands), clusters <10 dropped → 3 maps (177/123/39). `hair_masks` unchanged by the `_kmedoids` refactor.
  - Render: `_hair_tone` adds delta × target(luma)/17 (`L1_TONE_SPAN_DARK/LIGHT`=14/28, `L1_TONE_PACK_SPAN`=17 measured). Rendered weighted span 12.6/17.4/28.8 for dark/mid/light vs refs 14/~20/28. Template L2 uses the same tone as the L1 cell beneath (+4% fringe). Head bottom stays flat.
  - **Policy change:** reference-shaded head hair (L1 hair cells + head L2) is exempt from the block-noise pass — 2-3px noise squares fought the strands and refs have none. Rest of the skin still gets noise; pack-less renders unchanged. The UI "픽셀 질감" help text may need a note.
  - Goldens updated; A/B: `out/hair_l2_masks/s3_flat.png` (2D head, before|after), `s3_3d.png`, `l1deltas.png`.

- 2026-11-01 (L1 hair shape = reference skeleton, step 4 on `feat/hair-l2-masks`): reference L1 hair silhouettes are near-identical (60% majority vote, train-only): back 8 rows for **short and long**; sides full except a front-edge notch — short `right 8,8,8,8,8,5,5,7` (ear), long `8,8,8,8,8,8,8,5`; front depth short `7,5,3,3,3,3,5,7`, long `5,4,3,3,3,3,4,5`. SCHP's 8×8 projection gave 1-row foreheads, 4–8-row staircase sides, and 8-row cheek columns.
  - Pack `hair_l1_shape` {short, long}; `select_l1_shape` buckets by style (ears exposed: short/pixie/ponytail/bun; covered: bob/long_*/curly).
  - `HS.reference_stencil(shape, photo_stencil)`: shape from the pack; from the photo only bald (kept as-is), `body_rows`, bottom footprint, and `bangs_evidence` (SCHP centre rows 3-4, still drives short/pixie 3 vs 5-row fringe). Applied in `render()` after the style is resolved, for SCHP and rule stencils alike. So `hair_source`/`hair_symmetry` UI options no longer change the head silhouette — only evidence. Consider simplifying/removing them.
  - `hairreport` side-jump check now covers u0-u4 only (the front 3 columns carry the reference notch). Hood-up now clears its face opening on L2 (hair L2 had poked through at u1 rows 3-4).
  - **Open bug (not fixed): head bottom UV orientation.** All 456 refs paint bottom row 7 like front row 7 (edges hair, centre skin: 94/36/32/31/31/32/36/94 vs 94/34/31/30/30/32/35/95) and row 0 like the back. Artists check in Minecraft, so in-game bottom v7 = chin. Our three.js viewer maps `ny` with v0 = front (BoxGeometry), and the renderer/hairreport follow it — so we paint hair under the chin in-game. Fix needs renderer + `skinModel.js` + `hairreport` together; verify with one skin in real Minecraft first.
  - 668 passed, production QA 49 ok. A/B: `out/hair_l2_masks/s4_real.png` (photo | step3 | step4 on 5 real SCHP photos), `s4_3d.png`.

- 2026-11-01 (chin fix + reference body drape + UI cleanup, branch `feat/hair-chin-drape-ui`):
  - **Head bottom orientation fixed** (user decision: trust the 456 refs, no in-game test). Minecraft maps bottom faces with v reversed vs top: texture row 7 = chin/front, row 0 = back. `render.bottom_row(v)` converts the stencil's physical rows (v0 = chin) to texture rows at every write; template L2 converts back for clipping; `hairreport` chin = texture rows 4-7, rear = rows 0..rear-1. Viewer `skinModel.js` swaps `ny` UV rows for **all** parts (marker skin verified: row 0 meets the back face). Previous skins had hair under the chin in-game.
  - **Body drape = reference** (user decision: reference length). Long refs (185): back L1 12 rows (u0/u7 11), chest locks u0-1/u6-7 10-11 rows, side faces edge columns only; L2 strand bands back u1 / u3-4 / u6, front u1/u6. Pack `hair_body` {l1_depth, l2_mask (50% vote), tones (body luma-delta medoids, 1 cluster of 102)}. `long_straight`/`long_wavy`/`curly` share it (`HS.REF_DRAPE_STYLES`, `STYLE_DRAPE` (11, 12)); SCHP body evidence no longer changes their length; long_wavy wave shell and body edge-darkening are legacy-only. Body drape hair is exempt from block noise like the head.
  - **Straight vs wavy dropped** (user decision): VLM enum unchanged, rendering identical.
  - **UI**: removed 헤어스타일 표현 / 머리 좌우 모양 controls. Backend still accepts `hair_source`/`hair_symmetry` but ignores them (echoes mask/symmetrized); `hair_overlay` validation unchanged.
  - `hairreport`: drape length measured on L1 (`DRAPE_TOL` 45 for shaded drape); reference-drape styles cap at 12.
  - 670 passed, production QA 49 ok, lint clean, build ok. A/B: `out/hair_l2_masks/drape_3d.png`, `chin_ab.png`, `chin_marker_bottom.png`.

- 2026-11-01 (deepseek 재탐색/작업 브랜치): 사용자 지시("코드를 재탐색하고 앞으로의 작업을 위해 deepseek branch를 열어")로 Claude 세션 이후 상태를 다시 확인하고 `deepseek` 브랜치를 열었다.
  - 기준: `origin/master` = `fc39cf0` (PR #36 머지). 종전 워크트리 `feat/hair-chin-drape-ui`(`084d7b5`)와 `git diff` 0 — 로컬 트리는 이미 master와 내용이 동일했다. `deepseek` 는 `origin/master` 에서 생성했고 업스트림은 `origin/deepseek` 로 둔다.
  - 검증: `.venv/bin/python -m pytest -q` → **670 passed in 245.69s** (2026-11-01 20:52 KST, SCHP 모델 포함). `pytest --collect-only -q` → 670. README/§2 의 657 은 낡은 값이라 670 으로 갱신했고, 과거 세션 기록값은 감사 교훈대로 건드리지 않았다.
  - 구조 재확인: `format.py`(UV 정본) → `colors.py`(WB·군집·마스크 근거) → `attributes`/`classify`(14필드 이중 질의) → `render.py`(reference pack 의 L1 shape/tones + L2 mask + body drape, 이후 hood/noise) → `candidates.py`; 웹은 `backend/app.py` 단일 `POST /api/v1/generate-skin` + `frontend/src/App.jsx`/`Skin3DViewer`/`skinModel.js`. QA 게이트는 `production_qa.py`(49 케이스), `reference_qa.py`(train/holdout), `paired_benchmark.py`, `production_status.py`(fail-closed).
  - 게이트 재실행: `scripts/production_status.py` → `ready=false`. blockers = eye/hood holdout 부족(eyes<20, hood_up<10, hood_down<5) + hood_up 0/2·hood_down 0/1 승인 + paired 0/30. eyes 4개만 승인됨 — 코드 문제가 아니라 **인간 라벨/승인 대기**다.
  - 남은 리스크: `hair_source`/`hair_symmetry` 는 API가 받고 응답에 에코하지만 렌더에는 쓰이지 않는다(하위호환); `pose.py` 는 휴면(mediapipe 제거); 미추적 `docs/pipeline_overview_ko.md` 는 2026-10-29·610 tests 기준이라 현재와 어긋난다(커밋 여부는 사용자 판단).
  - 이번 커밋은 README/handover 문서만 변경하며 코드·에셋은 무변경. 이후 실제 작업은 기존 `feat/*` PR 흐름을 유지한다.

- 2026-11-01 (hood-up + 긴 머리 렌더 수정, `deepseek`): 프로덕션에서 후드 업 + 긴 흑발 사진이 ① 앞 chest lock 이 머리 바로 아래 2행에서 절단되고 ② 뒷머리 드레이프가 후드 위로 노출됐다.
  - 원인: `render_body`/`render_hair_overlay` 가 hood 와 무관하게 reference drape(back 12행, front u0-1/u6-7 11행)를 그리고, `render_hood_overlay` 의 cowl(L2 front/back rows 0-1~2)이 front lock 상단을 덮었다. 후드는 L2, 머리는 L1 이라 옷이 머리 위에 그려진 것.
  - 수정: hood up 에서 `hide_back_drape` — body back 전체 + side face 의 뒤쪽 edge column 만 제거(right u0=뒤·left u0=앞, 앞쪽 edge 는 유지). front lock 은 유지하고 hood cowl 이 `body_hair_cells` 를 덮지 않게 skip (머리는 옷 위로 떨어진다). ponytail tail·long_wavy legacy tail 도 hood up 에서 숨김. hood down 의 front cowl 도 같은 skip 을 적용.
  - 검증: 신규 테스트 2개(hood-up back hair 0 / chest lock row0 / side edge 방향), production QA 49 ok. QA matrix 에 hood-up back-hair·chest-lock gate 를 추가했고, 수정 전 코드에 같은 gate 를 돌려 `ok=False`(`hood-up back hair at (0,0)`)로 회귀를 잡는 것을 확인했다.
  - A/B: `out/hood_bug/compare_3d.png` (before | after, front/back), `before.png` / `after.png`. **672 passed** (241.61s), production QA 49 ok. 코드 변경: `render.py`, `production_qa.py`, `tests/test_render.py`.

- 2026-11-01 (hood-down 참조 cowl, `feat/hood-down-cowl`, #37 위 stack): 후드 다운이 참조 팩의 `hoods.down` 마스크를 선택만 하고 쓰지 않아, 8×3 솔리드 front 밴드가 상의 패턴 상단 3행(스트라이프 등)을 덮었다.
  - 수정: down 경로가 선택된 마스크의 front/back 셀만 그린다. 위쪽 edge 셀은 `top_alt` fold rim, 나머지는 top 10% 어둡게. body hair 셀은 skip (머리는 옷 위). `production_qa` 에 down front L2 ≤8셀 gate 추가 — 수정 전 코드에서 24셀 red 확인.
  - 검증: **673 passed** (240.72s), production QA 49 ok. A/B: `out/hood_bug/down_compare.png` (stripe/plain before|after), `down_3d_zoom.png`.

- 2026-11-01 (결과 미리보기 모달 제거 + 뷰어 고정, `feat/viewer-ui`, #38 위 stack): 사용자 지시 3건 — ① 변환 후 완성 미리보기 창 제거 ② 자동 회전 제거(마우스 전용) ③ 조명 변화 제거(가장 밝은 고정 조명).
  - `SkinPreview.jsx`·`previewOpen` 상태·모달 CSS 삭제. 생성 결과는 기존 `.result-section` 에 즉시 표시되고 "미리보기 다시 열기" 버튼도 제거.
  - `Skin3DViewer`: `useFrame` 자동 회전 제거 → `OrbitControls` 마우스 드래그로만 회전. 조명은 `ambient 1.1` + key `directional 1.8` + fill `0.7` 고정(조명 애니메이션 없음).
  - 검증: `npm run lint` / `npm run build` green. Headless CDP 실측: 실사진 생성 후 `.skin-preview-dialog` 0개·"미리보기 다시 열기" 없음, 뷰어 2.5s 간격 스크린샷 **픽셀 동일**(자동 회전/조명 변화 0), 마우스 드래그 후 diff 발생(수동 회전 정상). 스크린샷 `out/ui_test/`.

- 2026-11-01 (template-variant QA coverage, `feat/qa-templates`): 로드맵 item 4 — 49-case matrix 는 스타일당 시드 1개라 hood up 4종/down 2종/eyes 4종 중 일부만 검증했다.
  - `tests/test_production_qa.py`: 팩의 모든 hood 템플릿을 강제 선택해 noise 0/50%에서 `_check` invariant 검증, 모든 eye 템플릿을 강제해 양안/row6 L2 clear 검증. 템플릿 수(4/2/4)를 pin 해 팩 재빌드 시 리뷰를 강제.
  - 검증: **675 passed** (273.77s). 코드 무변경(테스트만); release gate 의 49-case report 는 그대로.

- 2026-11-01 (deprecated hair params 제거, `fix/hair-params`): `hair_source`/`hair_symmetry` 폼·응답 필드를 제거했다. reference skeleton 도입(2026-11-01) 이후 렌더에 영향이 없던 잔재이며, 내부 `extract` 인자는 유지한다(`tests/test_colors.py` 가 계속 검증). 구클라이언트가 보내도 FastAPI가 무시하고 200; `hair_overlay` 만 응답에 남는다.
  - 검증: **675 passed** (266.03s). backend 계약 테스트 갱신: legacy 필드를 보내도 200·응답에 없음, `hair_overlay` 가비지는 400.

- 2026-11-01 (slim-geometry QA, `feat/slim-qa`): `production_qa` 가 classic 만 검사하던 공백. slim 1케이스(hood up, long hair, noise 0) 추가, `_check(model=)` 로 `validate_image(model)`; 사용하지 않던 `get_layout` 제거. **50 cases**.
  - 검증: 50 cases ok, **675 passed**. 문서(`production-roadmap`, `production-status`, `production-qa`)의 49-case 표기도 50으로 갱신.

- 2026-11-02 (모바일 결과 가시성, `fix/mobile-result-scroll`): 미리보기 모달 제거 후 모바일에서 변환 결과가 화면 밖에 남는 회귀(scrollY=0, result top=919 > viewport 701). 결과 섹션이 뷰포트 아래일 때만 `scrollIntoView`(reduced-motion 존중), 이미 보이면 스크롤하지 않는다.
  - 검증: headless CDP 모바일 창 before `scrollY=0/top=919` → after `scrollY=919/top=0`; `npm run lint`/`build` green.

- 2026-11-02 (파이프라인 개요 갱신, P1-7): `docs/pipeline_overview_ko.md`를 2026-10-29 초안(1df10c7/610 tests)에서 현재 master(226ce53/675 tests) 기준으로 갱신했다. 14필드, reference pack(L1 스켈레톤/음영 톤/L2 마스크/body drape), head bottom row7, 후드 up/down, API 정리(`hair_source`/`hair_symmetry` 제거), 웹 UI(모달 제거·고정 조명·모바일 스크롤), QA 50 cases, 프로덕션 게이트/인게임/스코어링 항목을 반영하고 §8 변경 요약을 추가했다.
  - 검증: 문서 내 stale 수치(610/539/13필드/5필드/8×8 스텐실) 제거, `git diff --cached --check` clean. 문서-only 변경(테스트 수 불변).

- 2026-11-02 (production gate v2 / 라운드 종료, `feat/gate-v2`): D1–D7 결정을 코드·테스트·문서로 고정.
  - D1 eyes holdout-n **면제**(user-accepted, data-limited; approved eyes 4는 유지), D2 hood_down **n≥5 + p90≤0.25**(count-only 통과 금지), D3 hood_up **n≥3**(코퍼스 상한; 10은 데이터 필요), D5 pack v2 **보류**(v1 split/pack 유지), D6 라벨 불일치 3쌍 stratum 제외(pair 보존).
  - D4 활성 팩 리뷰 시트 `out/production_benchmark/pack_review/review_sheet.png`(up 4 / down 2) 작성 — **사람 승인만 남음**.
  - D7 결과: gate v2 `ready=false`; blockers = hood_down n, approved up 0/2, down 0/1. paired **72/30 accepted**. 근거·잔여 리스크는 `docs/production-gate-v2.md`.
  - 검증: **676 passed** (242.20s), `tests/test_production_status.py` 3 (eyes waiver + hood_down p90 gate).

- 2026-11-02 (후드 형상 수정, `fix/hood-shape`): 사용자 피드백 — "모든 hood up이 너무 깊고, 모든 hood down은 목 뒤에 후드가 없다".
  - **up**: `render_hood_overlay` 개구부를 3/4행 → **2행**으로 올리고 brim을 row 1로 내려 이마/앞머리를 노출. 팩 up 템플릿 4개는 front mask가 rows 0-2 full로 동일하고 **렌더에 쓰이지 않는다**(절차적 풀셸) — 템플릿 승인만으로는 모양이 바뀌지 않는다는 사실을 확인.
  - **down**: 기존 참조 cowl 위에 나페 border(옆 1px/뒤 2px, head L2 hair 하단 기준) + body back **1행 fold**(중앙 shadow, hair 위에 그림) 추가.
  - 검증: **677 passed** (361.62s), production QA **50 ok**, A/B `out/hood_ab/hood_ab_sheet.png`. 테스트 갱신: `test_hood_up_opens_at_row_two` 추가, crown/down-cowl 테스트를 새 정책에 맞춤.
  - 주의: 승인된 72쌍은 **v1 기준선**이다. 후드 쌍은 재생성·재승인이 필요하며, 그때까지 게이트는 v1 승인을 유지한다. 팩 리뷰 시트(`out/.../pack_review/v3`)도 이 변경 전 렌더라 재생성 대상.

- 2026-11-02 (최종 head-only 후드 마스크, `fix/hood-shape`): 사용자가 마스크 편집기에서 최종 마스크를 완료 → `assets/hood_masks.json`(up L1/L2, down L2 back/sides, **body 0**).
  - `skinmaker/hood_masks.py`로 공유 렌더러를 만들고, `render_hood_overlay`가 asset이 있으면 마스크 경로를 사용하도록 연결(asset 없으면 레거시 pack fallback).
  - up: L1 front row0 브림 + L2 장식/심/엣지. down: head L2 nape/sides + **body back 1행 fold**, **body front cowl 0**.
  - 검증: **677 passed** (773.21s, 부하로 느림), production QA **50 ok**, A/B `out/hood_ab_masks/hood_ab_masks.png`. 테스트: down mask-path/up brim/crown 갱신, 레거시 variant/fur는 `load_hood_masks` monkeypatch로 fallback 테스트.
  - 주의: 승인된 72쌍은 **pre-mask v1 기준선**이다. 후드 쌍은 재생성·재승인이 필요하며, 그때까지 게이트는 v1 승인을 유지한다. 에디터 도구(`tools/mask_editor/`)는 로컬 untracked이고, 저장 상태는 `out/mask_editor/mask.json`이다.

- 2026-11-02 (head.bottom 마스크 프로덕션 반영, `feat/hood-bottom-masks`): 사용자가 에디터에서 저장한 최종 마스크에 `head.bottom`이 포함됨 — up L1 16 / L2 6, down L2 16 / L1 0. `assets/hood_masks.json` 갱신, `skinmaker/hood_masks.py`의 HEAD_FACES에 bottom 추가 → 프로덕션 렌더가 bottom L1/L2를 적용.
  - 에디터: face 탭과 atlas에 `head.bottom`, 3D `ny` 레이캐스트로 직접 편집(로컬 `tools/mask_editor/`, untracked).
  - 검증: **678 passed** (724.71s), production QA **50 ok**, `test_final_asset_applies_head_bottom_masks`; asset bottom up 16/6, down 16/0.
  - 주의: 72 approved pairs는 **pre-bottom v1** 기준선이다. 후드 쌍은 재생성·재승인이 필요하며, 그때까지 게이트는 v1 승인을 유지한다.

- 2026-11-02 (hood-down long_hair body-back hair 제거, `fix/hood-down-back-hair`): 사용자 요청 — hood_down + long hair에서 몸통 뒷면에 머리카락을 그리지 않는다.
  - `render_body`/`render_hair_overlay`에 `hide_body_back_hair` 추가; `render()`가 `hood == "down" and hair_length == "long"`에서 자동 설정.
  - body **back face만** hair skip (side locks는 유지); long_wavy/ponytail의 body back tail도 skip. editor preview도 같은 플래그 사용.
  - 검증: **679 passed** (729.00s), production QA **50 ok**, hood-down long vs short body back L1/L2 diff **0**; body back L2 = 12 fold, body front L2 = 20 base hair.
  - 주의: 72 approved pairs는 pre-mask v1 기준선이다. 후드 쌍은 재생성·재승인이 필요하다.

- 2026-11-02 (medium hair body-back skip 확장, `fix/body-back-hair-medium`): 프로덕션 E2E에서 VLM이 long-hair 사진을 `hair_length=medium`으로 분류해 body back L2 hair 40셀이 남는 것을 확인. `hide_body_back_hair` 조건을 `long` → `long|medium`으로 확장(short는 원래 없음). 테스트에 medium long_wavy 추가.
  - 검증: **679 passed** (710.36s), QA 50 ok; medium/long/short 모두 body back L2 12(fold), hair 0. 배포 후 프로덕션 E2E 재확인 예정.

- 2026-11-02 (Gate v3, `feat/gate-v3`): 후드가 `assets/hood_masks.json` 마스크 기반으로 바뀐 것에 맞춰 게이트를 재정의.
  - 팩 hood 템플릿 승인(2/1)과 hood holdout coverage blocker 제거(보고만); `assets/hood_masks_approval.json`(SHA+policy)로 마스크 승인.
  - `benchmark_baseline.json`(mask_sha+policy) 없거나 불일치하면 **paired benchmark stale** blocker. 현재 72쌍은 pre-mask v1이라 baseline missing으로 `ready=false`.
  - 현재 blocker는 **1개**: `paired benchmark baseline missing (regenerate/re-approve)`; 나머지(hair/QA/eyes/mask approval/pairs count)는 통과.
  - 문서: `docs/production-gate-v3.md`, `docs/production-status.md`. 테스트 4개.

- 2026-11-02 (지퍼 색, `feat/zipper-color`, notes 30건): `draw_zipper`의 고정 `METAL`을 상의 색 파생으로 변경. 중간/밝은 상의는 0.78 shade, 아주 어두운 상의는 흰색 45% mix로 대비 유지; 단추는 그대로.
  - 검증: **681 passed** (243.78s), QA 50 ok; `test_zipper_color_is_derived_from_top`; A/B `out/zipper_ab/zipper_ab.png`(before silver → after blue-derived).
  - 주의: notes 30건 중 "지퍼 색이 상의/잠바/후드 색을 닮아야"를 직접 해결. 72 approved pairs는 여전히 pre-mask v1이며 paired baseline은 보류 상태다.

- 2026-11-02 (open jacket/inner layer, `feat/open-jacket`, notes 15건): `closure_type`에 **open** 추가(VLM hint/CategoryPanel 라벨 포함). `draw_open_front`가 가운데 2px를 이너(top: inner_top 색)로 채우고 u2/u5에 겉옷 엣지, 지퍼/단추는 그리지 않음. 칼라는 그 뒤에 덮고 넥타이는 유지.
  - 검증: **682 passed** (245.38s), QA 50 ok, frontend lint/build ok; `test_open_jacket_shows_inner_strip_and_no_zipper`; A/B `out/open_jacket_ab/open_jacket_ab.png`(closed zipper → open+gray inner).
  - 주의: VLM이 실제 열린 잠바를 open으로 분류하는지는 실사진 E2E로 확인 필요. 72 approved pairs는 여전히 pre-mask v1/paired baseline 보류.

- 2026-11-02 (무늬 연속성, `feat/arm-patterns`, notes 6건): `render_arms`가 “무늬는 소매에 넣지 않는다”고 단색 처리하던 것을 변경. stripe/check/plaid는 `_pattern_color`, graphic은 크롭 texture를 소매에도 적용; 소매 끝 seam은 유지.
  - 검증: **683 passed** (243.85s), QA 50 ok; `test_arms_use_the_body_pattern`; A/B `out/arms_pattern_ab/arms_pattern_ab.png`(plain arms → striped arms).
  - 주의: 의상 색 재현(9건)은 색 샘플링/폴백 문제로 분리해 별도 진단이 필요하다. 72 approved pairs는 여전히 pre-mask v1/paired baseline 보류.

- 2026-11-02 (color audit + outer guard, `fix/color-outer-guard`): 수기 notes 의상 색 9건 audit. pair 사진에서 `quality.inspect`→`colors.extract`로 observed top/outer/inner를 실측.
  - Root cause: 어두운 outer 표본(그림자/바지)이 확신 있는 top을 덮어씀(teal/gray→black); hoodie는 outer 후보에서 빠져 배경 오염 top(beige→light blue) 사용.
  - Fix: layered(inner_top≠none)에서 inner가 dark/missing이고 top이 40 luma 이상 밝으면 outer 무시; hoodie를 outer 후보에 추가. 단일 재킷(inner none)의 outer 우선은 유지.
  - 검증: teal `(27,26,27)→(73,139,164)`, gray `(37,36,44)→(166,187,192)`, beige `(198,224,250)→(142,122,99)`; **686 passed** (241.29s), QA 50; A/B `out/color_audit/color_audit_ab.png`; 문서 `docs/color-audit-2026-11-02.md`.
  - 남은 색: pink/white top(배경 오염), 흰 바지(bottom), 금발(hair low-confidence/dark). 후드 형상/머리색 테마는 아직.

- 2026-11-02 (hair fallback, `fix/hair-fallback`, notes 5건 중 2건 개선): top background reject 실험은 악화(pink→MISSING, white→brown, teal→red)되어 폐기. `resolve_colors`의 hair fallback을 조정 — low-confidence라도 luma>90인 밝은 샘플은 측정색 유지, 어두운 샘플은 default.
  - 검증: gold `#ddc19c` → blond; `#8d6648` → brown(개선); **687 passed**, QA 50; A/B `out/color_audit/hair_audit_ab.png`; 문서 갱신.
  - 남은 색: pink/white top(region), white pants(bottom), dark gold hair(00/02/06); 후드 형상 6건.

- 2026-11-02 (WB cap, `fix/wb-cap`): 공격적 skin-anchored WB gain(R 0.80~0.87/B 1.14~1.15)이 white/beige를 light blue로 만드는 것을 확인. `WB_CLIP` 1.25→**1.10**, 10% 초과 gain은 미적용(identity). white hood 2건 + beige 개선; teal/gray는 outer guard 유지.
  - 검증: **687 passed**, QA 50; A/B `out/color_audit/wb_ab.png`; 남은 pink/pants/dark hair/hood geometry.

- 2026-11-02 (SCHP upper-clothes top, `fix/seg-top-color`): WB_CLIP 1.10 유지(1.05는 lipstick WB confidence 테스트를 깨서 폐기). `extract`가 SCHP Upper-clothes(4) 마스크에서 **raw RGB** top 색을 뽑도록 override; bands는 small mask fallback. pink `#e4cbc7`, white hood near-white, beige 개선.
  - 검증: **687 passed** (240.34s), QA 50; A/B `out/color_audit/seg_ab.png`; 남은 white pants(bottom)/dark hair/hood geometry.

- 2026-11-02 (white pants bright mask, `fix/seg-bottom`): SCHP Pants/Skirt 마스크 bright 60%에서 bottom 샘플. white pants `#c18a69`→`#e9e2de`; trusted seg bottom은 white-as-background fallback을 우회하고 `bottom_plausible=True`.
  - 검증: colors 90 passed, full suite/QA; A/B `out/color_audit/pants_ab.png`; hair는 VLM bbox/light percentile로도 dark(region 자체 dark), hood geometry 미착수.

- 2026-11-02 (hood audit, `docs/hood-audit`): 후드 형상 6건을 최종 마스크 기준으로 감사. 03(앞머리)/17(밖 머리)/05(깊은 후드)는 마스크로 해결, 07/11(후드 안 모자)은 headwear 스키마·색 샘플 부재, 09(얕은 후드/귀)는 depth/귀 속성 부재. A/B `out/hood_audit/hood_audit_1.png`, `_2.png`; 문서 `docs/hood-audit-2026-11-02.md`. 코드 변경 없음.

- 2026-11-02 (headwear, `feat/headwear`): `headwear`(none/beanie/cap) 속성 + VLM hint + CategoryPanel 라벨. 후드 up일 때 head front row1에 1px 챙; cap은 light, beanie는 dark heuristic (색 샘플 없음). VLM E2E: `hood_up_short_hair_11` → headwear=beanie; `07`은 beanie로 오분류(원본 white cap, UI에서 cap 수정 가능). A/B `out/hood_audit/headwear_ab.png`.
  - 검증: full suite/QA; 남은 후드 09(귀/depth), dark gold hair.

- 2026-11-02 (hood_fit/ears, `feat/hood-fit`): `hood_fit`(normal/shallow/deep) + UI. 후드 up + shallow이면 hood overlay 뒤 side-front(u6/u1, v4-5)에 skin shade 귀 2px. VLM E2E 09는 `hood_fit=normal`(자동 감지 실패; UI에서 shallow 수정). A/B `out/hood_audit/ears_ab.png`. 후드 6건은 마스크/headwear/hood_fit으로 모두 처리(09는 수동 설정).
  - 남은 골: dark gold hair 3건.

- 2026-11-02 (hair audit, `docs/hair-audit`): dark hair 3건(00/02/06)은 source-limited. SCHP mask dark(#3e1a0c/#191615/#1f1c1a), VLM bbox-only도 dark/empty, bright clustering에도 gold 없음. 02 blonde는 뒤에 있는 다른 사람; 00/06은 auburn/brown. 수동 hair color override 또는 머리가 보이는 사진이 필요. 크롭 `out/hair_audit_crops.png`; 문서 `docs/color-audit-2026-11-02.md`.

- 2026-11-02 (manual hair colour override, `feat/hair-override`): API `hair_color`(#rrggbb) + 메인 설정 패널 color input/checkbox. source-limited 3건(00/02/06)을 사용자가 gold로 지정 가능. API E2E `#d4af37` → gold hair; A/B `out/hair_override_ab.png`.
  - 검증: backend 35, full suite/QA; invalid color 400 `bad_hair_color`; mask editor는 색 피커 없음 유지(메인 패널만).

- 2026-11-02 (attribute masks Phase 1a, `feat/attribute-masks`): 일반 `assets/attribute_masks.json`(+approval) 도입, hood.up/down 마이그레이션, headwear.cap/beanie + hood_fit.shallow seed. `render()` `mask_override`; production은 approved asset, 없으면 procedural. 에디터 key/value tree(hood/headwear/hood_fit) + general `/api/defaults|preview|save`; gate가 general asset SHA를 읽음.
  - 남은 Phase 1b+: hair/beard/body/arms/legs, 3D all-part pick/atlas, seed exporter, approval CLI, docs.

- 2026-11-02 (head masks Phase 1b, `feat/head-masks`): editor keys hair_style/hair_length/beard + `apply_head_masks` post-pass. Hair L1 clip/add + L2 clip; style/length intersect; beard adds hair-shaded front cells; preview uses hood=none for hair/beard. Blank masks by default; seed/all-part 3D remain.
  - 검증: 702 passed; QA 50; custom hair/beard mask tests; editor defaults expanded; assets/approval unchanged.

- 2026-11-02 (hair seed, `feat/head-mask-seed`): editor `/api/defaults`가 hair_style/hair_length 마스크를 procedural head hair cells로 seed(L1; L2는 L1 fallback). `render_head(return_cells=True)` 추가. bob/long = 272 cells, short = 156; beard는 procedural 부재로 blank.
  - 검증: editor defaults test hair cells>0, beard=0; full suite/QA.

- 2026-11-02 (all-part editor + sleeve, `feat/all-part-sleeve`): editor PARTS 6 / FACES 36 / real dims; viewer `pick(part,layer)` for body/arms/legs; part tabs + dynamic atlas grid; `sleeve_len` masks seed + `render_arms` clip. Tests 703; QA 50; asset/approval unchanged.

- 2026-11-02 (bottom masks, `feat/bottom-masks`): all-part editor + `bottom_garment` (jeans/shorts/skirt/pants/none). `render_legs` 후 apply_bottom_masks가 rows0-8 clip (shoes rows9-11 유지); editor는 bottom=none 대비 diff seed (352 cells). Tests 704; QA 50; asset/approval unchanged.

- 2026-11-02 (structure masks, `feat/structure-masks`): editor keys closure_type/collar_type/pocket_type/neckwear; structure drawers + tie accept body.front mask; seeds 11/16/2/6/2 cells. Tests 705; QA 50; asset/approval unchanged.

- 2026-11-02 (inner_top + approval CLI, `feat/inner-approval`): inner_top mask (body throat + arm cuffs, 38-cell seed); scripts/approve_attribute_masks.py validates draft -> asset + SHA approval (requires --yes). Tests 708; QA 50; production asset unchanged until run.

- 2026-11-02 (top_garment, `feat/top-garment`): body/arm/leg(0-8) mask, seed tee/vest 550, dress 582; editor 14 keys/56 entries. Tests 709; QA 50. All 14 shape keys done; approval CLI promotes drafts; paired deferred.

- 2026-11-03 (editor boot fix, `fix/editor-boot`): viewer.js `PART_UV2`가 `HEAD2` 정의 전에 평가돼 TDZ ReferenceError → 모듈이 부팅 전에 죽고 `/api/defaults` 요청 없음/“불러오는 중” 고정. 정의 후로 이동; index에 error/unhandledrejection status handler; app.js v10; 초기 face `front`. Headless Chrome에서 defaults 200 → preview 200 → status `head / hood.up / L1 / head.front` 확인.

- 2026-11-03 (body hair masks, `fix/body-hair-masks`): hair mask seed에 body L1/L2 drape 포함(long_wavy 예: L1 186, L2 50); `apply_body_hair_masks`가 L1/L2 body hair를 mask로 clip/add; hood-down back policy 유지. 3D Mask view/body atlas에 body hair 표시. Tests 710; QA 50.

- 2026-11-03 (head L2 hair, `fix/head-l2-hair`): head L2 mask seed from overlay-on vs hair_overlay=False baseline (long_wavy head L2 72 cells); apply_head_masks L2 clip; Mask view/head L2 atlas editable. Tests 711; QA 50.

- 2026-11-03 (hair_length preview style, `fix/hair-length-preview`): preview/seed base style mapping short→short, medium→bob, long/very_long→long_straight. head L1 146/212/272/328, body 0/0/186/186; short no longer looks like long_straight. Tests 712; QA 50.

- 2026-11-03 (hair_length saved migration, `fix/hair-length-draft`): stored draft hair_length body faces replaced by new length-matched seed (head edits preserved): short/medium body0, long/very_long 186 L1. Fixes short showing very_long-like saved body drape. Tests 712; QA 50.

- 2026-11-03 (seed reset + hair_style base, `fix/editor-seed-reset`): saved drafts override new seeds -> `/api/seed` + "Seed로 되돌리기" per key/value; hair_style seed/preview base very_long so hair_length=very_long is not clipped by long-baseline style masks. Tests 714; QA 50.

- 2026-11-03 (QA contact sheets, `feat/qa-contact-sheet`): `run_production_qa.py` now writes a labelled contact sheet (`--image`, default `out/production_qa/contact_sheet.png`; `--asset` to QA a draft). Production asset c4bae: 50/50 PASS. Promoted draft b387: 17 FAIL, all hood-up + long hair body-back; stay undeployed. Tests 715.

- 2026-11-03 (combo preview P0, `feat/combo-preview`): `/api/defaults` 16-key enums/defaults/models/combo; `/api/preview` combo/model/effective/warnings; editor 16-select combo panel, mask key/value auto-sync, URL+localStorage; classic/slim 2D; 3D classic front; symmetry metadata note. Tests 719; QA 50. P1: slim 3D, presets, 3D back/overlay; production site out.

- 2026-11-03 (P1 slim 3D + presets + 3D capture): viewer.js slim arm 3px UV/geometry + `setModel`; editor model select drives 3D (classic/slim); combo presets (hoodie/jacket/dress/tee); 3D headless capture fixed with `--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader`; QA 3D page renders 16 of 17 contexts (WebGL limit). Tests 719; P2 production site out.

- 2026-11-03 (L1/L2 multi-select, `feat/layer-multiselect`): layer tabs toggle independently (at least one); atlas renders every selected layer (2 grids/face); one paint stroke applies to all selected layers (mirror too); 3D `setEditableLayer` accepts an array and shows the L2 shell when selected; status `L1+L2`. CDP verified: layers ["L1","L2"], atlas 72, one paint sets L1=1/L2=1. Tests 719.

- 2026-11-03 (pants erased fix, `fix/top-leg-blank`): `apply_top_leg_masks` treated a blank top_garment leg grid (editor defaults for hoodie) as "remove leg"; it ran after `apply_bottom_masks` and repainted rows 0-8 with skin. Now blank top-leg masks are skipped; dress masks with cells still apply. Regression test added: blank top-leg + jeans bottom keeps the pants. Tests 720.

- 2026-11-03 (top body + hood-up hair migration, `fix/top-hair-mask-migration`): `/api/defaults` now refills top_garment body faces as full (body.back 96/96; body 352) and zeroes hair_style/hair_length body.back (L1/L2) for the hood-up/down policy. QA with the fixed asset: 50/50 PASS. Migration skip top_garment.none. Tests 721.

- 2026-11-03 (person auto-crop, `feat/person-autocrop`): YOLOv8n ONNX exported (13MB) and `skinmaker/person.py` detects the largest person via cv2.dnn (class 0, NMS), 10% margin. `quality.inspect` EXIF transpose → person crop → multiscale face; `PhotoInput.source=person`; backend `crop` form + `no_face` can_crop/image_size; frontend CropModal. Provided fullbody/snow fixture: person (557,245,708,1945), face found, source=person. Tests 690.

- 2026-11-03 (request cancellation, `feat/request-cancel`): `generate_skin` stages now run via `asyncio.to_thread` (`_await_or_cancel`); client disconnect raises 499 between stages; frontend uses `AbortController` and aborts on unmount/beforeunload. Tests 725.

- 2026-11-03 (loading progress, `feat/loading-progress`): loading overlay now shows a progress bar plus a short current-operation line (사진 읽기 → 인물 찾기 → 전신 크롭 → 얼굴 → 의상 분석 → 색 추출 → 스킨 그리기 → 마무리), elapsed-time estimate capped at 92%. Frontend-only; real server progress is a follow-up.

- 2026-11-03 (SSE progress + timings, `feat/sse-progress`): `POST /api/v1/generate-skin` with `Accept: text/event-stream` returns SSE progress (`inspect`/`classify`/`segment`/`extract`/`render`/`steps`/`done`) then a `result` event with `data.timings`; JSON clients unchanged. Frontend parses SSE and drives the loading bar + stage text. Tests 726.

- 2026-11-03 (parallel VLM, `perf/parallel-vlm`): `classify()` now runs the natural-order and reversed-order Gemini calls concurrently (`ThreadPoolExecutor(max_workers=2)`) instead of sequentially, halving the worst-case 2x30s latency; merge/agreement semantics unchanged. Tests 726.

- 2026-11-03 (segment cache, `perf/segment-cache`): `parsing.bottom_mask` caches the SCHP result by RGB pixel SHA-1 in a small 8-entry in-memory LRU (no disk persistence). Same image: ~3.1s → ~0.03s. Tests 726 (118.78s).

- 2026-11-03 (VLM timeout, `fix/vlm-timeout`): `make_transport` now passes `timeout=SKINMAKER_VLM_TIMEOUT` (default **10s**, previously 30s) so a slow Gemini call costs at most 10s instead of 30s. Tests 726.

- 2026-11-03 (final stage order, `fix/final-stage-order`): SSE now emits `saving` (88%) before writing the input/steps/candidate files, then `steps` (95%) after the writes, then `done` (100%). Avoids the bar appearing frozen at the end. Tests 726.

- 2026-11-04 (merge coerced fields + upload suffix, `fix/merge-coerced-upload-suffix`): 코드 리뷰 2건 수정.
  - `classify._merge`: 병합된 `coerced` 에 필드명이 아니라 튜플이 들어가 `"bottom_garment" in attrs.coerced` 가 거짓이었다. 그래서 강제된 필드를 확신 있는 값으로 취급해 S1 커버 폴백(`resolve_sleeve`/`resolve_bottom_ex`)과 패턴 보수화(`effective_pattern`)가 건너뛰어졌다. 이제 필드명을 `append` 한다. 테스트 `test_classify_merge_records_coerced_field_names_flat`.
  - 업로드 저장 확장자: 파일명(`Path(file.filename).suffix`)을 그대로 써서 `x.html` 로 올리면 공개 출처의 `/static/skins/` 에서 `text/html` 로 서빙될 수 있었다. 이제 PIL 이 감지한 형식(JPEG/PNG/WEBP/AVIF → .jpg/.png/.webp/.avif), 그 밖은 `.bin`. 테스트 `test_upload_is_stored_with_extension_from_image_format`.
  - 검증: 신규 테스트 2개 수정 전 실패 → 수정 후 통과; `pytest -q` → **728 passed** (124.04s), exit 0.
  - 미결정: 마스크 승인 정책. `render()` 는 `attribute_masks_approval.json` 의 SHA 를 확인하지 않고 `assets/attribute_masks.json` 을 그대로 쓴다. 승인 검사는 `production_status.py` 게이트에만 있다. 렌더 경로에서 강제할지, 문서만 고칠지 사용자 결정이 필요하다.
  - 로컬 미추적 파일(`assets/yolov8n.pt`, `scripts/build_pack_review.py`)은 이 PR 에 포함하지 않았다.
- 2026-11-04 (mask-approval policy decided, `docs/mask-approval-policy`): 사용자 결정 **Option B** — 렌더러는 `assets/attribute_masks.json` 을 있는 그대로 사용한다. SHA 승인(`attribute_masks_approval.json`)은 `production_status` 릴리스 리포트에서만 확인하며 렌더링을 막지 않는다. 코드 동작은 변경 없음; `attribute_masks.py` 독스트링을 정책에 맞게 고쳤다. 승인 검사를 렌더에 강제하려면 별도 결정이 필요하다.

- 2026-11-04 (results UI cleanup, `feat/results-ui`): 사용자 요청 3건.
  - 로딩 바 아래 `보통 20~40초 걸려요. 창을 닫지 말아 주세요.` 힌트 삭제 → 같은 날 복구하고 시간만 `보통 10초 정도 걸려요. 창을 닫지 말아 주세요.` 로 바꿈 (`.loading-hint` 스타일 복원). 진행 바와 `loading-stage` 단계 문구는 유지.
  - 후보 카드의 `스킨 편집 ✏️` 버튼 삭제. 사이드바의 `편집` 버튼과 `SkinEditor` 모달은 유지.
  - 후보 카드를 원본보다 크게: `Skin3DViewer` 에 선택적 `className` 을 추가하고 후보 카드는 `width: min(300px, 100%)` + `aspect-ratio: 13 / 18` 로 CSS sizing. 데스크톱 후보 카드 300px, 뷰어 약 258×357, 원본 사진은 기존 200×280 유지. 720px 이하에서는 후보 카드 패딩만 10px 로 줄여 360px 뷰포트에서 뷰어 220×305, 가로 스크롤 없음. 편집기 뷰어는 360×480 그대로.
  - 원본 카드의 다운로드 버튼은 `margin-top: auto` + `padding-top: 12px` 로 카드 하단에 맞춰 후보 카드 버튼과 같은 높이에 정렬.
  - 검증: `npm run lint` / `npm run build` green. Headless Chrome 1440×1000 및 360×800, 후보 1개와 3개 모두 확인. 3후보 데스크톱은 `[원본+후보1] / [후보2+후보3]`, 360px에서는 세로 1열, `scrollWidth` = viewport(1440/360). 로딩 힌트 0개, 후보 편집 버튼 0개, 사이드바 편집 버튼 1개, 원본/후보 다운로드 버튼 y좌표 일치(1391px). `.venv/bin/python -m pytest -q` → **726 passed, 2 skipped** (115.16s, 2회 실행 중 108.22s).
  - 리스크: 시각 확인은 mock transport 기반이며 실제 사진/실기기 확인은 수동 후속. 320px 미만에서는 기존 고정 200×280 원본 카드가 넘칠 수 있다(이번 변경 전부터 존재).
