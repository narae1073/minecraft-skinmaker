# Hair Silhouette Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve mask-driven hair so rounded hairlines don't create bald corners, side/back coverage follows a profile, and long hair reaches the upper-body shoulders.

**Architecture:** Keep `hair_source=rule` pixel-identical. Extend the mask-derived `HairStencil` with per-face coverage profiles and a body-length signal; derive these from the existing SCHP segmentation, then paint them deterministically in the renderer. The mask remains optional and failure falls back to the rule stencil.

**Tech Stack:** Python, NumPy, Pillow, existing SCHP class map and pixel renderer.

**Spec:** User-approved choice A in chat, 2026-10-15: infer unseen head corners and wraparound from the mask; long hair paints body back/sides to measured extent, with short strands at the front shoulders.

## Global Constraints

- `rule` mode must remain byte-identical to the recorded four golden hashes.
- No VLM schema, prompt, or transport changes.
- No new dependency; use the per-request SCHP class map already passed into `extract()`.
- Hair body paint must preserve the shirt front except for shoulder strands; preserve all existing skin validation invariants.
- Missing/invalid mask evidence falls back to today's rule render.

## Review Focus

- Rounded ∩ hair mask with background at the top corners must not render skin-colored corner gaps: test both corners fill while observed face-class cells remain skin.
- A central part-line must not be indiscriminately filled as hair: test face-class (skin/scalp) cells remain observable.
- Asymmetric mask must retain asymmetry in `raw` and mirror the profile in `symmetrized`: test both side profiles.
- Long hair reaching the shoulder band must extend body back/sides but not cover the shirt center: test exact row/region behavior.
- Short hair, mask unavailable, and `rule` mode must not paint body hair: test no body changes and golden hashes.

---

### Task 1: Infer unobserved arch corners and curved head wrap

**Files:** `skinmaker/hairstencil.py`, `tests/test_hairstencil.py`, `tests/test_render.py`

**Interfaces:** Preserve `mask_stencil(seg, face, img_size, symmetry) -> HairStencil | None`; evolve `HairStencil` from uniform `side_rows` to per-column profiles for right/left/back. Keep `rule_stencil()`'s consumed output equivalent to existing geometry.

- [x] Add tests: an ∩ fixture leaves background in top-corner source cells yet produces covered front corners; explicit FACE-class part cells remain uncovered; side/back profiles curve rather than become uniform full-width row counts; raw/symmetrized behavior remains distinct.
- [x] Run the new tests and verify expected failures against current uniform-row behavior.
- [x] Implement mask-only unknown-cell arch inference and per-column side/back profile projection/inference. Keep face-class cells as skin; only infer from background where adjacent arch evidence supports coverage.
- [x] Adapt `render_head()` to consume profiles. Rule path must retain its existing byte-identical golden hashes.
- [x] Run focused tests: `tests/test_hairstencil.py`, `tests/test_render.py`.
- [x] Commit this independently.

### Task 2: Derive shoulder-length extent and render body hair

**Files:** `skinmaker/hairstencil.py`, `skinmaker/colors.py`, `skinmaker/render.py`, `tests/test_hairstencil.py`, `tests/test_render.py`, `tests/test_colors.py`

**Interfaces:** Add a body-hair extent to `HairStencil`; mask mode derives it from contiguous SCHP hair below/alongside the face into the shoulder band. `render_body(..., hair_stencil=None)` paints hair only for a mask stencil with observed body extent.

- [x] Add tests: short/no shoulder hair yields zero body coverage; hair extending to shoulders yields body back and side coverage to measured rows plus only outer shoulder strands on the front; shirt center and neck remain visible; rule/no-mask output stays unchanged.
- [x] Run tests and verify expected failures against current head-only stencil.
- [x] Implement extent extraction and body rendering; paint after shirt and neck so hair overlaps only the intended shoulder/upper-body cells.
- [x] Run focused tests and verify validation invariants on classic/slim skins.
- [x] Commit this independently.

### Task 3: Verify real fitting photos and full suite

**Files:** `out/hair_ab.py` (if needed), plan checklist only.

- [ ] Extend/run the existing A/B board on the user's three archived input photos for mask+symmetrized, mask+raw, and rule.
- [ ] Inspect step masks and 3D previews; verify pale/bright background cases don't create bald corners and body hair doesn't obscure clothing.
- [ ] Run full suite unpiped: `.venv/bin/python -m pytest -q`.
- [ ] Build frontend if any frontend source changed; otherwise no frontend changes expected.
- [ ] Record A/B observations and final status.
