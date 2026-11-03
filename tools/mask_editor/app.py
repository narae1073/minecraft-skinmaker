"""General attribute-mask editor: paint shape stencils for attribute values.

Shape-only (no colour picker). Parts: head, body, both arms, both legs.
Each mask is ``{attribute.value: {L1/L2: {part.face: grid}}}``; the production
renderer reads the same asset; colours/patterns stay in the pipeline.
"""
from __future__ import annotations

import dataclasses
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
COMBO_KEYS = A.FIELD_ORDER
COMBO_ENUMS = {name: A.ENUMS[name] for name in COMBO_KEYS}
_COMBO_BASE = Q._attrs("long", "long_straight", "up")
DEFAULT_COMBO = {name: _COMBO_BASE.get(name) for name in COMBO_KEYS}
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
# Saved-draft schema. 2 = drafts written by this editor after the one-off
# body migrations were retired from the load path; user body edits persist.
SCHEMA = 2
LENGTH_STYLE = {
    "short": "short",
    "medium": "bob",
    "long": "long_straight",
    "very_long": "long_straight",
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
    # hair_style masks are seeded at the longest length so a later
    # hair_length=very_long mask is not clipped by a long-baseline style mask.
    length = value if key == "hair_length" else "very_long"
    style = value if key == "hair_style" else LENGTH_STYLE.get(value, "long_straight")
    attrs = Q._attrs(length, style, "none")
    canvas = SkinCanvas("classic")
    cells = R.render_head(canvas, R.resolve_colors(Q._observed()), attrs, None,
                          style=style, pack=None, seed="", masks=None, return_cells=True)
    l1 = {}
    for face in ("top", "front", "right", "left", "back", "bottom"):
        f = LAYOUT.face("head", face, 0)
        l1[f"head.{face}"] = [[1 if (face, u, v) in cells else 0 for u in range(f.w)] for v in range(f.h)]
    # Body hair drape (medium/long/very_long): seed L1 and L2 from the
    # procedural target vs a short-hair baseline. This is the body hair the
    # editor/mask view previously missed.
    target = R.render(Q._observed(), attrs, (), mask_override={})
    base = dict(attrs.values)
    base["hair_style"] = "short"
    base["hair_length"] = "short"
    baseline = R.render(Q._observed(), A.validate(base), (), mask_override={})
    l2 = {}
    # Head L2 hair: the procedural hair overlay. Seed from the overlay-on
    # target vs an overlay-off baseline so the head L2 hair is selectable too.
    no_overlay = dataclasses.replace(Q._observed(), hair_overlay=False)
    l2_base = R.render(no_overlay, attrs, (), mask_override={})
    for face in ("top", "front", "right", "left", "back", "bottom"):
        f = LAYOUT.face("head", face, 0)
        grid = [[1 if target.get("head", face, u, v, 1)[:3] != l2_base.get("head", face, u, v, 1)[:3] else 0
                 for u in range(f.w)] for v in range(f.h)]
        if any(any(r) for r in grid):
            l2[f"head.{face}"] = grid
    for face in ("front", "back", "right", "left"):
        f = LAYOUT.face("body", face, 0)
        grid1 = [[1 if target.get("body", face, u, v, 0)[:3] != baseline.get("body", face, u, v, 0)[:3] else 0
                  for u in range(f.w)] for v in range(f.h)]
        grid2 = [[1 if target.get("body", face, u, v, 1)[:3] != baseline.get("body", face, u, v, 1)[:3] else 0
                  for u in range(f.w)] for v in range(f.h)]
        if any(any(r) for r in grid1):
            l1[f"body.{face}"] = grid1
        if any(any(r) for r in grid2):
            l2[f"body.{face}"] = grid2
    return {"L1": l1, "L2": l2}


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


def _seed_for(key: str, value: str) -> dict:
    if key in ("hair_style", "hair_length"):
        return _seed_hair(key, value)
    if key == "sleeve_len":
        return _seed_sleeve(key, value)
    if key == "bottom_garment":
        return _seed_bottom(value)
    if key in ("closure_type", "collar_type", "pocket_type", "neckwear"):
        return _seed_structure(key, value)
    if key == "inner_top":
        return _seed_inner(value)
    if key == "top_garment":
        return _seed_top(value)
    return {}


def _load_saved() -> tuple[dict, int]:
    """Return ``(masks, schema)`` for the saved draft; schema 1 when unmarked."""
    try:
        doc = json.loads((OUT / "attribute_masks.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, SCHEMA
    if not isinstance(doc, dict):
        return {}, SCHEMA
    if "masks" not in doc:
        return doc, 1
    try:
        schema = int(doc.get("schema", 1))
    except (TypeError, ValueError):
        schema = 1
    masks = doc["masks"] if isinstance(doc["masks"], dict) else {}
    return masks, schema


def _defaults() -> dict:
    approved = AM.load_masks()
    saved, schema = _load_saved()
    masks = {}
    for key, values in MASKABLE.items():
        for value in values:
            name = f"{key}.{value}"
            from_draft = isinstance(saved.get(name), dict)
            src = saved.get(name) or approved.get(name)
            # One-off body migrations only touch legacy drafts (schema < 2) and
            # approved assets; a current draft keeps the user's body edits.
            migrate = not from_draft or schema < SCHEMA
            if src is None:
                src = _seed_for(key, value)
            elif migrate and key == "hair_length" and isinstance(src, dict):
                # Migration: old drafts seeded hair_length bodies from
                # long_straight, so short/medium carried a long body drape.
                # Preserve the user's head edits; replace body faces with the
                # new length-matched seed.
                seed = _seed_hair(key, value)
                src = {layer: dict(src.get(layer, {}) or {}) for layer in LAYERS}
                for layer in LAYERS:
                    for face in FACES:
                        if face.startswith("body."):
                            src[layer][face] = seed[layer].get(face) or _blank(face)
            if migrate and key == "top_garment" and value != "none" and isinstance(src, dict):
                # A saved top mask can have a partial body (e.g. back=2 cells),
                # which render_body treats as "not top" -> skin. Refill body
                # faces from the current seed; keep the user's arm/leg edits.
                src = {layer: dict(src.get(layer, {}) or {}) for layer in LAYERS}
                for layer in LAYERS:
                    for face in FACES:
                        if face.startswith("body."):
                            w, h = DIMS[face]
                            src[layer][face] = [[1] * w for _ in range(h)]
            if key in ("hair_style", "hair_length") and isinstance(src, dict):
                # Hood up/down hides body-back hair. Zero the body.back cells in
                # every hair mask so a saved mask cannot paint through the hood.
                src = {layer: dict(src.get(layer, {}) or {}) for layer in LAYERS}
                for layer in LAYERS:
                    for face in FACES:
                        if face.startswith("body.back"):
                            src[layer][face] = _blank(face)
            masks[name] = _normalize_key(src)
    return masks


@app.get("/")
def index():
    return FileResponse(ROOT / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/defaults")
def defaults():
    return JSONResponse(
        {"parts": PARTS, "part_faces": PART_FACES, "faces": FACES, "dims": DIMS,
         "layers": LAYERS, "enums": COMBO_ENUMS, "defaults": DEFAULT_COMBO,
         "models": ["classic", "slim"], "combo": DEFAULT_COMBO,
         "maskable": MASKABLE, "masks": _defaults()},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/seed")
def seed(key: str, value: str):
    if key not in MASKABLE or value not in MASKABLE[key]:
        return JSONResponse({"error": "bad key/value"}, status_code=400)
    return JSONResponse({"key": key, "value": value, "mask": _normalize_key(_seed_for(key, value))},
                        headers={"Cache-Control": "no-store"})


@app.post("/api/save")
async def save(req: Request):
    body = await req.json()
    payload = {"version": 1, "schema": SCHEMA, "source": "mask_editor", "policy": AM.POLICY,
               "masks": body.get("masks", {})}
    (OUT / "attribute_masks.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True, "path": str(OUT / "attribute_masks.json")}


def _combo_attrs(combo: dict) -> A.Attributes:
    raw = dict(DEFAULT_COMBO)
    raw.update({name: value for name, value in combo.items() if name in COMBO_KEYS})
    raw["hair_bbox"] = _COMBO_BASE.hair_bbox
    return A.validate(raw)


def _combo_warnings(requested: dict, attrs: A.Attributes) -> list[str]:
    out: list[str] = []
    for item in attrs.derived:
        out.append(f"cross: {item}")
    for name in attrs.coerced:
        out.append(f"invalid {name}: {requested.get(name)} -> {attrs.get(name)}")
    for name in attrs.missing:
        out.append(f"missing {name}: default {attrs.get(name)}")
    for name in COMBO_KEYS:
        if name in requested and requested[name] != attrs.get(name):
            msg = f"{name}: {requested[name]} -> {attrs.get(name)}"
            if msg not in out:
                out.append(msg)
    return out


def _attrs_for(key: str, value: str) -> A.Attributes:
    hood = "none" if key in ("hair_style", "hair_length", "beard", "sleeve_len", "bottom_garment",
                             "closure_type", "collar_type", "pocket_type", "neckwear", "inner_top", "top_garment") else "up"
    if key == "hood":
        hood = value
    if key == "hair_length":
        base = dict(Q._attrs(value, LENGTH_STYLE.get(value, "long_straight"), hood).values)
    elif key == "hair_style":
        base = dict(Q._attrs("very_long", value, hood).values)
    else:
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
    mode = body.get("mode", "final")
    if mode not in ("final", "mask"):
        mode = "final"
    model = str(body.get("model", "classic"))
    if model not in ("classic", "slim"):
        return JSONResponse({"error": "bad model"}, status_code=400)
    combo = body.get("combo")
    warnings: list[str] = []
    if combo is not None:
        if not isinstance(combo, dict):
            return JSONResponse({"error": "bad combo"}, status_code=400)
        for name, val in combo.items():
            if name not in COMBO_ENUMS or val not in COMBO_ENUMS[name]:
                return JSONResponse({"error": f"bad combo {name}={val}"}, status_code=400)
        attrs = _combo_attrs(combo)
        warnings = _combo_warnings(combo, attrs)
    else:
        # Back-compat for the single key/value preview used by older tests.
        if key not in MASKABLE or value not in MASKABLE[key]:
            return JSONResponse({"error": "bad key/value"}, status_code=400)
        attrs = _attrs_for(key, value)
    if mode == "mask" and (key not in MASKABLE or value not in MASKABLE[key]):
        return JSONResponse({"error": "bad key/value"}, status_code=400)
    observed = Q._observed()
    if mode == "mask":
        canvas = R.render(observed, attrs, (), mask_override={}, model=model)
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
        canvas = R.render(observed, attrs, (), mask_override=masks, model=model)
    canvas.image.save(OUT / "preview.png")
    return JSONResponse({"skin": "/out/preview.png", "key": key, "value": value,
                         "mode": mode, "model": model, "effective": attrs.values,
                         "warnings": warnings, "coerced": list(attrs.coerced),
                         "derived": list(attrs.derived)},
                        headers={"Cache-Control": "no-store"})
