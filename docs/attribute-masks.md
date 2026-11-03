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

## Body hair masks (2026-11-03)

medium/long/very_long hair draws a body drape on the L1 body front/back/sides
(reference pack `l1_depth`, or legacy `body_rows`/front locks) and an L2 body
overlay. The hair mask seed now includes those body cells:

- `hair_style.long_wavy` seed: body L1 186 cells, L2 50 cells (example).
- `apply_body_hair_masks` clips/adds L1 body hair to the mask and restores the
  top colour for removed cells; L2 body hair is clipped/added on the L2 layer.
- The hood-down body-back policy wins (back skipped when hidden).
- The 3D Mask view now paints body hair blue for hair_style/hair_length, and the
  body part atlas shows the mask cells to edit.

## Head L2 hair masks (2026-11-03)

The head L2 hair is the procedural hair overlay. It was not seeded, so the L2
layer showed no mask cells (and no blue in the Mask view). Seed it by diffing the
overlay-on target against an `hair_overlay=False` baseline:

- head L2 seed: 72 cells for long_wavy/long; body L2 remains the body drape.
- `apply_head_masks` clips L2 head hair to the same mask.
- 3D Mask view + head L2 atlas now expose these cells for editing.

## hair_length preview base style (2026-11-03)

The length preview previously always used `hair_style=long_straight`, so
`hair_length=short` showed a long_straight head (only the body drape became 0).
This was a preview base-state bug, not a mask-data bug.

`hair_length` now maps to a matching base style:
`short → short`, `medium → bob`, `long/very_long → long_straight`.

Head L1 seed counts: short 146, medium 212, long 272, very_long 328;
body L1: 0/0/186/186. There is no `hair_length=normal` value (hood_fit normal is
unrelated).

## Saved-draft migration for hair_length bodies

Drafts saved before the length→style fix can carry the old long_straight body
drape on `hair_length.short`/`medium`. `/api/defaults` now preserves the user's
head edits but replaces the **body faces** with the length-matched seed:

- short/medium body L1 = 0, long/very_long body L1 = 186
- L2 body likewise 0/0/50/50
- head cells remain from the saved draft.

Reload the editor to pick up the migration.

## Other bugs found (2026-11-03)

1. **Saved drafts override new seeds.** `/api/defaults` prefers
   `out/mask_editor/attribute_masks.json`, so a key saved before a seed fix
   keeps the old shape (e.g. top_garment saved 166 vs seed 550, hair_style 278
   vs seed 328). Added `GET /api/seed?key=&value=` + **Seed로 되돌리기** button
   to reset only the selected key/value.
2. **hair_style masks clipped very_long.** Style masks were seeded at length
   `long`; intersecting with `hair_length=very_long` clipped it back to long.
   Style masks/previews now use `very_long` as their base, so style+length
   intersection no longer cuts the longest length.
3. The editor process was running stale code for the saved-draft migration;
   restart the editor after pulling.

## Combo preview (P0, 2026-11-03)

The editor now previews a **16-key combination** (14 shape keys + pattern + symmetry)
without a photo:

- `/api/defaults` exposes `enums` (16), `defaults`, `models` (classic/slim), `combo`.
- `/api/preview` accepts `{combo, model, masks, mode, key, value}`; `A.validate`
  applies cross rules (`top_garment=none` → sleeve/pattern/closure/collar/pocket
  none) and returns `effective` + `warnings`.
- Mask key/value tabs auto-sync the matching combo value (14 maskable keys);
  pattern/symmetry are combo-only. `symmetry` is metadata (no visual effect yet).
- Combo/model persist in the URL hash and localStorage.
- P0 renders classic/slim **2D**; 3D is classic front. Slim 3D, presets, 3D back/
  overlay are P1.

## Editor UI — 2D atlas (2026-11-04)

- The 2D editor is a canvas drawn on the real 64×64 classic atlas. Rects come from
  `/api/defaults` → `atlas.rects` (one box per face per layer; L1 and L2 never overlap).
- Masked texels are hatched: L1 `\` in blue, L2 `/` in orange. Boxes that contain
  mask pixels are bright; empty boxes are dimmed and light up as soon as a pixel is drawn.
- Draw by clicking/dragging on the atlas (Shift = erase). Ctrl+wheel, +/−, or the
  zoom buttons change zoom (2×–24×). Clear/Fill act on the active box only.
- 3D: left-drag paints on whichever part is under the cursor (nearest hit across parts).
  Edits show in 3D immediately (a client-side tint on the last render); the exact
  server render replaces it when it arrives.
- Pure helpers live in `tools/mask_editor/atlas.js`; `atlas.test.mjs` runs from
  `tests/test_mask_editor_atlas.py` when Node is installed.
- Known limits: slim-model masks still use the classic grid (3-px arm faces are not
  separate in the editor); the whole mask set is still sent on each preview.

## Editor UI — history, base skin, reset (2026-11-04)

- Base skin (on by default): the atlas shows the real final render (the same image as
  the 3D Final view), with empty boxes veiled. The base is always the final render,
  even in Mask view. It refreshes from the server after each edit (about 30 ms render).
- Undo/Redo: strokes, fill and clear are per-cell diffs (small). Seed and reset are
  whole-mask snapshots. History is capped at 100 commands. Shortcuts: Ctrl+Z, Ctrl+Y,
  Ctrl+Shift+Z.
- 초기 상태로 (Reset): every mask goes back to the procedural seed (`GET /api/seed-all`,
  the same hood-policy zeroing as the defaults). Combo settings are not changed. Reset
  is an undoable step, and nothing is written to disk until Save.
- Plain wheel zooms the atlas (2×–24×) around the cursor. Right-drag erases.

## Editor fixes — seeds, hair intersection, preview source (2026-11-04)

- Hair seeds are taken from the same pipeline the renderer uses (`render(head_hair_out=...)`),
  not from the rule stencil. Seeding from the rule stencil cut the side hair whenever the
  style and length masks were intersected (short hair: sides 48/64 bare vs 7/64 procedural).
- Masked hair cells keep the pipeline's strand shading; flat colour only for added cells.
- Reset (`/api/seed-all`) and the per-value seed (`/api/seed`) now share `_finalize_seed`
  with the saved-draft defaults, so the top body is refilled (back torso no longer bare).
- Preview `source`: `draft` (editor masks, default) or `production` (approved asset, what
  generation uses). The base skin follows the source; the instant tint is draft-only.
- Advisory combo warning for contradictory hair pairs (e.g. short style + long length).
- Viewer `dispose()` releases the loop, listeners and GPU resources.
- Draft schema 3: the first load of a draft saved before this fix backs the file up to
  `out/mask_editor/attribute_masks.pre-v3-<stamp>.json`, re-seeds the hair keys, and refills
  legacy top bodies. Later loads do nothing. Editor tests run against a temp OUT and never
  touch the real draft.
- Slim-specific masks: slim arm faces that are narrower than classic (front, back, top,
  bottom: 3 px vs 4 px) can carry a per-entry `"slim"` sub-dict with grids of the slim width.
  `attribute_masks.resolve_model(masks, model)` swaps those in for slim renders only; classic
  renders ignore them. The editor's model select switches the atlas to the slim layout; a
  slim override starts as a copy of the classic columns on first edit, so the visible cells
  do not jump. Existing assets have no slim sub-dicts and are unchanged.
- Photo-driven seeds: `POST /api/photo` observes an uploaded photo (colours, SCHP hair
  silhouette; no VLM) and the seeds and preview use it until `DELETE /api/photo`. Without a
  photo the fixture is used. Uploading does not overwrite drafts; 초기 상태로 or 이 값만 seed로
  re-seed from the photo (undoable). Process-wide state: one photo at a time for everyone
  who can reach the editor.
