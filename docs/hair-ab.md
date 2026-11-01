# Hair reference A/B

```bash
.venv/bin/python scripts/build_hair_ab.py
```

Produces `out/production_benchmark/hair_ab.png`: current long/short styles on
the left, four train-only reference heads per length on the right.

## 2026-11-01 read

- Center depth-5 fringe matches the human long-bang prior.
- Reference L2 is mostly solid; row3 has no interior alpha gaps, so unsupported
  interior holes were not added.
- Current L2 is now included correctly (L1+L2 composite; the first version
  accidentally cropped L1 only). Head remains flatter than references; added
  tapered outer corners `(3,4,5,5,5,5,4,3)` and one reference-tone dark + one
  light accent column per face (colour only).
- Remaining gap is style-specific L2 silhouette/highlight variation, not depth.

## Rejected experiment (2026-11-01)

Clearing L1/L2 front side cells outside the bang profile was tested and
rejected: it created bald temple gaps and a much worse hairline. The current
stencil side hair is retained; the fringe profile only adds/overrides the top
hairline, it does not erase the photo-derived side silhouette.
