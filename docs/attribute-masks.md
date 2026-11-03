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

## Phase 2b — bottom_garment

- `render_legs` is followed by `apply_bottom_masks`: if a `bottom_garment.<value>`
  mask exists, leg garment rows 0–8 are clipped (mask → sampled bottom colour,
  outside → skin). Shoes rows 9–11 stay procedural.
- Editor seeds `bottom_garment` masks by diffing the procedural render against
  `bottom=none` (jeans/shorts/skirt/pants 352 cells; none blank). The seed is a
  starting silhouette; shorts/skirt row boundaries may need painting because the
  current diff covers the same garment rows.
- Production asset/approval unchanged; masks are editor drafts.

## Phase 2c — structure keys

- Editor keys: `closure_type` (none/zipper/buttons/open), `collar_type`
  (none/crew/v_neck/shirt/hood), `pocket_type` (none/patch), `neckwear`
  (none/tie).
- `structure.draw_*` accepts a body.front mask; `apply_structure` clips zipper,
  buttons, collar, open-front and patch pockets to the mask.
- `render_body` clips the neckwear tie to the `neckwear.tie` mask (inner-top
  throat cells remain).
- Seeds: zipper 11, buttons 16, crew 2, patch 6, tie 2 cells (neckwear uses the
  known tie cells because the synthetic QA tie/inner colours can match).
- Production asset unchanged; editor drafts.

## Phase 2d — inner_top + approval CLI

- `inner_top` (none/shirt/tee/knit): body-front throat cells and arm sleevecuff
  cells are clipped to the mask; editor seeds by diffing the procedural render
  against `inner_top=none` (38 cells for shirt/tee/knit).
- `scripts/approve_attribute_masks.py` promotes the editor draft to
  `assets/attribute_masks.json` and writes `attribute_masks_approval.json` with
  the policy + SHA. It requires an explicit `--yes` (human gate) and validates
  the schema first.
  - `python scripts/approve_attribute_masks.py --draft out/mask_editor/attribute_masks.json --yes`
- The gate reads the promoted asset; the paired baseline stays stale.

## Phase 2e — top_garment (final shape key)

- `top_garment` (tee/hoodie/jacket/shirt/sweater/vest/uniform/apron/overalls/
  dress/none) participates in body, arm and leg masks.
- Body: the top mask clips body garment cells (outside → skin), preserving the
  pattern/texture inside.
- Arms: the top mask combines with `sleeve_len` (vest etc. can have no sleeves).
- Legs: `apply_top_leg_masks` clips dress/top garment rows 0–8; shoes stay.
- Editor seeds top masks from the `top_garment=none` diff across body/arms/legs
  (tee/vest 550, dress 582 cells).
- All 14 shape keys are now editable; `pattern`/`symmetry` are colour/pattern
  rules, not shape masks.

## Load / troubleshooting

- The editor boot requests `/api/defaults` (about 0.6 s on the host; it seeds
  the masks), then renders one preview. Expect a few seconds, not a minute.
- A module-level error before `boot()` leaves the status at “불러오는 중…” and
  no `/api/defaults` request appears in the server log. The viewer's TDZ
  (`PART_UV2` before `HEAD2`) caused exactly that and is fixed; `index.html`
  now has an error handler that prints the error into the status.
