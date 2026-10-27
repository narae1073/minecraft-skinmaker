# QA render — `skinmaker.qarender`

Reusable visual-QA tool for skin texture/geometry changes. It renders the
**same three.js model the web viewer uses** (shared `frontend/src/skinModel.js`)
through headless Chrome, from two fixed turntable angles, and writes PNGs plus
camera metadata.

Use it whenever a change affects the 64×64 atlas, the L1/L2 layer split, hair
silhouettes, or the 3D viewer. It is also the intended input for the visual-QA
sub-agent loop (render → inspect → fix → re-render).

## Requirements

- Chrome or Chromium (auto-detected; override with `SKINMAKER_CHROME=/path/to/chrome`)
- `frontend/node_modules` installed (`cd frontend && npm ci`) — the harness
  imports `three` from there and the model from `frontend/src/skinModel.js`
- Headless software WebGL works with the flags the tool passes
  (`--enable-unsafe-swiftshader`, ANGLE/SwiftShader)

## Usage

```bash
.venv/bin/python -m skinmaker.qarender out/qa_l2/skin_after.png
.venv/bin/python -m skinmaker.qarender skin.png --out out/qa_render \
    --model classic --yaw 24 --pitch 30 --width 512 --height 768
```

From Python:

```python
from skinmaker.qarender import render_views
result = render_views("out/qa_l2/skin_after.png", "out/qa_l2/after")
# result["views"][0]["path"] == "front_right.png"
```

The skin must be a 64×64 RGBA PNG (the app's output format).

## Camera contract

Both views are rendered with identical projection parameters, so the pair is
directly comparable ("parallel-consistent"):

| view | yaw | pitch | projection |
|---|---|---|---|
| `front_right` | +24° | +30° (looking down) | perspective, fov 12°, distance 24 |
| `back_right` | +204° (180° + 24°) | +30° | same |

- **Near-orthographic:** a 12° vertical FOV at distance 24 gives very weak
  perspective (less than ~2% size change across the model), matching the
  requested "near-orthographic look".
- The camera orbits the origin at the model's vertical center; `up` is +Y for
  both shots, so the horizon stays level and the front/back pair has no roll.
- Both views share fov, distance, target, and lighting, so depth/alignment
  differences are real model differences, not camera differences.

## Outputs

| file | contents |
|---|---|
| `front_right.png` | +24° yaw, +30° pitch |
| `back_right.png` | +204° yaw, +30° pitch |
| `contact_sheet.png` | both views side by side with angle labels |
| `render.json` | skin sha256, texture L1/L2 opaque-pixel counts, camera parameters, canvas size |

`render.json`'s `skin.texture` counts are a quick sparsity check for overlay
work: `l2_opaque` much smaller than `l1_opaque` means the overlay is not a
full silhouette copy.

## Options

| option | default | meaning |
|---|---|---|
| `--out` | `out/qa_render` | output directory |
| `--model` | `classic` | `classic` (4px arms) or `slim` (3px arms) |
| `--yaw` | `24` | front-shot yaw; back shot is `yaw + 180` |
| `--pitch` | `30` | downward tilt for both shots |
| `--fov` | `12` | vertical FOV; smaller = flatter projection |
| `--distance` | `24` | camera distance from the origin |
| `--width` / `--height` | `512` / `768` | screenshot size |
| `--browser` | auto | Chrome/Chromium binary |
| `--timeout` | `90` | per-view Chrome timeout (seconds) |

## I/O and provenance

The tool serves the repository root plus the single skin file
(`/__skin__.png`) from a loopback HTTP server, then invokes Chrome twice with
`--virtual-time-budget`. The page imports the real model and hides nothing, so
the screenshot is the app's renderer with a fixed camera (no auto-rotation).

The generated images are for local QA only; `out/` is gitignored. Commit
`render.json` excerpts or the sub-agent's verdict into PR descriptions when a
change is visual.

## Tests

`tests/test_qarender.py` covers the camera contract and an optional end-to-end
smoke render. The browser smoke test is skipped when Chrome is absent and on CI
(`CI=true`) because software WebGL on hosted runners is flaky; run it locally
before shipping visual changes.
