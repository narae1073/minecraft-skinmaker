"""Procedural attribute-mask seeds: the shape each attribute value draws, computed
by diffing the renderer. Pure functions of a SeedContext (the observed colours and
the base attribute values); no photo or server state.

Used by the mask editor (developer) and by the website's per-skin job editor.
"""
from __future__ import annotations

import contextlib
import contextvars
import dataclasses
from dataclasses import dataclass, field
from typing import Iterator

from . import attributes as A
from . import production_qa as Q
from . import render as R
from .format import get_layout

SCHEMA = 3


@dataclass(frozen=True)
class SeedContext:
    """What the seeds render with: observed colours and base attribute values."""
    observed: object
    base: dict = field(default_factory=dict)

    def base_values(self) -> dict:
        return dict(self.base)


def fixture_context() -> SeedContext:
    fixture = Q._attrs("long", "long_straight", "none")
    base = dict(fixture.values, hair_bbox=fixture.hair_bbox, hood="none")
    return SeedContext(observed=Q._observed(), base=base)


_CTX: contextvars.ContextVar = contextvars.ContextVar("seed_context", default=None)


def _ctx() -> SeedContext:
    return _CTX.get() or fixture_context()


@contextlib.contextmanager
def using(ctx: SeedContext) -> Iterator[SeedContext]:
    token = _CTX.set(ctx)
    try:
        yield ctx
    finally:
        _CTX.reset(token)


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
    attrs = A.validate(dict(_ctx().base_values(), hair_length=length, hair_style=style))
    # Head hair comes from the same pipeline the renderer uses (reference
    # silhouette + overlay), not from the rule stencil: a rule-stencil seed
    # cut the side hair when style and length masks were intersected.
    head_cells: set = set()
    target = R.render(_ctx().observed, attrs, (), mask_override={}, head_hair_out=head_cells)
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
    baseline = R.render(_ctx().observed, A.validate(base), (), mask_override={})
    l2 = {}
    # Head L2 hair: the procedural hair overlay. Seed from the overlay-on
    # target vs an overlay-off baseline so the head L2 hair is selectable too.
    no_overlay = dataclasses.replace(_ctx().observed, hair_overlay=False)
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
    base = _ctx().base_values()
    base["bottom_garment"] = "none"
    baseline = R.render(_ctx().observed, A.validate(base), (), mask_override={})
    base["bottom_garment"] = value
    target = R.render(_ctx().observed, A.validate(base), (), mask_override={})
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
    base = _ctx().base_values()
    base["top_garment"] = "hoodie"
    base["inner_top"] = "none"
    base[key] = "none"
    baseline = R.render(_ctx().observed, A.validate(base), (), mask_override={})
    base[key] = value
    target = R.render(_ctx().observed, A.validate(base), (), mask_override={})
    f = LAYOUT.face("body", "front", 0)
    grid = [[1 if target.get("body", "front", u, v, 0)[:3] != baseline.get("body", "front", u, v, 0)[:3] else 0
             for u in range(f.w)] for v in range(f.h)]
    return {"L1": {"body.front": grid}, "L2": {}}


def _seed_inner(value: str) -> dict:
    if value == "none":
        return {}
    base = _ctx().base_values()
    base["top_garment"] = "hoodie"
    base["inner_top"] = "none"
    baseline = R.render(_ctx().observed, A.validate(base), (), mask_override={})
    base["inner_top"] = value
    target = R.render(_ctx().observed, A.validate(base), (), mask_override={})
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
    base = _ctx().base_values()
    base["top_garment"] = "none"
    baseline = R.render(_ctx().observed, A.validate(base), (), mask_override={})
    base["top_garment"] = value
    target = R.render(_ctx().observed, A.validate(base), (), mask_override={})
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


def seed_for(key: str, value: str) -> dict:
    return _seed_for(key, value)


def seed_masks() -> dict:
    return _seed_masks()


def finalize_seed(key: str, value: str, src: dict) -> dict:
    return _finalize_seed(key, value, src)


def seed_hair(key: str, value: str) -> dict:
    return _seed_hair(key, value)
