# Production gate v2 — 2026-11-02 decisions (D1–D7)

Gate v1 (2026-10-31) required holdout n≥20 for eyes, ≥10 for hood-up and ≥5 for
hood-down. The reference corpus cannot support those numbers: there are only 3
unique eye patterns, 3 extractable hood-down patterns and 3 full-crown hood-up
patterns in the 98-skin holdout. This document records the round-closure
decisions and the honest residual blockers. `ready=true` is **not** claimed.

## Decisions

| ID | Decision | Result |
|---|---|---|
| D1 | Eyes target | **Waived** as a holdout-n gate. The user accepts the current eye style; eye coverage n is still reported, but is data-limited and not a release gate. Approved eyes (4) remain required. |
| D2 | hood-down | Keep **n≥5** and add a **coverage p90 ≤ 0.25** gate. Count-only passing is a false positive: the v2 proposal reaches n=5 but p90=0.328, so it stays blocked. |
| D3 | hood-up | Re-baseline to **n≥3** (current corpus ceiling: 3 full-crown holdout). Reaching n≥10 requires more full-crown reference data; re-splitting to 10 holdout would leave 11 train refs and collapse the ≥10-member clusters. |
| D4 | Approved templates | Review the **active pack** templates (4 up / 2 down) instead of relying on the candidate queue (only 1 up candidate exists). Review sheet: `out/production_benchmark/pack_review/review_sheet.png` (`up_0..3`, `down_0..1`). Human approval/record is still pending. |
| D5 | Pack v2 | **Hold.** `out/production_benchmark_v2/` and `out/pack_v2/` are proposal-only; the committed split/pack remain v1 (550/98). v2 changes only the hood-down count, not hood-up or eyes; adopting it also needs eye approvals re-applied, goldens/tests and an A/B. |
| D6 | Label-mismatch pairs | Excluded from hood strata while kept as pairs: `hood_down_short_hair_06`, `hood_down_long_hair_12` (approved) and `hood_up_short_hair_00` (unapproved). |
| D7 | Round closure | **Documented closure** (gate v2 + residuals), not `ready=true`. The paired benchmark is green; the remaining blockers are data/approval limited and are listed below. |

## Gate v2 targets

| Check | v1 | v2 |
|---|---|---|
| holdout size | 50–100 | 50–100 |
| hair | n≥50, p90≤0.10 | n≥50, p90≤0.10 |
| eyes | n≥20 | **waived** (user-accepted, data-limited) |
| hood-up | n≥10 | **n≥3** (corpus ceiling) |
| hood-down | n≥5 | **n≥5 and p90≤0.25** |
| approved eyes / hood-up / hood-down | 3 / 2 / 1 | 3 / 2 / 1 |
| paired | ≥1 approved, target 30 | ≥1 approved, target 30 |
| QA matrix | 50 cases | 50 cases |

## Evidence — 2026-11-02

- Committed benchmark v1: split 550 train / 98 holdout; hair n=98 p90=0.080;
  eyes n=3; hood-up n=3; hood-down n=0.
- Data the user added: 82 reference skins (hood-up 129, hood-down 63 total;
  82 new files) and 74 people photos (hood-up 36, hood-down 38, AVIF converted).
- Proposal benchmark v2 (not adopted): split 619/100; hair n=100 p90=0.083;
  eyes n=3; hood-up n=3; hood-down n=5 with p90=0.328 (fails D2's 0.25).
  Pack v2: 4 up / 2 down templates, source counts up=22, down=24.
- Paired benchmark: **84 pairs, 72 human-approved, `accepted=true`**; 12
  unapproved (10 old reverted pairs, 2 new). The 30-pair target is met.
- Approved templates: eyes 4; hood-up 0/2; hood-down 0/1. Candidate queue:
  eyes 19, hood-up 1, hood-down 3 — hence the active-pack review path (D4).
- Deterministic QA matrix: 50 cases, ok.

## Current gate output (v2)

```json
{
  "version": 2,
  "ready": false,
  "blockers": [
    "hood_down holdout n below 5",
    "approved hood_up templates 0 < 2",
    "approved hood_down templates 0 < 1"
  ],
  "approved": {"pairs": 72, "eyes": 4, "hood_up": 0, "hood_down": 0}
}
```

## Residual blockers / path to `ready=true`

1. **hood-down**: v1 committed corpus has n=0; the v2 proposal has n=5 but
   p90=0.328. Either collect more/cleaner hood-down references or improve the
   templates until p90≤0.25, then adopt the split/pack.
2. **Approved hood templates**: visually review
   `out/production_benchmark/pack_review/review_sheet.png` (4 up / 2 down) and
   record approvals. Without human approval this stays blocked by design.
3. **Eyes**: waived for style; no further action this round.

## Round closure (D7)

The round closes with gate v2 defined, the paired benchmark accepted (72
approved), and the three residuals above documented. Production readiness is
still **false**; do not claim `ready=true` until the residuals are cleared.
