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

Checks: rear-bottom coverage, chin hair, L2 alpha holes inside the head hair
silhouette, side-profile jumps, body-drape rows. Exit status is non-zero when a
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
C. Length: for long-haired portraits, does the L2 back/drape reach the expected
   body rows, and do the bangs reach the brow without covering the eyes?
D. Continuity: is the side hairline continuous from front to back, with no
   staircase jumps, zero-width columns, or L1/L2 mismatched silhouettes?
E. Style: does the L2 silhouette match the portrait style
   (bob / long straight / wavy / curly / ponytail / bun / pixie)?
Return JSON only: {"bottom":"PASS|FAIL","l2":"PASS|FAIL","length":"PASS|FAIL",
"continuity":"PASS|FAIL","style":"PASS|FAIL","evidence":["..."]}.
Do not propose code fixes; report visual defects only.
```

Style (E) is checked against the `hair_style` tag; uncertain tags fall back to bob / long-straight / long-wavy by length.
