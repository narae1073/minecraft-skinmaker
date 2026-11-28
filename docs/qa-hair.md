# Hair QA — L1/L2 visual + deterministic checks

Hair changes need a **bottom** and **side** view; the default front/back pair cannot
see the head underside, the L2 holes, or the side hairline.

## Render

```bash
.venv/bin/python -m skinmaker.qarender out/skin.png --out out/qa_hair \
    --views hair --width 512 --height 768
```

`--views hair` adds:

| view | yaw | pitch |
|---|---|---|
| `front_right` | +24° | +30° |
| `back_right` | +204° | +30° |
| `bottom` | +204° | **−60°** |
| `right_side` | +90° | 0° |

The head bottom orientation is **v0 = front (chin), v7 = back** (verified with a
row-marker skin).

## Deterministic report

```bash
.venv/bin/python -m skinmaker.hairreport skin.png \
    --hair "#3a2a1c" --skin "#e0ac69" --length long
.venv/bin/python -m skinmaker.hairreport --batch out/qa_final --out out/hair_report.json
```

Checks: rear-bottom coverage, chin hair, L2 defect holes inside the head hair
silhouette, intentional strand notches, side-profile jumps, body-drape rows. Exit status is non-zero when a
check fails.

Known limits: a dark-skinned subject can be misread as bald; a genuinely bald
skin rendered with hair is a product defect, not a report error.

## Sub-agent prompt

```text
You are reviewing Minecraft 64x64 skins for hair correctness.
Images per skin: front-right, back-right, bottom (camera below), right-side.

For each skin return PASS/FAIL plus one-line evidence for:
A. Bottom coverage: from below, is the rear hair footprint fully hair-coloured,
   with no skin patches behind the hairline? (Chin/neck skin is allowed.)
B. L2 solidity: are there any transparent/1px gaps in the L2 back, sides or body?
   The L2 hair must read as a continuous layer, not separated teeth.
C. Length: for long-haired portraits, does the front chest hair reach the
   expected 5 rows (C-tapered edge lock), and does the back stop at mid-back (<=6 rows) rather than
   cover the whole torso? Do the bangs reach the brow without covering the eyes?
D. Continuity: is the side hairline continuous from front to back, with no
   staircase jumps, zero-width columns, or L1/L2 mismatched silhouettes?
F. Bang policy: loose styles (bob/long_straight/long_wavy/curly) cover the eyebrow
   row (4) but keep eyes rows 5-6 visible. Short/pixie keep the eyebrow row open when the SCHP front hairline has no
   visible bangs; visible short bangs get the 5-row fringe. Pulled-back
   ponytail/bun keep it open. L2 may cover at most the top of the
   eyes (row5) in a deliberate, limited style accent; row6 must stay visible.
   L2 bang-tip notches must reveal L1 hair, never skin.
G. Pixel hygiene (mandatory): inspect at 1:1 and 8x. Reject ANY isolated/stray
   pixel, 1px gap, alternating checker, 4x4/grid pattern, or floating trim. Check
   the 2D UV of the top/front faces directly; do NOT infer cleanliness from a
   contiguous-looking band. Render with noise 0 AND production noise (50%),
   because noise is applied after most texture passes.
E. Style: does the L2 silhouette match the portrait style
   (bob / long straight / wavy / curly / ponytail / bun / pixie)?
Return JSON only: {"bottom":"PASS|FAIL","l2":"PASS|FAIL","length":"PASS|FAIL",
"continuity":"PASS|FAIL","bangs":"PASS|FAIL","pixels":"PASS|FAIL",
"style":"PASS|FAIL","evidence":["..."]}.
Do not propose code fixes; report visual defects only.
```

Style (E) is checked against the `hair_style` tag; uncertain tags fall back to bob / long-straight / long-wavy by length.


## Hood / reference-pack checks (2026-10-31)

- **Eyes:** both eyes present and symmetric; sclera/iris not inverted or hidden by hair; iris colour matches the photo.
- **Hair L2:** irregular strand/column tones, no regular even/odd stripes and no large square patches.
- **Hood up:** hood covers crown/sides/back, face opening keeps both eyes and the face visible; no hair holes through the hood.
- **Hood down:** cowl sits at the neck/shoulders; no hood shell over the head.
- **Hood none:** no hood overlay at all.

## Body drape is capped by hair length (2026-11-28)

**Symptom.** `long_straight`, `long_wavy` and `curly` looked waist-length at
`medium` and `long` — identical to `very_long`.

**Cause.** `hairstencil.STYLE_DRAPE` held one reference cape `(11 front, 12 back)`
for all three loose styles, and `render` used it for every length. The reference
drape in `reference_pack.hair_body.l1_depth` is likewise one very-long
silhouette, so masks could only cut it, never reshorten it.

**Fix.** The cape is capped by the declared length:

- `hairstencil.style_drape(style, hair_length)` → `min(style rows, LENGTH_BODY_ROWS[length])`
  (`short 0 / medium 2 / long 6 / very_long 10`); omitting the length keeps the
  legacy reference rows for callers/tests that need the raw silhouette.
- `hairstencil.cap_drape(drape, front, back)` trims the per-column reference
  cascade to those rows; faces left empty are dropped.
- `render` passes `attrs["hair_length"]` and caps the drape before rendering.
- `hairreport` compares against the same capped expectation.

**A/B (synthetic observed, `noise_seed=None`, hair `#112233`)** — body rows actually
painted, before → after:

| style | length | front | back |
|---|---|---|---|
| long_straight / long_wavy / curly | short | 11 → **0** | 12 → **0** |
| " | medium | 11 → **2** | 12 → **2** |
| " | long | 11 → **6** | 12 → **6** |
| " | very_long | 11 → **10** | 12 → **10** |

- Unchanged: `short`, `bob`, `ponytail`, `bun` (no drape), head hair, bangs, L2.
- Golden pixel baselines updated for `long` (`aad4f2e43b6ed7a0 → 3ae4f6c3a81c3e18`)
  and `very_long` (`54bd7befaed3252e → 279f327fa7961687`); `short` and `medium`
  hashes are byte-identical because their fallback styles have no drape.
- `docs/handover.md` records the same numbers.
