# Production status gate (v2, 2026-11-02)

Fail-closed aggregate gate. It is intentionally not wired into normal CI while
human approvals are incomplete; run it for release decisions.

```bash
.venv/bin/python scripts/production_status.py
# exit 1 with blockers, writes out/production_status.json
```

It checks:

- holdout size 50–100, structural/quality pack QA, train-split provenance;
- hair holdout n≥50 and p90≤0.10;
- hood-up holdout n≥3 (corpus ceiling; n≥10 needs more full-crown data);
- hood-down holdout n≥5 **and p90≤0.25** (count-only passing is a false positive);
- eyes: **user-accepted, data-limited** — holdout n is reported but not gated;
- deterministic 50-case render matrix;
- approved eye/hood templates (human review: ≥3 eyes, ≥2 hood-up, ≥1 hood-down);
- approved paired photo→skin benchmark: ≥1 approved, target 30, structural acceptance.

Current state (2026-11-02): `ready=false`. Blockers: hood-down holdout n,
approved hood-up 0/2, approved hood-down 0/1. Paired benchmark: **72 approved /
84 pairs, accepted=true** (target 30 met). Decisions D1–D7, evidence and residual
risks are recorded in [production-gate-v2.md](production-gate-v2.md); the gate
must not claim `ready=true` until those residuals clear.
