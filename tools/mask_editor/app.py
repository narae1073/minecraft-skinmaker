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

from fastapi import File, FastAPI, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))
from skinmaker import attribute_masks as AM  # noqa: E402
from skinmaker import attributes as A  # noqa: E402
from skinmaker import colors as C, parsing as P, quality as QU  # noqa: E402
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
SCHEMA = 3
LENGTH_STYLE = {
    "short": "short",
    "medium": "bob",
    "long": "long_straight",
    "very_long": "long_straight",
}
app = FastAPI(title="skinmaker attribute mask editor")

# One uploaded photo drives the seeds and the preview. Without one, the
# fixture observation is used. Single-user local tool: process-wide state.
_PHOTO: dict = {"observed": None, "name": None, "info": None}
MAX_PHOTO_BYTES = 15 * 1024 * 1024


def _observed():
    return _PHOTO["observed"] or Q._observed()


def _photo_info(name: str, observed) -> dict:
    return {"name": name, "skin": observed.skin.hex, "hair": observed.hair.hex,
            "top": observed.top.hex, "bottom": observed.bottom.hex,
            "hair_stencil": observed.hair_stencil is not None}


@app.get("/api/photo")
def photo_info():
    return JSONResponse(_PHOTO["info"], headers={"Cache-Control": "no-store"})


@app.delete("/api/photo")
def photo_clear():
    _PHOTO.update(observed=None, name=None, info=None)
    return JSONResponse({"ok": True})


@app.post("/api/photo")
def photo_upload(file: UploadFile = File(...)):
    """Observe a photo (colours, hair silhouette) for the editor's seeds and preview."""
    import io
    from PIL import Image
    raw = file.file.read(MAX_PHOTO_BYTES + 1)
    if not raw or len(raw) > MAX_PHOTO_BYTES:
        return JSONResponse({"error": "bad_size"}, status_code=413)
    try:
        fmt = Image.open(io.BytesIO(raw)).format
    except Exception:
        return JSONResponse({"error": "not_an_image"}, status_code=400)
    suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(fmt)
    if suffix is None:
        return JSONResponse({"error": "unsupported_format"}, status_code=400)
    path = OUT / "photo" / f"current{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    photo = QU.inspect(path)
    if photo.face is None:
        return JSONResponse({"error": "no_face"}, status_code=422)
    try:
        seg = P.bottom_mask(photo.image) if P.parsing_on() else None
    except Exception:
        # No parser model on this host: colours only, no hair silhouette from the photo.
        seg = None
    observed = C.extract(photo, hair_bbox=None, seg=seg, hair_overlay=True)
    name = Path(file.filename or "photo").name
    info = _photo_info(name, observed)
    _PHOTO.update(observed=observed, name=name, info=info)
    return JSONResponse(info, headers={"Cache-Control": "no-store"})


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


# Arm faces whose slim width differs from classic (slim: 3 px, classic: 4 px).
SLIM_LAYOUT = get_layout("slim")
SLIM_FACES = {}
for _part in ("r_arm", "l_arm"):
    for _face in PART_FACES[_part]:
        _sf = SLIM_LAYOUT.face(_part, _face, 0)
        if (_sf.w, _sf.h) != DIMS[f"{_part}.{_face}"]:
            SLIM_FACES[f"{_part}.{_face}"] = (_sf.w, _sf.h)


def _slim_rects() -> dict:
    rects = {}
    for layer, index in (("L1", 0), ("L2", 1)):
        rects[layer] = {}
        for face in FACES:
            part, short = face.split(".", 1)
            rects[layer][face] = list(SLIM_LAYOUT.face(part, short, index).rect)
    return rects


def _normalize_key(src) -> dict:
    out = {"L1": {}, "L2": {}}
    if not isinstance(src, dict):
        return out
    slim = src.get("slim")
    if isinstance(slim, dict):
        sub = {"L1": {}, "L2": {}}
        for layer in LAYERS:
            face_map = slim.get(layer) or {}
            if not isinstance(face_map, dict):
                continue
            for face, (w, h) in SLIM_FACES.items():
                grid = face_map.get(face)
                if isinstance(grid, list):
                    sub[layer][face] = [
                        [int(bool(grid[v][u])) if v < len(grid) and u < len(grid[v]) else 0 for u in range(w)]
                        for v in range(h)
                    ]
        if any(sub[layer] for layer in LAYERS):
            out["slim"] = sub
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
    # Head hair comes from the same pipeline the renderer uses (reference
    # silhouette + overlay), not from the rule stencil: a rule-stencil seed
    # cut the side hair when style and length masks were intersected.
    head_cells: set = set()
    target = R.render(_observed(), attrs, (), mask_override={}, head_hair_out=head_cells)
    l1 = {}
    for face in ("top", "front", "right", "left", "back", "bottom"):
        f = LAYOUT.face("head", face, 0)
        l1[f"head.{face}"] = [[1 if (face, u, v) in head_cells else 0 for u in range(f.w)] for v in range(f.h)]
    # Body hair drape (medium/long/very_long): seed L1 and L2 from the
    # procedural target vs a short-hair baseline. This is the body hair the
    # editor/mask view previously missed.
    base = dict(attrs.values)
    base["hair_style"] = "short"
    base["hair_length"] = "short"
    baseline = R.render(_observed(), A.validate(base), (), mask_override={})
    l2 = {}
    # Head L2 hair: the procedural hair overlay. Seed from the overlay-on
    # target vs an overlay-off baseline so the head L2 hair is selectable too.
    no_overlay = dataclasses.replace(_observed(), hair_overlay=False)
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
    baseline = R.render(_observed(), A.validate(base), (), mask_override={})
    base["bottom_garment"] = value
    target = R.render(_observed(), A.validate(base), (), mask_override={})
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
    baseline = R.render(_observed(), A.validate(base), (), mask_override={})
    base[key] = value
    target = R.render(_observed(), A.validate(base), (), mask_override={})
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
    baseline = R.render(_observed(), A.validate(base), (), mask_override={})
    base["inner_top"] = value
    target = R.render(_observed(), A.validate(base), (), mask_override={})
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
    baseline = R.render(_observed(), A.validate(base), (), mask_override={})
    base["top_garment"] = value
    target = R.render(_observed(), A.validate(base), (), mask_override={})
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


def _migrate_draft_if_legacy() -> None:
    """One-time: drafts before schema 3 carry rule-stencil hair masks that clip
    the side hair. Back the file up, re-seed the hair keys, and mark it v3."""
    import time
    path = OUT / "attribute_masks.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(doc, dict) or not isinstance(doc.get("masks"), dict):
        return
    try:
        schema = int(doc.get("schema", 1))
    except (TypeError, ValueError):
        schema = 1
    if schema >= SCHEMA:
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (OUT / f"attribute_masks.pre-v3-{stamp}.json").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    masks = dict(doc["masks"])
    for name, grid in _seed_masks().items():
        if name.startswith(("hair_style.", "hair_length.")):
            masks[name] = grid
    # Legacy top masks may hold a partial body; refill it once here, since the
    # v3 load path no longer does it.
    for name, grid in list(masks.items()):
        if name.startswith("top_garment.") and not name.endswith(".none") and isinstance(grid, dict):
            masks[name] = _normalize_key(_refill_top_body(grid))
    doc = {**doc, "schema": SCHEMA, "masks": masks}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


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
    _migrate_draft_if_legacy()
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
                # A saved top mask can have a partial body (e.g. back=2 cells).
                # Refill body faces; keep the user's arm/leg edits.
                src = _refill_top_body(src)
            if key in ("hair_style", "hair_length") and isinstance(src, dict):
                # Hood up/down hides body-back hair in every hair mask.
                src = _zero_body_back_hair(src)
            masks[name] = _normalize_key(src)
    return masks


@app.get("/")
def index():
    return FileResponse(ROOT / "index.html", headers={"Cache-Control": "no-store"})


def _atlas_rects() -> dict:
    """Face rects in the 64x64 classic atlas, per layer (L1 = base, L2 = overlay)."""
    rects = {}
    for layer, index in (("L1", 0), ("L2", 1)):
        rects[layer] = {}
        for face in FACES:
            part, short = face.split(".", 1)
            r = LAYOUT.face(part, short, index).rect
            rects[layer][face] = list(r)
    return rects


@app.get("/api/defaults")
def defaults():
    return JSONResponse(
        {"parts": PARTS, "part_faces": PART_FACES, "faces": FACES, "dims": DIMS,
         "layers": LAYERS, "enums": COMBO_ENUMS, "defaults": DEFAULT_COMBO,
         "models": ["classic", "slim"], "combo": DEFAULT_COMBO,
         "atlas": {"size": 64, "rects": _atlas_rects()},
         "slim": {"sub_faces": sorted(SLIM_FACES), "dims": {f: list(d) for f, d in SLIM_FACES.items()},
                  "atlas": {"size": 64, "rects": _slim_rects()}},
         "maskable": MASKABLE, "masks": _defaults()},
        headers={"Cache-Control": "no-store"},
    )


def _refill_top_body(src: dict) -> dict:
    """A top's body faces must be full: a partial body reads as "not top" -> skin."""
    src = {layer: dict(src.get(layer, {}) or {}) for layer in LAYERS}
    for layer in LAYERS:
        for face in FACES:
            if face.startswith("body."):
                w, h = DIMS[face]
                src[layer][face] = [[1] * w for _ in range(h)]
    return src


def _zero_body_back_hair(src: dict) -> dict:
    """Hood policy: no hair masks on the body back (the hood covers it)."""
    src = {layer: dict(src.get(layer, {}) or {}) for layer in LAYERS}
    for layer in LAYERS:
        for face in FACES:
            if face.startswith("body.back"):
                src[layer][face] = _blank(face)
    return src


def _finalize_seed(key: str, value: str, src: dict) -> dict:
    """Post-process a procedural seed the same way the saved-draft defaults do."""
    if key == "top_garment" and value != "none" and isinstance(src, dict):
        src = _refill_top_body(src)
    if key in ("hair_style", "hair_length") and isinstance(src, dict):
        src = _zero_body_back_hair(src)
    return _normalize_key(src)


def _seed_masks() -> dict:
    """Procedural seed for every maskable value (no draft, no approved asset)."""
    out = {}
    for key, values in MASKABLE.items():
        for value in values:
            out[f"{key}.{value}"] = _finalize_seed(key, value, _seed_for(key, value))
    return out


@app.get("/api/seed-all")
def seed_all():
    return JSONResponse({"masks": _seed_masks()}, headers={"Cache-Control": "no-store"})


@app.get("/api/seed")
def seed(key: str, value: str):
    if key not in MASKABLE or value not in MASKABLE[key]:
        return JSONResponse({"error": "bad key/value"}, status_code=400)
    return JSONResponse({"key": key, "value": value, "mask": _finalize_seed(key, value, _seed_for(key, value))},
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


SHORT_STYLES = {"short", "pixie"}
LONG_STYLES = {"long_straight", "long_wavy", "ponytail", "bun"}
LONG_LENGTHS = {"long", "very_long"}


def _hair_pair_warning(style, length) -> str | None:
    """Advisory: contradictory hair pairs make the style and length masks cut each other."""
    if (style in SHORT_STYLES and length in LONG_LENGTHS) or (style in LONG_STYLES and length == "short"):
        return f"hair: {style} + {length} 은 서로 맞지 않아 머리가 잘릴 수 있음"
    return None


def _combo_warnings(requested: dict, attrs: A.Attributes) -> list[str]:
    out: list[str] = []
    pair = _hair_pair_warning(attrs.get("hair_style"), attrs.get("hair_length"))
    if pair:
        out.append(pair)
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
    source = str(body.get("source", "draft"))
    if source not in ("draft", "production"):
        return JSONResponse({"error": "bad source"}, status_code=400)
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
    observed = _observed()
    # The final render is always produced: it is the base skin under the atlas
    # and the 3D texture in Final view. Mask view adds a separate image.
    # production = the approved asset (what generation uses); draft = the editor masks.
    render_masks = None if source == "production" else masks
    final = R.render(observed, attrs, (), mask_override=render_masks, model=model)
    final.image.save(OUT / "preview.png")
    mask_url = None
    if mode == "mask":
        canvas = R.render(observed, attrs, (), mask_override={}, model=model)
        shown = AM.resolve_model(masks, model)
        for layer, layer_index in (("L1", 0), ("L2", 1)):
            for face in FACES:
                part, short = face.split(".", 1)
                grid = AM.get_mask(shown, key, value, layer, part, short)
                if not grid:
                    continue
                color = (0, 150, 190, 255) if layer == "L1" else (0, 220, 240, 255)
                for v, row in enumerate(grid[:DIMS[face][1]]):
                    for u, bit in enumerate(row[:DIMS[face][0]]):
                        if bit:
                            canvas.put(part, short, u, v, color, layer_index)
        canvas.image.save(OUT / "preview_mask.png")
        mask_url = "/out/preview_mask.png"
    return JSONResponse({"skin": "/out/preview.png", "mask": mask_url, "key": key, "value": value, "source": source,
                         "mode": mode, "model": model, "effective": attrs.values,
                         "warnings": warnings, "coerced": list(attrs.coerced),
                         "derived": list(attrs.derived)},
                        headers={"Cache-Control": "no-store"})
