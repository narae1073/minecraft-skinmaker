# Production roadmap — photo → Minecraft skin

## Challenge to the original goal

The original goal ("pixel-perfect production-ready" via template extraction and a
reference-skin holdout) is not a valid acceptance test as written.

1. **The reference skins are unpaired.** A holdout skin has no corresponding
   input photo, so "visual similarity to the holdout" cannot measure the
   photo→skin pipeline. It can only measure style/template coverage. Using it as
   a production gate would reward copying or style overfit.
2. **"Pixel-perfect" is undefined.** Production quality is a set of measurable
   properties: anatomical/face integrity, eye/hair/hood structure, clothing,
   palette, no isolated pixels/holes, style match, identity, latency, fallback.
3. **The corpus is biased.** 682 skins are anime/cartoon-heavy; 34 hats were
   excluded; only 11 hood-down. Reference-derived templates must be filtered and
   evaluated on stratified holdouts, not treated as the target distribution.
4. **QA sub-agents are not a deterministic gate.** They are useful for visual
   review, but they missed a noise-pass defect because their renders had no noise
   and their prompt lacked pixel-hygiene checks. Deterministic UV/render checks
   must be the gate; VLM/human review is an additional signal.
5. **The current pack was trained on all references**, including the split
   holdout. Its score is contaminated. A train-only pack is required for an
   honest baseline.

## Revised goal

Raise the photo→skin pipeline to a **measured production gate**:

- 100% structural invariants on regression fixtures (no isolated pixels, 1px
  holes, disconnected hood shell, beard, face/eye damage).
- Reference-style coverage on a strict train/holdout split (not a likeness score).
- A small **paired photo→skin benchmark**: ≥60% human preference over the
  current baseline, stratified by hair/hood/style, before "production quality".
- No regression in existing head/top/bottom QA; documented latency, fallback,
  licensing and failure cases.

Templates are a means; the gate is measured output quality on defined data.

## Phases

### Phase 0 — Benchmark and specification (started)

- Deterministic stratified split: `out/reference_skins` → 550 train / **98
  holdout** (hats/caps excluded).
- Defect taxonomy: isolated pixels, 1px gaps, grid/checker, disconnected trim,
  hood/hair holes, face/eye corruption, style mismatch, palette/identity.
- Paired pilot protocol: 30–50 photo + hand-approved skin pairs, stratified.

### Phase 1 — Evaluation harness (done)

- `skinmaker/reference_qa.py` + `scripts/build_reference_benchmark.py`.
- Structural validation of every template shape/mask.
- Honest train-only coverage baseline; see below.
- Deterministic render invariants stay in pytest; visual sub-agents get a
  pixel-hygiene/noise prompt (`docs/qa-hair.md`).

### Phase 2 — Template library v2 (train-only, review queue started)

- A relaxed eye extractor raised holdout eye matches from 3 to 93, but produced
  zero-sclera iris-only templates. Rejected: `reference_qa.quality_ok` now
  requires sclera/iris support and non-flat hair tone maps. Coverage alone is not
  a quality signal.
- Human review queue: 19 eye / 1 hood-up / 3 hood-down candidates in
  `out/production_benchmark/template_gallery.png`; none approved yet. Six eye candidates are objectively shortlisted (`recommended=true`) for faster human review.
- Approved candidates now rebuild the pack via `apply_template_approvals`.

- Extract hair L2/eyes/hood templates **only from the train split**; keep the
  holdout untouched.
- Expand eye/hood samples with seed labels; filter costume/animal hoods; add
  style labels and cluster coverage.
- Coverage targets: hair p90 distance ≤0.10; eyes ≥20 holdout samples; hood-up
  ≥10; hood-down ≥5 before claiming style coverage.

### Phase 3 — Structural composition (QA gate started)

- Deterministic matrix: `scripts/run_production_qa.py` (49 cases, styles × hoods × noise + beard).
- Warp templates to the measured hairline/head; no isolated pixels; hood after
  noise; face/eye/beard invariants.
- Add feature flags and fallback to the current renderer.

### Phase 4 — Paired validation (scaffold started)

- `skinmaker/paired_benchmark.py` validates hand-approved pairs; `accepted` requires ≥1 approved pair with zero structural issues.
- 10-photo current-output pilot seeded with `approved:false`; review sheet at `out/paired_benchmark/review_sheet.png`. The sheet shows the current outputs are still rough; they are a regression baseline, not ground truth.
- Next: 30–50 human-approved pairs; human preference + VLM + structural checks.
- Tune template selection; publish failures, not just wins.

### Phase 5 — Production hardening (gate started)

- Aggregate fail-closed gate: `scripts/production_status.py` (currently NOT READY).

- Full skin (clothing/face/identity), UI, latency/cost, licensing, retention,
  monitoring, rollback.

## First-phase baseline (2026-10-31, train-only pack)

- Split: 550 train / 98 holdout; 34 hats excluded.
- Structural pack: **PASS**.
- Holdout style coverage (lower is better):
  - hair: n=98, mean 0.061, p90 **0.080**
  - eyes: n=3 (insufficient)
  - hood-up: n=3 (insufficient)
  - hood-down: n=0 (insufficient)
- Paired photo→skin benchmark: **missing**.
- The committed pack is now **train-only** (550 train refs, split metadata in the pack); the 98 holdout refs are unseen. Train-only re-score is identical: hair p90 **0.080**.

## Immediate next actions

1. Expand/clean eye and hood extraction on the train split (the current holdout
   samples are too small to validate).
2. Build a 30–50 paired photo→skin pilot; this is the missing ground truth.
3. Generate a train-only production pack and rerun the holdout coverage.
4. Add render-invariant tests for every template variant (noise 0 and 50%).
