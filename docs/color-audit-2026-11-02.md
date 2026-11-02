# Color sampling audit — 2026-11-02

Method: `quality.inspect(pair_photo)` → `colors.extract(photo)` → render with the
pair's validated attributes. No VLM re-run. The skin pair snapshots are the
pre-fix outputs.

## Root causes found

| Pair | Note | observed top | observed outer | observed inner | Pre-fix output |
|---|---|---|---|---|---|
| up_long_04 | teal jacket → black | `#498ba4` (correct) | `#111011` (shadow) | `#400e0a` (dark) | black |
| up_long_09 | gray hood → black | `#a6bbc0` (correct) | `#27252e` (shadow) | missing | black |
| down_long_08 | beige hoodie → light blue | `#cae5ff` (background) | `#8e7a63` (beige) | `#302018` | light blue |

1. **Dark outer sample override**: the jacket/outer override trusted a near-black
   sample (shadow/pants) over a confident, brighter top. Fixed: for layered
   jackets (`inner_top != none`) only, if the inner sample is dark/missing and
   the top is >40 luma brighter, keep the top.
2. **Hoodie outer ignored**: `hoodie` was not in the outer-override candidates,
   so a background-contaminated top (`#cae5ff`) was used instead of the beige
   outer (`#8e7a63`). Fixed: hoodie joins the outer candidates.
3. **Background/inner contamination remains** for pink/white: top samples pick
   `#ddd9d8` / `#a6cbe2` / `#acc5e3`; outer is missing. Needs a region/reject
   change (separate).
4. **Hair low confidence/dark samples**: gold hair was sampled as
   `#ddc19c` (conf=False), `#8d6648` (conf=False), or near-black; the renderer
   falls back to default brown. Needs a hair-region/VLM-bbox audit.

## Fixed in this pass

- teal jacket: `(27,26,27)` → `(73,139,164)`
- gray hood: `(37,36,44)` → `(166,187,192)`
- beige hoodie: `(198,224,250)` → `(142,122,99)`
- A/B: `out/color_audit/color_audit_ab.png`

## Still open

- pink jacket → white (`hood_down_long_hair_00`)
- white hood → light blue (`hood_down_short_hair_09`, `hood_up_long_hair_08`)
- white pants → orange (`hood_down_long_hair_03`) — bottom sample
- gold hair → brown/black (`hood_down_long_hair_01`, `hood_up_long_hair_00/01/02/06`)


## Round 2 — hair fallback + rejected top-reject

- **Top background reject experiment (rejected)**: passing `bg` chroma to the top
  bands made pink → MISSING, white hood → brown, teal → red. The region, not the
  reject alone, is the problem; reverted.
- **Hair low-confidence fallback**: if the hair sample is not confident but
  light (luma > 90), use the measured colour instead of DEFAULT_HAIR. Gold
  `#ddc19c` (conf=False) now renders blond; `#8d6648` renders brown (closer than
  default). Dark low-confidence samples keep the default.
- A/B: `out/color_audit/hair_audit_ab.png` (old dark → new blond/brown).
- Remaining hair notes: `up_long_00/02/06` — confident dark samples (hat/shadow);
  needs a better hair region/VLM bbox audit.

## Round 3 — white/beige colour cast (WB cap)

Strong skin-anchored white-balance gains (R≈0.80–0.87, B≈1.14–1.15) turned
white/beige garments light blue (`#c7e1ff`, `#a6cbe1`, `#afc7e2`). With
`WB_CLIP = 1.10`, gains above 10% are treated as uncertain and not applied
(identity), so the raw near-white/beige survives.

- white hood 1: light blue → near-white
- white hood 2: light blue → near-white
- beige hoodie: light blue → beige (outer still supplies the beige)
- A/B: `out/color_audit/wb_ab.png`
- teal/gray stay correct via the earlier outer guard.

Remaining: pink jacket (region still white), white pants (bottom remains
orange), dark gold hair, hood geometry.

## Round 4 — SCHP upper-clothes top (raw RGB)

The WB cap alone left pink `#e4cbc7` desaturated to `#cbc5c4` (a 0.91 gain is
within the 10% cap). A tighter cap (1.05) fixed pink but broke the lipstick WB
confidence contract, so it was rejected.

Instead, the SCHP upper-clothes mask (class 4) now provides the top colour from
the **raw RGB**, bypassing the skin-anchored WB for the garment sample. Bands
still fallback when the mask is small.

- pink jacket: white/gray → `#e4cbc7` pink
- white hood: light blue → near-white
- beige hoodie: light blue → beige (outer supplies beige)
- A/B: `out/color_audit/seg_ab.png`

Remaining: white pants (bottom sample), dark gold hair, hood geometry.
