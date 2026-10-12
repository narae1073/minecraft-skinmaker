# skinmaker

Person photo → Minecraft 64×64 skin (RGBA PNG).

The AI (a VLM) only extracts an attribute JSON from the photo; **every pixel is drawn by
code**. The split exists because of the pixel budget: a 64×64 skin has only 3,264 pixels
available for painting (1,632 per layer), and the front of the face alone is 64 pixels.
87% of the identity lives in hair and clothing, and downscaling a neural image into an
8×12 garment turns it into color blotches — so the AI's share is limited to
**classification** (what garment is it) and **color extraction**. The code renderer owns
100% of the pixels, which is also what makes seams structurally impossible: there is
exactly one renderer.

```
photo ──VLM──→ attribute JSON ──→ code renderer ──→ 64×64 RGBA
             (classify / color)                  + invariant checks
```

- Requirement that anchors all design: *the face and hair only need to be roughly
  similar, not exact.* Faces end as enums; hair silhouette is free to design; only
  color is measured.
- Evaluable area: only 4 of the 14 cuboid faces are observed in a photo. The 75%
  that cannot be observed is where real quality work happens.

## Install / run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python -m pytest -q                  # full suite
.venv/bin/python -m skinmaker --model classic  # dummy skin + preview into out/
```

`out/placeholder_<model>.png` is the skin, `..._preview.png` is the QA 3/5-view sheet
(panel order: front / side / back / top / overlay hair layer).

## Locked design decisions

| Item | Decision |
|---|---|
| AI role | Vision API → attribute JSON only. Zero generated pixels. |
| Face | Rendered by code (eyes 2×2, mouth 4×1) — enum-grade similarity |
| Hands | Rendered by code (bottom 3–4 rows of the arms) |
| Hair | Solid color set (10) × length (4) enums; only color is measured |
| Outerwear | AI returns enum + HEX; code renders it into the 8×12 body box |
| Boundaries | Code owns every pixel → seams structurally impossible |
| Models | `classic` (4px arms) / `slim` (3px arms) |
| Hard gate | Face detection failure only. No other rejection gates. |

## The 64×64 UV layout

`skinmaker/format.py` is the single source of truth. `get_layout()` self-checks the
atlas against the wiki counts and raises if anything drifts.

Layer-0 / layer-1 (overlay) regions per part, atlas-relative (x, y, w, h), and box (w, h, d):

| Part | Layer 0 region | Layer 1 region | Box |
|---|---|---|---|
| head | (0, 0) 32×16 | (32, 0) 32×16 | 8×8×8 |
| body | (16, 16) 24×16 | (16, 32) 24×16 | 8×12×4 |
| r_arm | (40, 16) 16×16 | (40, 32) 16×16 | 4×12×4 |
| r_leg | (0, 16) 16×16 | (0, 32) 16×16 | 4×12×4 |
| l_leg | (16, 48) 16×16 | (0, 48) 16×16 | 4×12×4 |
| l_arm | (32, 48) 16×16 | (48, 48) 16×16 | 4×12×4 |

- Head/body follow the cuboid face order; limbs follow the limb order
  (semantically front → right → back → left → top → bottom — positions in the atlas
  differ between the two groups, which is why this is code, not convention).
- Usable pixels per layer: classic 1,632 / slim 1,568 (verified programmatically).

**Slim: only the front/back faces shrink to 3px; the side (depth) faces stay 4px.**
Because the limb box narrows, the back face's start x moves 1px left. The 4th column
is ignored by the game.

## Left arm / leg mirror rule

`canvas.put(part, face, u, v, color)` takes `u` as **author coordinates, not texture
coordinates**. `l_arm` / `l_leg` have opposite u direction; the canvas flips them on
write. Draw both limbs with the same code and texture-space left/right symmetry holds
automatically. `validate.py` enforces it.

## Invariants (`skinmaker/validate.py`)

Everything that would break the skin in-game is fixed here:

| Code | Condition |
|---|---|
| `size` | exactly 64×64 |
| `mode` | RGBA |
| `overlap` | faces of different parts never overlap |
| `bleed` | pixels belonging to no face are fully transparent |
| `base_alpha` | inner-layer usable pixels are fully opaque (Java forces) |
| `mirror` | left/right parts are exact texture-space mirrors |

Alpha caveats: **Java allows partial transparency (1–255) on the outer
(overlay) layer but enforces full opacity on the inner layer.** Bedrock allows only
0/255.

## Assets / YuNet model (S0)

S0 uses OpenCV's bundled YuNet. The model file is not committed.

```bash
mkdir -p assets
curl -sSLf -o assets/face_detection_yunet_2023mar.onnx \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
```

To use a different path, set `SKINMAKER_YUNET`.

### S0 measurement

```bash
.venv/bin/python -m skinmaker.measure path/to/photos
```

Reports rejection rate, quality-flag distribution, face size/brightness/blur/saturation.
**The only hard gate is face detection failure**; the other flags
(blur / dark / bright / small / flat) are renderer parameters for S1–S3, not rejections.
Multiple detections: `quality.select_face()` picks the subject by area (YuNet scores
cluster around 0.85–0.92 and carry no information), ties broken by image-center distance.

## Optional pose model (upper/full body bands)

S1 bands use joint landmarks (shoulder/pelvis/knee) when a pose model is present and
fall back to face-proportion geometry otherwise. **The model is optional and works
without it.** This machine cannot run mediapipe (SIGILL); pose detection is isolated
off unless you supply a working model:

```bash
curl -sSLf -o assets/pose_landmarker_lite.task \
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task
```

Set `SKINMAKER_POSE` for a non-default path. Upper-body framing (pelvis out of frame)
leaves the bottom band empty → bottom color MISSING → S3 default + S2 `none` rule
infers trousers.

## Stage-by-stage contact sheet

```bash
.venv/bin/python -m skinmaker.samples <photo file|folder> -o out/samples
# one sheet per photo; --no-placeholder to render S3 live, --patterned for patterned tops
```

One git-stage per photo. Panels, top to bottom:

| Panel | Shows | Catches |
|---|---|---|
| **S0 input gate** | original + face box + hair/skin/top sample regions | no face / wrong face / hat grabbed as hair / top band on background |
| **S1 observed colors** | original vs white-balanced + per-region HEX with share & confidence | over-correction / skinlike top / hat-as-hair |
| **S3 atlas 64×64** | skin texture at 8× with an 8-texel grid | which texel is which coordinate |
| **S3 skin over UV guide** | skin composited 55% over a color-coded UV guide | *the key check*: every region landed in its rect |
| **S4 preview** | front / side / back / top / overlay | odd faces, silhouette collapse |

Panel footers carry detection score, quality metrics, region share, and flags.
S1 is actual measurement; S3/S4 panels are filled with a PLACEHOLDER dummy by default
(header says so). Pass `--no-placeholder` to make S3 render live (S1 colors + default
enums, S2 not wired in this view).

Stage 1 observation (`skinmaker/colors.py`) in one breath: skin-referenced white
balance (clipped/unconfident gains are identity — a clipped gain is what turned a
white shirt mint), cluster-mode dominant color, chroma+**luma** background rejection
(dark neutral jeans vs a gray backdrop), bottom-band cascade
(face-proportional bands → frame-lower bands → lower-body foreground mask),
`bottom_plausible` flag feeding the render fallback policy
(`render.bottom_usable`: use measurement when confident or plausible-not-skin-not-background).

## S4 candidates

```bash
.venv/bin/python -m skinmaker.s4 --transport mock --photo <photo> --out out/s4
# --transport gemini|ollama|openrouter for live runs
```

Double-query disagreement only varies fields (`hair_length`, `sleeve_len`); agreeing
queries produce a single candidate — no evidence-free variation, no ranking, all
candidates saved.

## S2 classification

```bash
.venv/bin/python -m skinmaker.s2 --transport mock --photo <photo>
```

Transports: `mock` | `gemini` | `ollama` | `openrouter`. The VLM fills a 5-field schema
(top/bottom garment enum, sleeve length, pattern, bottom length) plus boxes
(`hair_bbox` feeds hair color extraction; first answer wins on dual-query box
disagreement). Crops are framing-aware: always extended to the image bottom for legs,
and full-body frames are sent at up to `FULLBODY_MAX_PX = 1536` vs portrait's 768.

OpenRouter transport (`skinmaker/vlm/openrouter.py`): `OPENROUTER_API_KEY`, optional
`OPENROUTER_DEFAULT_MODELS` (comma list), free-model fallback chain, first model to
return a parseable JSON object wins; nonexistent ids were removed against the live
`/models` endpoint.

## Output quality CLI (`eval`) and the label harness

```bash
.venv/bin/python -m skinmaker.eval out/s0_photos --show 200
.venv/bin/python -m skinmaker.bottom_eval            # mask on/off A/B + fallback policies
```

- `eval`: VLM-free objective metrics — `valid` (invariants), `crown/cheek/torso`
  pixel-consistency (deterministic render → mismatch means a wiring bug), and per-fallback
  yield, broken down by framing bands (`full <0.10 / mid <0.20 / portrait ≥0.20`,
  face-height ratio). `--hair-box "x,y,w,h"` injects a fixed hair box for wiring checks;
  a single global box is deliberately **not** evidence toward the <50% hair-fallback
  target (per-photo boxes require the real VLM).
- `bottom_eval`: compares S1's measured bottom color against human category labels
  (`docs/superpowers/specs/bottom_labels.json`, categories blue / dark / light / mid /
  colored / none / unclear), scores mask on/off, and compares render fallback policies
  (`default_only`, `confident_only`, `trust_measured`, `gate`). Nothing here calls the network.

## Parsing layer (optional: `SKINMAKER_PARSING`)

Bottom-garment localization via a SCHP human-parsing mask is an **optional layer**. It is off by default — without the flag the existing band/cascade path is used unchanged.

```bash
pip install -r requirements-parsing.txt        # onnxruntime (no torch needed)
mkdir -p out/models
curl -sSLf -o out/models/schp-atr-18-int8-static.onnx \
  "https://huggingface.co/pirocheto/schp-atr-18/resolve/main/onnx/schp-atr-18-int8-static.onnx?download=true"
export SKINMAKER_PARSING=1                     # on: the dominant colour of Pants/Skirt mask pixels becomes the bottom colour
export SKINMAKER_PARSER=out/models/schp-atr-18-int8-static.onnx   # default path (overridable)
```

- Measured (`docs/superpowers/specs/2026-10-11-heldout-protocol.md`, L0/L1): 2.2 s/photo on this 4-core box, ~110 MB RSS; fitting-set A/B on 59 photos took bottom agreement **0.644 → 0.746 (+6)** — the mask resolved every diagnosed localization failure.
- If the dependency or the model file is missing, the layer quietly falls back to the band path. top/hair sampling is unchanged; `bottom_plausible` and the render fallback policy apply as before.

## Web (Vite + FastAPI)

```bash
set -a; source .env; set +a      # GEMINI_API_KEY
.venv/bin/python -m uvicorn backend.app:app --port 8001
cd frontend && npm install && npm run dev   # http://localhost:5173/
```

Contract: `POST /api/v1/generate-skin` (multipart `file`)
→ `{"status":"success","data":{"skins":[url,...]}}`.
Generated e2e skins are archived under `backend/static/skins/`.
If 8000 is taken, also update `frontend/vite.config.js`.

## Status

- [x] Stage 1: UV constants, canvas, invariant validation, multi-view preview, dummy skin
- [x] S0: input gate (YuNet detection, quality signals, degradation plan, measurement CLI, multi-face selection)
- [x] Stage-by-stage visual sample sheet (contact sheet)
- [x] S1: observation (skin-referenced WB, cluster mode, confidence/skinlike flags, bottom cascade + foreground mask + loss test harness)
- [x] S2: VLM classification (5-field schema, 4 transports incl. OpenRouter fallback chain, dual-query uncertainty)
- [x] S3: parametric render (incl. the bottom fallback policy)
- [x] S4: N candidates + validation (variation only on dual-query disagreement; no ranking)
- [x] Web: FastAPI `generate-skin`, Vite capture, static skin archive

## Notes

- **Java Edition skins must be signed** → they must be uploaded via minecraft.net to
  show in the real game; without a legit account, verification stays local
  (`validate.py` + previews). For quick visual checks, copy the PNG into
  **Bedrock** instead (file copy is enough).
- Photos of other people require portrait consent. This project is a **local-only** tool
  by design; don't turn it into a web service for third-party photos.
