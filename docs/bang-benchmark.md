# Bang / exposure benchmark

The automatic reference-bang classifier was too noisy. This benchmark requires
human labels on train-only reference head fronts.

```bash
.venv/bin/python scripts/build_bang_benchmark.py
# inspect out/production_benchmark/bang_review_sheet.png
.venv/bin/python scripts/review_bangs.py set <id> --depth 0-8 --exposure covered|partial|exposed
.venv/bin/python scripts/review_bangs.py summary
```

- 60 candidates sampled deterministically from the 550 train references.
- Labels live in `out/production_benchmark/bang_labels.json`.
- `summary` gives median depth and exposure counts by long/short, plus a
  label-quality guard. Degenerate sets (e.g. 19/20 `depth=5, covered`) are
  marked unusable and must not be used to fit a prior.
- No generated hair or renderer policy changes are derived until labels exist.
- The current policy remains: loose=5-row eyebrow cover, short/pixie
  exposure-aware 3/5, tied-up=2; L2 top-eye row accent only.


## Current label audit (2026-11-01)

60 labels: **54/60 depth=5**. A dominant depth is accepted as a real prior; the
guard only rejects extreme collapse (>95% one depth) or >20% depth/exposure
contradictions. This set has 90% depth5 and 8/60 contradictions, so it is
usable. `assets/bang_prior.json` records median depth 5 for both long and short.
Depth remains "hair rows from top at center columns"; exposure is forehead/
eyebrow visibility, not eye visibility.


## Renderer link

`skinmaker.hairstencil` loads `median_depth` from `assets/bang_prior.json` for
loose styles and the short/pixie visible-bang fallback. Current median is 5;
the SCHP exposure rule and tied-up 2-row rule still take precedence.
