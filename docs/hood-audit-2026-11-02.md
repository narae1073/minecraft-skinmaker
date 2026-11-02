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
