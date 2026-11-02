> **2026-11-02 update (gate v4 / attribute masks):** the gate now reads
> `assets/attribute_masks.json` + `assets/attribute_masks_approval.json`
> (policy `attribute-masks-2026-11-02`). `hood.up/down` were migrated 1:1 from
> the old hood asset. The paired baseline is stale until re-approved.

# Production gate v3 — 2026-11-02 (mask-driven hood)

Gate v2 still required pack hood template approvals and pack hood holdout
coverage. The shipped hood is now driven by `assets/hood_masks.json` (head
L1/L2, including bottom), so those pack checks no longer describe production.
Gate v3 replaces them and makes paired-baseline staleness explicit.

## Decisions

| Item | v2 | v3 |
|---|---|---|
| hood source | pack templates + holdout n/p90 | **mask asset + human approval file** |
| hood holdout coverage | blocker | **reported only** (mask-driven) |
| approved hood templates | 2 up / 1 down | **removed** |
| mask approval | — | `assets/hood_masks_approval.json` with asset SHA + policy |
| paired benchmark | approved count + accepted | also requires `benchmark_baseline.json` with the current mask SHA and policy |
| eyes | waived (user-accepted) | unchanged |
| hair / holdout / QA / approved eyes / pairs | gated | unchanged |

`RENDER_POLICY = "mask-hood-2026-11-02"`. A changed mask asset or render policy
invalidates the paired baseline until the pairs are regenerated and re-approved.

## Current output (2026-11-02)

```json
{
  "version": 3,
  "ready": false,
  "blockers": ["paired benchmark baseline missing (regenerate/re-approve)"],
  "approved": {"pairs": 72, "eyes": 4, "hood_masks": true}
}
```

The 72 approved pairs are **pre-mask v1**. The gate refuses `ready=true` until
`out/paired_benchmark/benchmark_baseline.json` records the current mask SHA and
policy **after** a new round of human approval.

## Path to ready

1. Re-render the 74 hood pairs with the current renderer and re-approve them.
2. Write `out/paired_benchmark/benchmark_baseline.json`:
   ```json
   {"mask_sha": "<assets/hood_masks.json sha256>", "policy": "mask-hood-2026-11-02"}
   ```
3. Run `scripts/production_status.py`; it should have no blockers.
4. Optional: in-game Minecraft check (chin/bottom/up/down).
