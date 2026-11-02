"""General attribute-mask editor: paint shape stencils for attribute values.

Shape-only (no colour picker). Parts: head, body, both arms, both legs.
Each mask is ``{attribute.value: {L1/L2: {part.face: grid}}}``; the production
renderer reads the same asset; colours/patterns stay in the pipeline.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))
from skinmaker import attribute_masks as AM  # noqa: E402
from skinmaker import attributes as A  # noqa: E402
from skinmaker import production_qa as Q, render as R  # noqa: E402
from skinmaker.canvas import SkinCanvas  # noqa: E402
from skinmaker.format import get_layout  # noqa: E402

OUT = REPO / "out" / "mask_editor"
OUT.mkdir(parents=True, exist_ok=True)
LAYOUT = get_layout("classic")
PARTS = ("head", "body", "r_arm", "l_arm", "r_leg", "l_leg")
PART_FACES = {part: tuple(LAYOUT.part(part, 0).faces) for part in PARTS}
FACES = [f"{part}.{face}" for part in PARTS for face in PART_FACES[part]]
DIMS = {f"{part}.{face}": (f.w, f.h) for part in PARTS for face, f in LAYOUT.part(part, 0).faces.items()}
LAYERS = ["L1", "L2"]
MASKABLE = {
    "hood": ("up", "down"),
    "headwear": ("beanie", "cap"),
    "hood_fit": ("shallow",),
    "hair_style": ("short", "pixie", "bob", "long_straight", "long_wavy", "curly", "ponytail", "bun"),
    "hair_length": ("short", "medium", "long", "very_long"),
    "beard": ("stubble", "full"),
    "sleeve_len": ("none", "short", "three_quarter", "long"),
    "bottom_garment": ("jeans", "shorts", "skirt", "pants", "none"),
    "closure_type": ("none", "zipper", "buttons", "open"),
    "collar_type": ("none", "crew", "v_neck", "shirt", "hood"),
    "pocket_type": ("none", "patch"),
    "neckwear": ("none", "tie"),
    "inner_top": ("none", "shirt", "tee", "knit"),
    "top_garment": ("tee", "hoodie", "jacket", "shirt", "sweater", "vest", "uniform", "apron", "overalls", "dress", "none"),
}
app = FastAPI(title="skinmaker attribute mask editor")


@app.middleware("http")
async def no_store_static(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/static", StaticFiles(directory=ROOT), name="static")
app.mount("/out", StaticFiles(directory=OUT), name="out")


def _blank(face: str) -> list[list[int]]:
    w, h = DIMS.get(face, (8, 8))
    return [[0] * w for _ in range(h)]


def _normalize_key(src) -> dict:
    out = {"L1": {}, "L2": {}}
    if not isinstance(src, dict):
        return out
    for layer in LAYERS:
        face_map = src.get(layer) or {}
        if not isinstance(face_map, dict):
            continue
        for face in FACES:
            w, h = DIMS[face]
            grid = face_map.get(face)
            if isinstance(grid, list):
                out[layer][face] = [
                    [int(bool(grid[v][u])) if v < len(grid) and u < len(grid[v]) else 0 for u in range(w)]
                    for v in range(h)
                ]
            else:
                out[layer][face] = _blank(face)
    return out


def _seed_hair(key: str, value: str) -> dict:
    if key not in ("hair_style", "hair_length"):
        return {}
    length = value if key == "hair_length" else "long"
    style = value if key == "hair_style" else "long_straight"
    attrs = Q._attrs(length, style, "none")
    canvas = SkinCanvas("classic")
    cells = R.render_head(canvas, R.resolve_colors(Q._observed()), attrs, None,
                          style=style, pack=None, seed="", masks=None, return_cells=True)
    grids = {}
    for face in ("top", "front", "right", "left", "back", "bottom"):
        f = LAYOUT.face("head", face, 0)
        grids[f"head.{face}"] = [[1 if (face, u, v) in cells else 0 for u in range(f.w)] for v in range(f.h)]
    return {"L1": grids, "L2": {}}


def _seed_sleeve(key: str, value: str) -> dict:
    if key != "sleeve_len" or value == "none":
        return {}
    end = R.SLEEVE_ROWS.get(value, 3)
    grids = {}
    for part in ("r_arm", "l_arm"):
        for face in PART_FACES[part]:
            f = LAYOUT.face(part, face, 0)
            if f.h < 12:
                grids[f"{part}.{face}"] = [[1] * f.w for _ in range(f.h)]
            else:
                grids[f"{part}.{face}"] = [[1 if v <= end else 0 for _ in range(f.w)] for v in range(f.h)]
    return {"L1": grids, "L2": {}}


def _seed_bottom(value: str) -> dict:
    if value == "none":
        return {}
    base = dict(Q._attrs("long", "long_straight", "none").values)
    base["bottom_garment"] = "none"
    baseline = R.render(Q._observed(), A.validate(base), (), mask_override={})
    base["bottom_garment"] = value
    target = R.render(Q._observed(), A.validate(base), (), mask_override={})
    grids = {}
    for part in ("r_leg", "l_leg"):
        for face in PART_FACES[part]:
            f = LAYOUT.face(part, face, 0)
            rows = min(9, f.h)
            grids[f"{part}.{face}"] = [
                [1 if target.get(part, face, u, v, 0)[:3] != baseline.get(part, face, u, v, 0)[:3] else 0
                 for u in range(f.w)] for v in range(rows)
            ]
    return {"L1": grids, "L2": {}}


def _seed_structure(key: str, value: str) -> dict:
    if value == "none":
        return {}
    if key == "neckwear":
        # The tie colour can equal the inner colour in synthetic QA colours;
        # seed the known tie cells instead of a colour diff.
        return {"L1": {"body.front": [[1 if (u == 4 and v in (1, 2)) else 0 for u in range(8)] for v in range(12)]}}
    base = dict(Q._attrs("long", "long_straight", "none").values)
    base["top_garment"] = "hoodie"
    base["inner_top"] = "none"
    base[key] = "none"
    baseline = R.render(Q._observed(), A.validate(base), (), mask_override={})
    base[key] = value
    target = R.render(Q._observed(), A.validate(base), (), mask_override={})
    f = LAYOUT.face("body", "front", 0)
    grid = [[1 if target.get("body", "front", u, v, 0)[:3] != baseline.get("body", "front", u, v, 0)[:3] else 0
             for u in range(f.w)] for v in range(f.h)]
    return {"L1": {"body.front": grid}, "L2": {}}


def _seed_inner(value: str) -> dict:
    if value == "none":
        return {}
    base = dict(Q._attrs("long", "long_straight", "none").values)
    base["top_garment"] = "hoodie"
    base["inner_top"] = "none"
    baseline = R.render(Q._observed(), A.validate(base), (), mask_override={})
    base["inner_top"] = value
    target = R.render(Q._observed(), A.validate(base), (), mask_override={})
    grids = {}
    f = LAYOUT.face("body", "front", 0)
    grids["body.front"] = [[1 if target.get("body", "front", u, v, 0)[:3] != baseline.get("body", "front", u, v, 0)[:3] else 0
                            for u in range(f.w)] for v in range(f.h)]
    for part in ("r_arm", "l_arm"):
        for face in PART_FACES[part]:
            f = LAYOUT.face(part, face, 0)
            grid = [[1 if target.get(part, face, u, v, 0)[:3] != baseline.get(part, face, u, v, 0)[:3] else 0
                     for u in range(f.w)] for v in range(f.h)]
            if any(any(r) for r in grid):
                grids[f"{part}.{face}"] = grid
    return {"L1": grids, "L2": {}}


def _seed_top(value: str) -> dict:
    if value == "none":
        return {}
    base = dict(Q._attrs("long", "long_straight", "none").values)
    base["top_garment"] = "none"
    baseline = R.render(Q._observed(), A.validate(base), (), mask_override={})
    base["top_garment"] = value
    target = R.render(Q._observed(), A.validate(base), (), mask_override={})
    grids = {}
    for part in ("body", "r_arm", "l_arm", "r_leg", "l_leg"):
        for face in PART_FACES[part]:
            f = LAYOUT.face(part, face, 0)
            grid = [[1 if target.get(part, face, u, v, 0)[:3] != baseline.get(part, face, u, v, 0)[:3] else 0
                     for u in range(f.w)] for v in range(f.h)]
            if any(any(r) for r in grid):
                grids[f"{part}.{face}"] = grid
    return {"L1": grids, "L2": {}}


def _defaults() -> dict:
    approved = AM.load_masks()
    saved = {}
    try:
        saved = json.loads((OUT / "attribute_masks.json").read_text(encoding="utf-8"))
        saved = saved.get("masks", saved)
    except (OSError, ValueError):
        saved = {}
    masks = {}
    for key, values in MASKABLE.items():
        for value in values:
            name = f"{key}.{value}"
            src = (saved.get(name) if isinstance(saved, dict) else None) or approved.get(name)
            if src is None:
                if key in ("hair_style", "hair_length"):
                    src = _seed_hair(key, value)
                elif key == "sleeve_len":
                    src = _seed_sleeve(key, value)
                elif key == "bottom_garment":
                    src = _seed_bottom(value)
                elif key in ("closure_type", "collar_type", "pocket_type", "neckwear"):
                    src = _seed_structure(key, value)
                elif key == "inner_top":
                    src = _seed_inner(value)
                elif key == "top_garment":
                    src = _seed_top(value)
                else:
                    src = {}
            masks[name] = _normalize_key(src)
    return masks


@app.get("/")
def index():
    return FileResponse(ROOT / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/defaults")
def defaults():
    return JSONResponse(
        {"parts": PARTS, "part_faces": PART_FACES, "faces": FACES, "dims": DIMS,
         "layers": LAYERS, "maskable": MASKABLE, "masks": _defaults()},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/save")
async def save(req: Request):
    body = await req.json()
    payload = {"version": 1, "source": "mask_editor", "policy": AM.POLICY,
               "masks": body.get("masks", {})}
    (OUT / "attribute_masks.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True, "path": str(OUT / "attribute_masks.json")}


def _attrs_for(key: str, value: str) -> A.Attributes:
    hood = "none" if key in ("hair_style", "hair_length", "beard", "sleeve_len", "bottom_garment",
                             "closure_type", "collar_type", "pocket_type", "neckwear", "inner_top", "top_garment") else "up"
    if key == "hood":
        hood = value
    base = dict(Q._attrs("long", "long_straight", hood).values)
    base.setdefault("headwear", "none")
    base.setdefault("hood_fit", "normal")
    if key == "neckwear":
        base["inner_top"] = "shirt"
    base[key] = value
    return A.validate(base)


@app.post("/api/preview")
async def preview(req: Request):
    body = await req.json()
    key = str(body.get("key", "hood"))
    value = str(body.get("value", "up"))
    masks = body.get("masks", {})
    if key not in MASKABLE or value not in MASKABLE[key]:
        return JSONResponse({"error": "bad key/value"}, status_code=400)
    mode = body.get("mode", "final")
    if mode not in ("final", "mask"):
        mode = "final"
    attrs = _attrs_for(key, value)
    observed = Q._observed()
    if mode == "mask":
        canvas = R.render(observed, attrs, (), mask_override={})
        for layer, layer_index in (("L1", 0), ("L2", 1)):
            for face in FACES:
                part, short = face.split(".", 1)
                grid = AM.get_mask(masks, key, value, layer, part, short)
                if not grid:
                    continue
                color = (0, 150, 190, 255) if layer == "L1" else (0, 220, 240, 255)
                for v, row in enumerate(grid[:DIMS[face][1]]):
                    for u, bit in enumerate(row[:DIMS[face][0]]):
                        if bit:
                            canvas.put(part, short, u, v, color, layer_index)
    else:
        canvas = R.render(observed, attrs, (), mask_override=masks)
    canvas.image.save(OUT / "preview.png")
    return JSONResponse({"skin": "/out/preview.png", "key": key, "value": value, "mode": mode},
                        headers={"Cache-Control": "no-store"})
