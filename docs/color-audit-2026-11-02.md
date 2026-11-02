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

## Round 5 — white pants via bright Pants mask cluster

The SCHP Pants mask mode was orange (`#c18a69`, skin/ground), but the bright 60%
of the mask is white (`#e9e2de`, share 0.48). The bottom is now sampled from
`_bright_pixels(rgb[Pants/Skirt], light=40)`; a trusted seg bottom also bypasses
the white-vs-background fallback and sets `bottom_plausible=True`.

- white pants: orange `#c18a69` → white `#e9e2de`
- A/B: `out/color_audit/pants_ab.png`
- Hair remains dark despite VLM bbox and light-percentile 30→95 (region itself is
  dark); needs a source/region audit.
- Hood geometry not yet re-evaluated.

## Round 9 — dark hair notes are source-limited

The three remaining dark hair notes cannot be recovered from the visible hair
region:

| pair | SCHP hair mask | VLM bbox-only | source crop |
|---|---|---|---|
| up_long_00 | `#3e1a0c` | bbox empty | auburn/red hood; no gold visible |
| up_long_02 | `#191615` | `#36231d` | blonde belongs to a second woman behind; hooded subject's hair is dark |
| up_long_06 | `#1f1c1a` | `#4d5158` | brown/auburn waves, no gold |

Bright hair clusters (light 20–60) do not contain gold either. The two light
hair notes (`#ddc19c`, `#8d6648`) are already fixed by the low-confidence
fallback; the three dark notes need a **manual hair-colour override** or a photo
where the subject's hair is actually visible.

Crops: `out/hair_audit_crops.png`

## Round 10 — manual hair-colour override

The three source-limited hair notes are now user-fixable:

- API: `POST /api/v1/generate-skin` accepts `hair_color=#rrggbb`; invalid values
  return 400 `bad_hair_color`.
- UI: main Settings panel has a “머리색 직접 지정” checkbox + colour input.
- The mask editor still has no colour picker (unchanged).
- E2E on `hood_up_long_hair_02` with `#d4af37` → gold hair.
- A/B: `out/hair_override_ab.png`

The automatic audit remains: 2 light notes are fixed by the fallback; 3 need the
manual override because the source has no gold in the visible subject's hair.
