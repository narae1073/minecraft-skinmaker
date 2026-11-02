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

## Phase 1b — hair + beard keys

Added editor keys with a head post-pass:

- `hair_style` (8 values) and `hair_length` (4 values): L1 hair cells outside the
  combined mask are restored to skin; L1 mask cells are painted with the hair
  colour; L2 is clipped to the same mask (falls back to the L1 grid when L2 is
  absent). When both style and length masks exist they intersect.
- `beard` (`stubble`, `full`): mask cells add hair-shaded beard cells on the
  head front (there is no procedural beard).
- Editor preview uses `hood=none` for hair/beard so cells are visible; hood up
  for hood/headwear/hood_fit.
- These masks are **empty by default**; the user paints them. A procedural seed
  exporter and the all-part 3D/atlas remain Phase 2/3.

### Hair seed (2026-11-02)

`/api/defaults` now seeds `hair_style.*`/`hair_length.*` from the current
procedural `render_head` hair cells (L1); L2 falls back to L1 in the renderer.
`beard.*` stays blank because there is no procedural beard. This gives the
editor a real starting silhouette instead of an empty grid. The seed is
editor-only (draft); production approval is still separate.

## Phase 2a — all-part editor + sleeve_len

- Editor data model is now all 6 parts (head, body, both arms, both legs) and
  all 36 part.faces with their real dimensions from `skinmaker/format.py`.
- 3D picking is generalized (`viewer.pick(part, layer, x, y)`) to the body, arm
  and leg meshes (the UVs already existed); L2 mesh visibility is coordinated
  across all parts.
- First body key: `sleeve_len` (`none`/`short`/`three_quarter`/`long`).
  - `render_arms` accepts the sleeve mask and clips each arm cell to it
    (mask cell → sleeve/pattern colour; outside → skin).
  - Editor seeds sleeve masks from the procedural row ranges (short 192 cells,
    long 384 across both arms); `none` blank.
- Production asset/approval unchanged (no sleeve masks yet); the editor seed is
  draft-only. Body/legs keys beyond sleeve remain Phase 2b.
