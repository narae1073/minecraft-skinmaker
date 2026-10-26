# handover — skinmaker (2026-10-26, repo-hygiene branch)

## 1. Project in one paragraph

Photo → Minecraft 64×64 skin pipeline.
S0 quality/face detection (YuNet) → S1 colour measurement (white-balance + band/cascade) → SCHP human-parsing mask (colour localization for bottom/hair/shoes — default ON) → S2 classification (double query, uncertainty flags) → S3 parametric render (+ deterministic noise) → S4 candidates (1–3 variants from double-query disagreements) → web app (FastAPI + React 19 / three.js with 3D viewer and editor modal).

## 2. Current state (verified 2026-10-26)

- Tests: **505 passed** (~3 min) with `tests/fixtures/` committed; a fresh clone no longer skips fixtures.
- Frontend: `npm run lint` clean, `npm run build` green (Vite 8 / Node 24).
- Python 3.12.3 venv at `.venv`; do **not** use `python` or `uv`.
- Parsing model: `out/models/schp-atr-18-int8-static.onnx` (66 MB, gitignored). YuNet: `assets/face_detection_yunet_2023mar.onnx` (228 KB, gitignored). Both fetched by `scripts/fetch_assets.sh`.
- `mediapipe` was removed from requirements: the pose model is `assets/pose_landmarker_lite.task.disabled`, so `detect_pose()` always returns `None` and pose bands/cover measurement are dormant (code and tests remain).
- Deployment target: home server + Cloudflare Tunnel `skin.achijaser.date` (public, no auth as of the decision). systemd units and tunnel setup are the next phase.
- Git: work on branches/PRs; `master` protection and CI are being added in the next phase. `opencode.jsonc` is deleted and gitignored by the user.

## 3. Repo hygiene that landed on this branch

- Untracked **253 generated skin PNGs** under `backend/static/` (the folder is gitignored; the app recreates it). Local `backend/static` was purged (~547 MB).
- Untracked **70 held-out photos** (public repo) and moved them to `out/heldout-photos/` (gitignored). History was **not** rewritten; old commits still contain them.
- Removed `app.log`; added `*.log` to `.gitignore`.
- Moved `website_output_images/` → `docs/assets/screenshots/`; moved `frontend/public/mockups/` → `docs/design/mockups/` (not referenced; no longer shipped in `dist`).
- Moved `handover.md` → `docs/handover.md`; moved the one tracked ledger to `docs/ledger/`.
- `requirements.txt` is runtime only; `requirements-dev.txt` adds pytest/httpx; `requirements-parsing.txt` was merged (onnxruntime is runtime).
- Added `.env.example` and `tests/fixtures/README.md`.
- Deleted the broken Pages workflow and disabled GitHub Pages (it deployed the repo root, not the app, and 404'd).
- Deleted the two `ci-sync-*` branches that contained a secret-dumping workflow (runs were blocked; no secrets existed).

## 4. Next phases (agreed plan)

1. **CI + agent workflow**: `.github/workflows/ci.yml` (pytest + lint + build), branch protection (PR, 1 approval, required checks), `AGENTS.md`, `scripts/dev_setup.sh`, PR template.
2. **Deployment hardening**: upload cap (15 MB), in-app rate limit (6/min/IP), 14-day retention timer; `deploy/skinmaker.service`, `deploy/cloudflared-skinmaker.service`, `deploy/skinmaker-cleanup.*`, `scripts/deploy.sh`, `docs/deployment.md`.
3. **Host setup**: create tunnel `skinmaker`, route `skin.achijaser.date`, install/enable services, verify end-to-end from the public URL.

## 5. Known issues / backlog

- Pose path is dormant (model disabled, mediapipe removed). Re-enable deliberately: install `mediapipe`, restore `assets/pose_landmarker_lite.task`, re-add `requirements-pose.txt`.
- S2 `top_garment` distinction (polo/shirt/tank) remains the weakest field.
- Editor expansion (live re-render, outfit/skin-tone options) is deferred; the option seam is in `SkinEditor.jsx`.
- Deferred minors from the 2026-10-13 review (sidebar steps image, flatUrl guard, hard |Δ| in jeans test, eval tolerance) still apply.
- Public no-auth deployment: rate limit + upload cap + retention are the mitigations. Revisit Cloudflare Access if abuse appears.
- Old held-out photos remain in public git history; revisit only with a coordinated history rewrite.

## 6. Working norms (do not violate)

- TDD: fail first → minimal implementation → green. Run commands unpiped and check exit codes.
- `npm run lint` before frontend commits.
- Policy/constant changes need a recorded A/B baseline.
- Generated files, `.env`, and models are never committed.
- Short-lived branches + PRs; never push `master` after protection is enabled.
- Update this document at the end of a session; put task evidence in the PR description.

## 7. Records map

- Design specs/plans: `docs/superpowers/specs/`, `docs/superpowers/plans/`
- Ledger: `docs/ledger/`
- Screenshots: `docs/assets/screenshots/`
- Design mockups: `docs/design/mockups/`
- This document: `docs/handover.md`
