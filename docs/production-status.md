# Production status gate

Fail-closed aggregate gate. It is intentionally not wired into normal CI while
required human approvals are zero; run it for release decisions.

```bash
.venv/bin/python scripts/production_status.py
# exit 1 with blockers, writes out/production_status.json
```

It checks:

- holdout size 50–100, structural/quality pack QA, train-split provenance;
- hair holdout n≥50 and p90≤0.10;
- eye/hood-up/hood-down holdout sufficiency;
- deterministic 49-case render matrix;
- approved eye/hood templates (human review);
- at least one approved paired photo→skin example, target 30;
- approved paired benchmark structural acceptance.

Current blockers include eye/hood holdout shortage and zero approved templates
and pairs. Coverage alone can never make the gate pass.
