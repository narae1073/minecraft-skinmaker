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
- Current head remains flatter/darker than references; added tapered outer
  corners `(3,4,5,5,5,5,4,3)` and one reference-tone dark + one light accent
  column per face (colour only).
- Remaining gap is style-specific L2 silhouette/highlight variation, not depth.
