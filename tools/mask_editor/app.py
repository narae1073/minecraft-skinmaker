"""General attribute-mask editor: paint shape stencils for attribute values.

The editor is intentionally shape-only (no colour picker): it edits binary
occupancy for a selected (attribute, value) on the head L1/L2 faces. The
production renderer uses the same asset; colours/patterns stay in the pipeline.
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

OUT = REPO / "out" / "mask_editor"
OUT.mkdir(parents=True, exist_ok=True)
FACES = [f"head.{f}" for f in ("top", "front", "right", "left", "back", "bottom")]
LAYERS = ["L1", "L2"]
MASKABLE = {
    "hood": ("up", "down"),
    "headwear": ("beanie", "cap"),
    "hood_fit": ("shallow",),
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


def _blank() -> list[list[int]]:
    return [[0] * 8 for _ in range(8)]


def _normalize_key(src) -> dict:
    """Accept a {L1,L2} entry; fill missing head faces with blanks."""
    out = {"L1": {}, "L2": {}}
    if not isinstance(src, dict):
        return out
    for layer in LAYERS:
        face_map = src.get(layer) or {}
        if not isinstance(face_map, dict):
            continue
        for face in FACES:
            grid = face_map.get(face)
            if isinstance(grid, list):
                out[layer][face] = [
                    [int(bool(grid[v][u])) if v < len(grid) and u < len(grid[v]) else 0 for u in range(8)]
                    for v in range(8)
                ]
            else:
                out[layer][face] = _blank()
    return out


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
            src = (saved.get(name) if isinstance(saved, dict) else None) or approved.get(name) or {}
            masks[name] = _normalize_key(src)
    return masks


@app.get("/")
def index():
    return FileResponse(ROOT / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/defaults")
def defaults():
    return JSONResponse(
        {"faces": FACES, "layers": LAYERS, "maskable": MASKABLE, "masks": _defaults()},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/save")
async def save(req: Request):
    body = await req.json()
    payload = {
        "version": 1,
        "source": "mask_editor",
        "policy": AM.POLICY,
        "masks": body.get("masks", {}),
    }
    (OUT / "attribute_masks.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return {"ok": True, "path": str(OUT / "attribute_masks.json")}


def _attrs_for(key: str, value: str) -> A.Attributes:
    base = dict(Q._attrs("long", "long_straight", "up").values)
    base.setdefault("headwear", "none")
    base.setdefault("hood_fit", "normal")
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
                grid = AM.get_mask(masks, key, value, layer, "head", face.split(".", 1)[1])
                if not grid:
                    continue
                color = (0, 150, 190, 255) if layer == "L1" else (0, 220, 240, 255)
                for v, row in enumerate(grid[:8]):
                    for u, bit in enumerate(row[:8]):
                        if bit:
                            canvas.put("head", face.split(".", 1)[1], u, v, color, layer_index)
    else:
        canvas = R.render(observed, attrs, (), mask_override=masks)
    canvas.image.save(OUT / "preview.png")
    return JSONResponse({"skin": "/out/preview.png", "key": key, "value": value, "mode": mode},
                        headers={"Cache-Control": "no-store"})
