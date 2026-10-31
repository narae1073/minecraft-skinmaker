# Paired photo → skin benchmark

The 600+ reference skins are **unpaired**: they cannot validate photo→skin
likeness. This directory is for hand-approved pairs.

## Layout

```
out/paired_benchmark/
  pairs/<id>/
    photo.jpg|png|webp
    skin.png          # 64x64 RGBA
    meta.json         # {"approved": true, "notes": "..."}
```

- `approved: true` means a human accepted this skin as the reference output for
  that photo. Only approved pairs count toward the production gate.
- Unapproved pairs are regression-pilot candidates; they do **not** count as
  ground truth.
- `photo` must be a clear single-person image; `skin` must be a valid 64×64 RGBA
  texture.

## Review

```bash
# render [photo | front | back] for every pair
.venv/bin/python scripts/build_pair_review.py --root out/paired_benchmark

# after a human looks at review_sheet.png
.venv/bin/python scripts/review_pairs.py list
.venv/bin/python scripts/review_pairs.py approve <id> --notes "why"
.venv/bin/python scripts/review_pairs.py reject <id> --notes "what is wrong"
```

Approval is a human decision; the tooling never auto-approves.

## Validate

```bash
.venv/bin/python scripts/check_paired_benchmark.py \
  --root out/paired_benchmark --out out/paired_benchmark/report.json
```

The report requires at least one approved pair and no structural problems on
approved pairs before `accepted` is true.

## Acceptance target

- 30–50 approved pairs, stratified by hair style, hood up/down, and clothing.
- ≥60% human preference over the current baseline, with no structural
  regression.
- Structural invariants (validate_image, hair/eye/hood checks) 100%.

A 10-photo seeded pilot of current outputs is a **regression baseline**, not
approval data; set `approved: false` until a human has reviewed the skin.
