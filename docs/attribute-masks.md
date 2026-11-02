# Attribute-value shape masks — Phase 1a

## Goal

Make the 3D mask editor edit the **drawn shape** of attribute enum values, not
only hood up/down. A mask is binary occupancy; colours/patterns/shadows stay in
the render pipeline.

## Current scope (Phase 1a)

- New general asset: `assets/attribute_masks.json` + SHA approval.
- Migrated `hood.up` / `hood.down` 1:1 from `assets/hood_masks.json`.
- Seeded `headwear.cap`, `headwear.beanie`, `hood_fit.shallow` from the
  procedural renderer.
- Renderer accepts `mask_override` for the editor preview; production loads the
  approved asset. Missing mask → existing procedural path.
- Editor: key/value tree (`hood`, `headwear`, `hood_fit`), head L1/L2 faces,
  final/mask preview, save to `out/mask_editor/attribute_masks.json`.
- Gate reads the general asset/approval (policy `attribute-masks-2026-11-02`).

## Schema

```json
{"version": 1, "masks": {
  "hood.up": {"L1": {"head.front": [[0,1,...]]}, "L2": {"head.front": [...]}},
  "headwear.cap": {"L1": {"head.front": [[...]]}},
  "hood_fit.shallow": {"L1": {"head.right": [[...]], "head.left": [[...]]}}
}}
```

Face keys are `<part>.<face>`; grid dims come from `skinmaker/format.py`; only
`L1`/`L2`.

## Remaining (Phase 1b+)

- Hair (`hair_style`, `hair_length`), beard — head masks.
- Body/arms/legs: top_garment, bottom_garment, sleeve_len, inner_top,
  closure_type, collar_type, pocket_type, neckwear.
- `pattern`/`symmetry` are not shape masks (colour/pattern rules).
- Editor 3D picking/atlas for all parts; seed exporter; approval CLI.
- Paired benchmark remains deferred; gate `ready=false`.

## Run

```bash
.venv/bin/python -m uvicorn --app-dir tools/mask_editor app:app --host 0.0.0.0 --port 10483
```

Open `http://<tailnet-ip>:10483/`. Save writes the draft; production asset
approval is a separate human step.
