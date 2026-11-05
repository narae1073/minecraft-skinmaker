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

# Same .env handling as the backend: the photo classification needs the VLM key.
from backend.app import load_env_file  # noqa: E402
load_env_file()

OUT = REPO / "out" / "mask_editor"
OUT.mkdir(parents=True, exist_ok=True)
from skinmaker import attribute_seeds as AS  # noqa: E402
from skinmaker.attribute_seeds import (  # noqa: E402,F401
    COMBO_ENUMS, COMBO_KEYS, DEFAULT_COMBO, DIMS, FACES, LAYERS, LAYOUT, LENGTH_STYLE, MASKABLE,
    PARTS, PART_FACES, SLIM_FACES, SLIM_LAYOUT, _blank, _normalize_key, _refill_top_body,
    _slim_rects, _zero_body_back_hair, SCHEMA, _COMBO_BASE)


def _photo_base() -> dict:
    """Base attribute values for seeds: the photo's classification when loaded, else the fixture."""
    attrs = _PHOTO["attrs"]
    if attrs is not None:
        return dict(attrs.values, hair_bbox=attrs.hair_bbox, hood="none")
    return AS.fixture_context().base


def _seed_base(hood: str = "none") -> dict:
    base = _photo_base()
    base["hood"] = hood
    return base


def _in_seed_context(fn, *args):
    with AS.using(AS.SeedContext(observed=_observed(), base=_photo_base())):
        return fn(*args)


def _seed_for(key: str, value: str) -> dict:
    return _in_seed_context(AS.seed_for, key, value)


def _seed_hair(key: str, value: str) -> dict:
    return _in_seed_context(AS.seed_hair, key, value)


def _seed_sleeve(key: str, value: str) -> dict:
    return _in_seed_context(AS._seed_sleeve, key, value)


def _seed_bottom(value: str) -> dict:
    return _in_seed_context(AS._seed_bottom, value)


def _seed_structure(key: str, value: str) -> dict:
    return _in_seed_context(AS._seed_structure, key, value)


def _seed_inner(value: str) -> dict:
    return _in_seed_context(AS._seed_inner, value)


def _seed_top(value: str) -> dict:
    return _in_seed_context(AS._seed_top, value)


def _seed_masks() -> dict:
    return _in_seed_context(AS.seed_masks)


def _finalize_seed(key: str, value: str, src: dict) -> dict:
    return AS.finalize_seed(key, value, src)


app = FastAPI(title="skinmaker attribute mask editor")

# One uploaded photo drives the seeds and the preview. Without one, the
# fixture observation is used. Single-user local tool: process-wide state.
_PHOTO: dict = {"observed": None, "name": None, "info": None, "attrs": None}
MAX_PHOTO_BYTES = 15 * 1024 * 1024


def _observed():
    return _PHOTO["observed"] or Q._observed()


def _classify_photo(photo):
    """Run the production VLM classification on the photo. Returns (result, transport name)."""
    import os
    from skinmaker.classify import classify
    from skinmaker.vlm import get_transport
    name = os.environ.get("SKINMAKER_TRANSPORT", "gemini")
    timeout = float(os.environ.get("SKINMAKER_VLM_TIMEOUT", "10"))
    transport = get_transport(name, model=os.environ.get("SKINMAKER_MODEL"), timeout=timeout)
    return classify(photo, transport), name


def _photo_info(name: str, observed) -> dict:
    return {"name": name, "skin": observed.skin.hex, "hair": observed.hair.hex,
            "top": observed.top.hex, "bottom": observed.bottom.hex,
            "hair_stencil": observed.hair_stencil is not None}


@app.get("/api/photo")
def photo_info():
    return JSONResponse(_PHOTO["info"], headers={"Cache-Control": "no-store"})


@app.delete("/api/photo")
def photo_clear():
    _PHOTO.update(observed=None, name=None, info=None, attrs=None)
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
    # The photo is only needed while it is observed: write it to a private temp
    # file, read it, delete it. Nothing under out/ (which /out serves) keeps the
    # original; only the derived colours and attributes are held in memory.
    import os
    import tempfile
    fd, tmp_name = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
        photo = QU.inspect(tmp_name)
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
    if photo.face is None:
        return JSONResponse({"error": "no_face"}, status_code=422)
    try:
        result, transport_name = _classify_photo(photo)
    except Exception as exc:
        return JSONResponse({"error": "classify_failed", "detail": type(exc).__name__}, status_code=502)
    if not result.ok:
        status = 503 if result.error_kind == "transport" else 502
        return JSONResponse({"error": "classify_failed", "detail": result.error}, status_code=status)
    try:
        seg = P.bottom_mask(photo.image) if P.parsing_on() else None
    except Exception:
        # No parser model on this host: colours only, no hair silhouette from the photo.
        seg = None
    observed = C.extract(photo, hair_bbox=result.hair_bbox_px, seg=seg, hair_overlay=True)
    name = Path(file.filename or "photo").name
    info = dict(_photo_info(name, observed), attributes_source=transport_name,
                attributes={field: result.attributes.get(field) for field in A.FIELD_ORDER})
    _PHOTO.update(observed=observed, name=name, info=info, attrs=result.attributes)
    return JSONResponse(info, headers={"Cache-Control": "no-store"})


TOKEN_ENV = "SKINMAKER_EDITOR_TOKEN"
TOKEN_COOKIE = "editor_token"
GATED_PREFIXES = ("/api/", "/out/")


def _token_ok(request: Request, token: str) -> bool:
    import hmac
    sent = request.headers.get("x-editor-token") or request.cookies.get(TOKEN_COOKIE) or ""
    return hmac.compare_digest(sent.encode(), token.encode())


@app.middleware("http")
async def require_token(request: Request, call_next):
    """When SKINMAKER_EDITOR_TOKEN is set, the API and rendered output need it
    (header X-Editor-Token, or the cookie set by POST /api/auth)."""
    import os
    token = os.environ.get(TOKEN_ENV, "")
    path = request.url.path
    if token and path.startswith(GATED_PREFIXES) and path != "/api/auth" and not _token_ok(request, token):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)


@app.post("/api/auth")
async def editor_auth(request: Request):
    import hmac
    import os
    token = os.environ.get(TOKEN_ENV, "")
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    given = str((body or {}).get("token", ""))
    if not token or not hmac.compare_digest(given.encode(), token.encode()):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    response = JSONResponse({"ok": True})
    response.set_cookie(TOKEN_COOKIE, token, httponly=True, samesite="strict", max_age=60 * 60 * 24 * 30)
    return response


@app.middleware("http")
async def no_store_static(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/static", StaticFiles(directory=ROOT), name="static")
app.mount("/out", StaticFiles(directory=OUT), name="out")


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
