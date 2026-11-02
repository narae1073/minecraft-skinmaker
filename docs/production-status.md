# Production status gate (v3, 2026-11-02)

Fail-closed aggregate gate. It is intentionally not wired into normal CI while
human approvals are incomplete; run it for release decisions.

```bash
.venv/bin/python scripts/production_status.py
# exit 1 with blockers, writes out/production_status.json
```

It checks:

- holdout size 50–100, structural/quality pack QA, train-split provenance;
- hair holdout n≥50 and p90≤0.10;
- **hood masks**: `assets/hood_masks.json` approved by
  `assets/hood_masks_approval.json` (SHA + policy); hood holdout coverage is
  reported but not gated (the hood is mask-driven);
- deterministic 50-case render matrix;
- approved eyes templates (≥3; eye holdout n is user-accepted, not gated);
- approved paired benchmark: ≥1 approved, target 30, structural acceptance;
- **paired baseline**: `benchmark_baseline.json` must match the current mask SHA
  and render policy; a changed mask/renderer blocks until re-approval.

Current state (2026-11-02): `ready=false`; the only blocker is
**paired baseline missing** — the 72 approved pairs are pre-mask v1. Decisions
and the path to ready are in [production-gate-v3.md](production-gate-v3.md).
