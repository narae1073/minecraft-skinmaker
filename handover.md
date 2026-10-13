# handover — skinmaker, for the next session (written 2026-10-13, HEAD `a2aa2d3`)

## 1. Project in one paragraph

Photo → Minecraft 64×64 skin pipeline. **The VLM (Gemini) returns attribute JSON only; a code renderer paints the pixels.**
Stages: S0 quality/face detection (YuNet) → S1 colour measurement (white-balance + band/cascade) → S2 classification (double query, uncertainty flags) → SCHP human-parsing mask (colour localization for bottom/hair/shoes — **default ON** in code) → S3 parametric render (+ texture noise) → S4 candidates (1–3 variants from double-query disagreements) → web app (FastAPI + React 19 / three.js with 3D viewer & skin editor).

## 2. Current state (verified facts)

- Tests: **451 passed**. ESLint: 3 remaining advisories only (`Skin3DViewer.jsx` purity warnings — deferred by decision, see §5).
- Server: `set -a; source .env; set +a; .venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8001`
  (`--host 0.0.0.0` is required for LAN access — binding loopback-only was a real incident).
- **Do NOT use `python` or `uv`** (not installed). Use `.venv/bin/python`.
- **venv recovery history**: the system python3 moved 3.12 → 3.14 overnight once, orphaning the venv
  (`No module named uvicorn`). Fixed by reinstalling `python3.12 3.12.3-1ubuntu0.17` (+minimal) debs and
  re-pointing `.venv/bin/python3` → `/usr/bin/python3.12`. Deb cache: `/tmp/opencode/py312/` (if deleted,
  re-download from the Ubuntu archive pool). If a future `apt upgrade` removes python3.12 again, expect the same symptom.
- Parser model: `out/models/schp-atr-18-int8-static.onnx` (gitignored, present). `onnxruntime 1.31.0` only (no torch).
- `.env` has `SKINMAKER_PARSING=1`, now **redundant** (code default is ON) but harmless — left in place.
- Git state: `master` @ `a2aa2d3`; `origin/master` sits at `3211cdc` (the owner pushed once mid-session);
  ~9 commits unpushed. **History below `701573e` was rebased at some point** — commit SHAs in the ledger text
  may differ from current SHAs; same messages, content unchanged. Push is the owner's decision.

## 3. What this segment delivered (noise + editor plan, range `9e05a1b..251bcc6`, all committed)

- **Texture noise**: discrete tone banding `NOISE_STEPS=(0.92,0.96,1.0,1.08)`; per-face independent rng with
  variable pitch (1–3px patches); **left/right asymmetric** (base drawing stays mirror-symmetric;
  `validate.py` mirror check relaxed to per-channel |Δ| ≤ `NOISE_TOL=32`). User history: uniform grid →
  asked for irregular+asymmetric → asked for a no-2×2-clump rule → **retracted**; current patch scheme stays.
- **Deterministic seeds**: `derive_noise_seed` = sha256(resolved colours + sorted attrs + degrade + candidate
  index). `noise_level` is deliberately **NOT in the seed** — the slider is a pattern-stable knob.
- **noise_level** (spec §9): magnitude scaling of the steps; 0 = byte-identical to noiseless; 1 = current look.
  Web slider default **50%**. API form field `noise_level` (absent → 1.0; garbage → 400; out-of-range clamped).
- **Edit Skin editor** (spec §5): results cards and sidebar entries open a `SkinEditor` modal (large 3D view +
  **two-tone shoes toggle, default ON** + processing-steps section). At generation time each candidate is
  pre-rendered as an ON (`_c{n}.png`) / OFF (`_c{n}_flat.png`) pair — same seed, pixel differences confined
  to shoe rows (contract tests). **Owner verdict: "editor for later"** — further editor features (live re-render,
  outfit/skin-tone options) are deferred; the option-state seam in the modal is left ready.
- **Upper-body photos default to jeans** (spec §10): if the parser mask sees **zero** bottom-garment (5/6) **and**
  zero bare-leg (12/13) pixels, S2 confidently says "none", and top ≠ "dress" → resolve to `jeans` with
  `DEFAULT_JEANS #3b5a86` (classic denim; the observed "bottom" sample is discarded as a shirt-tail false
  positive). Full-body bare-legs photos stay "none" (D3 decision preserved). The response summary reflects the
  same decision (derived note), so texture and UI can't disagree.
- **Classification categories on the web** (spec §11): response gains `attributes {values, uncertain, derived,
  coerced}`, `candidates [{index, varied}]`, `noise_level`. Frontend shows Korean chips (uncertain = amber,
  derived = `*`) + a collapsed category-JSON table + a raw-JSON copy button; per-candidate `varied` subtitles
  explain why c2/c3 exist.
- **Processing-steps images** (spec §12): per request, `backend/static/steps/{token}_steps.png` (simple strip
  s0 photo/face → parser mask → colour samples → 64×64 atlas, **2-column grid**) and `_full.png` (full QA,
  6 panels incl. UV guide + 3D preview). Form field `steps` — **web checkbox default UNCHECKED**; when off the
  server skips building/saving entirely (`steps: null`; truthiness convention matches `parsing_on`; absent field
  → generated, for old clients). Parser mask runs **once per request** (`extract(seg=)` shares it).
  Web shows a fixed-height 150px thumbnail → **lightbox modal** (own scroll, simple/QA toggle, Esc/close).
- **Page shell, plan D** (spec §12 amendment): all flex centering removed from `body`/`#root` → block layout +
  `.container { margin: 24px auto 40px }`. Root cause evidence: CDP headless reproduction showed at `scrollY=0`
  the container top at −628px/−1371px (top physically unreachable — flex overflow trap); now 24px, centered,
  no horizontal overflow at 1240×950 and 390×844. **`5b8c7bf` (margin-block:auto) was a wrong fix** — the
  fixture lacked fixed-position siblings, so it lied. The earlier overflow-anchor/lazy-load changes treated
  secondary symptoms. Page section order: (original + candidates) row → (classification + steps) row; with
  steps off, the analysis row collapses to one column.

## 4. Final review (fresh subagent, 2026-10-13) — **ready to merge**, 0 Critical/Important

Deferred Minors, in reviewer priority order:
1. **Editor modal always passes the *current* generation's steps image** — clicking 편집 on an older sidebar
   skin shows another photo's steps. Fix: store `steps` on each history pair object. **Top follow-up fix.**
2. When `flatUrl` is null the toggle reads OFF while displaying the two-tone texture (control/texture mismatch,
   only reachable with older responses), and the download filename is the raw token (`1a2b3c4d_c1_flat.png`)
   → disable-toggle guard + human-friendly filename.
3. `Skin3DViewer` immutability advisories — the file changed in this range (LARM/LLEG), so clean them up
   (useMemo / loader callback) at the next edit of that component.
4. Backend jeans e2e pixel assertion uses hard |Δ| ≤ 8 — should use `NOISE_TOL` (32). Deterministic today,
   but brittle against fixture swaps or tone-code edits.
5. eval tolerance can hide swaps between *similar* colours (e.g. black hair vs dark navy) — an openly accepted
   semantic change (§3); reviewer suggests a follow-up test with an adjacent-colour pair.

Reviewer independently re-verified: full suite 451 green; mirror-stress (60 random seeds × 5 garment combos →
0 validate failures); seed/pair/guard/skip contracts; crash-fix aftermath clean; layout D with no residual trap.
Unplanned win confirmed: per-side limb rects make left-noise independence actually visible in the viewer.

## 5. Backlog (priority order)

1. Deferred minors 1, 2, 4 above (small; do RED→GREEN each if the owner says "fix minors").
2. **Editor expansion ("later")**: live re-render = store observed colours + attrs per token + a re-render
   endpoint (slider/toggle react without VLM cost) — see the cost note in spec §9.
3. Pale-colour chroma loss (pale-yellow pants measure `#c7cdc1` grey-green on white bg) — **measurement-logic
   design task, NOT constant tuning**.
4. Plan `2026-10-11-skinmaker-finish-wip.md` remnants: B1 seated-pose bottom crop (images12-class), B2
   "none"-hallucination gating.
5. Visual polish not chosen: outline (A) and shading (B) — owner picked only C (two-tone shoes). Re-propose
   if wanted.
6. S2 `top_garment` weakness (polo/shirt/tank distinctions scored 3/10 vs human labels) — human label expansion
   or better crops.
7. Owner decisions pending: push (~9 commits), and workspace cleanup
   (`.superpowers/sdd/2026-10-12-noise-editor/`) after this review.

## 6. Working norms (do not violate)

- **TDD**: watch the test fail → minimal implementation → green. Run failure-capable commands **unpiped and
  independently before committing** — `pytest | tail && commit` produced red commits twice (lesson logged).
- **Run `npm run lint` before any frontend commit** (the react-hooks plugin existed and two crashes slipped by).
- Constants/policy changes must be argued with a **recorded baseline A/B**; no improvement claims without one.
- The **59-photo fitting set** (`docs/superpowers/specs/bottom_labels.json`) is the only tuning/validation pool;
  held-out sets (49 + 45 photos) are **consumed** — never reuse. Human labels are ground truth (decision (a)).
- Korean commit messages; direct commits on `master`; pushing is the owner's call.
- Reviewer subagents only when the owner requests one; default reviews are self-reviews, disclosed openly.

## 7. Records map

- Rulings/mistakes/lessons ledger: `.superpowers/sdd/2026-10-12-noise-editor/progress.md`
- Noise+editor design: `docs/superpowers/specs/2026-10-12-skin-noise-editor-design.md` (§2–§12)
- Full validation ladder: `docs/superpowers/specs/2026-10-11-heldout-protocol.md`
  (L0→L3, L2b raw colour, L2c hair/shoes, web verification, S2 enum validation + human-accuracy addendum)
- S2 validation artifacts: `out/s2_enum_val.py` / `out/s2_enum_val.json` / `out/s2_review.html` /
  `out/s2_human_labels.json` (filled — strict 0.72 / coarse 0.76; top_garment 3/10 weakest)
- Master plan file: `/home/achi/.opencode/plan/2026-10-11-skinmaker-finish-wip.md`
- This document: `handover.md`

## 8. Proven techniques from this session

- **CDP headless verification**: `/usr/bin/google-chrome --headless=new --remote-debugging-port=...` +
  `websocket-client` (installed in the venv) to measure real-app scroll/layout metrics and capture screenshots —
  see `/tmp/opencode/scrolltest/{check,diag,probe2,probe3}.py`. **Verify layouts in the real app** (a fixture
  reproduced the wrong answer once).
- A/B visual boards for human judgment: `out/shoes_ab.py`, `out/noise_ab.py`.
- Session trivia: uvicorn log at `out/uvicorn.log`; find background servers with `pgrep -f uvicorn`;
  port 8001 was already bound once — check before starting a second instance (Errno 98).
