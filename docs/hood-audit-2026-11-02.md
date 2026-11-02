# Hood geometry audit — 2026-11-02

Method: render the six `hood_up_*` notes with the current code + final head masks,
compare with the old pair skins, inspect front-right QA renders.

## Resolved by the final masks

| pair | note | finding |
|---|---|---|
| hood_up_short_hair_03 | hood too deep, bangs hidden | final front mask opens the forehead; bangs/face visible |
| hood_up_long_hair_17 | hair outside the hood missing | hair is visible around the hood edges |
| hood_up_short_hair_05 | deep hood covers forehead | source is deep; current face opening is acceptable |

A/B: `out/hood_audit/hood_audit_1.png`

## Still open

| pair | note | blocker |
|---|---|---|
| hood_up_short_hair_07 | white cap under the hood | no `headwear` attribute or hat colour sample |
| hood_up_short_hair_11 | hat under the hood | same |
| hood_up_short_hair_09 | shallow hood, ears visible | no hood-depth / ears attribute; final side mask hides them |

A/B: `out/hood_audit/hood_audit_2.png`

## Proposed next feature

Add `headwear` (`none`/`beanie`/`cap`) + a hat-colour sample, render a brim band
at the hood opening. Ears need `hood_fit` (`shallow`/`deep`) or a mask-side cut.


## Round 7 — headwear

Added `headwear` (`none`/`beanie`/`cap`), a VLM hint and UI labels. Hood-up renders
a 1px brim at head-front row 1; cap uses a light heuristic, beanie a dark one.

- `hood_up_short_hair_11`: VLM E2E → `headwear=beanie`; brim rendered.
- `hood_up_short_hair_07`: VLM E2E → `beanie` (source is a white cap; UI can switch
  to `cap`), forced-cap A/B shows the light brim.
- A/B: `out/hood_audit/headwear_ab.png`

Still open: `hood_up_short_hair_09` shallow hood/ears. Hat colour is a heuristic
until a headwear colour sample exists.


## Round 8 — hood_fit / ears

Added `hood_fit` (`normal`/`shallow`/`deep`) and a UI label. With hood up and
`hood_fit=shallow`, a 2px skin-shaded ear patch is drawn after the hood overlay
at the side-front (right u6 / left u1, v4–5), so the final mask does not cover it.

- VLM E2E on `hood_up_short_hair_09` still returns `hood_fit=normal`; the UI can
  switch to `shallow`. A/B: `out/hood_audit/ears_ab.png` (old vs shallow ears).

All six hood notes now have a path: 03/17/05 via the final masks, 07/11 via
`headwear`, 09 via `hood_fit=shallow` (manual when the VLM misses it).
