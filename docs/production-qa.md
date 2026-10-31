# Production QA matrix

Deterministic gate for hair/eyes/hood/noise changes. This complements, but does
not replace, the visual sub-agent.

```bash
.venv/bin/python scripts/run_production_qa.py --out out/production_qa/report.json
```

## Matrix

- styles: short, pixie, bob, long_straight, long_wavy, curly, ponytail, bun
- hood: none / up / down
- noise: 0% and 50%
- one explicit beard=`full` case

## Hard checks

- `validate_image` structural validity.
- No beard pixels in center-jaw rows 6–7 (side hair is allowed).
- Both eye regions contain non-skin pixels.
- Hood-up top face has no isolated 1px accent islands (seam/highlight allowed).
- Eye rows 4–5 are not covered by a hood L2 shell.
- Noise-on run must not scatter the hood crown.

Exit status is non-zero on any failed case. Pixel-level QA should also inspect
the 2D UV directly; sub-agent verdicts are secondary.
