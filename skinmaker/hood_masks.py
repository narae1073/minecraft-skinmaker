"""Mask-driven hood rendering shared by production and the mask editor.

The masks are head-only L1/L2 grids (8x8 per face).  ``apply_hood_masks``
paints the fabric and the hood details (brim, seams, edge shading, and a
hood-down upper-back fold).  It deliberately paints **no body-front cowl**.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .canvas import shade

HEAD_FACES = ("top", "front", "right", "left", "back")
NEIGHBORS = ((1, 0), (-1, 0), (0, 1), (0, -1))
MASK_PATH = Path(__file__).resolve().parent.parent / "assets" / "hood_masks.json"


def _bit(grid, u, v):
    return 0 <= v < len(grid) and 0 <= u < len(grid[v]) and bool(grid[v][u])


def _edge(grid, u, v):
    return any(not _bit(grid, u + du, v + dv) for du, dv in NEIGHBORS)


def _four(color):
    color = tuple(color)
    return color + (255,) if len(color) == 3 else color


@lru_cache(maxsize=1)
def load_hood_masks(path: str | None = None) -> dict | None:
    try:
        data = json.loads(Path(path or MASK_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    masks = data.get("masks", data) if isinstance(data, dict) else None
    return masks if isinstance(masks, dict) else None


def apply_hood_masks(canvas, base, alt, kind: str, masks: dict, mode: str = "hood") -> None:
    from .render import FACE_SHADE  # local import: render imports this module

    base = _four(base)
    alt = _four(alt)
    for layer, layer_index, factor in (("L1", 0, 0.72), ("L2", 1, 1.0)):
        for face in HEAD_FACES:
            grid = (masks.get(layer) or {}).get(f"head.{face}") or []
            if not grid:
                continue
            face_base = shade(shade(base, FACE_SHADE.get(face, 1.0)), factor)
            for v, row in enumerate(grid[:8]):
                for u, bit in enumerate(row[:8]):
                    if not bit:
                        continue
                    if mode == "mask":
                        color = (0, 150, 190, 255) if layer == "L1" else (0, 220, 240, 255)
                    else:
                        color = shade(face_base, 0.80 if _edge(grid, u, v) else 1.0)
                        if layer == "L1":
                            color = shade(color, 0.90)
                        if face == "top" and u in (3, 4) and v > 0:
                            color = shade(color, 0.90)
                        if face == "back" and u == 4:
                            color = shade(color, 0.90)
                    canvas.put("head", face, u, v, color, layer_index)

    if mode != "hood":
        return

    if kind == "up":
        grid = (masks.get("L2") or {}).get("head.front") or []
        for v, row in enumerate(grid[:8]):
            for u, bit in enumerate(row[:8]):
                if bit and not _bit(grid, u, v + 1):
                    canvas.put("head", "front", u, v,
                               shade(shade(base, FACE_SHADE.get("front", 1.0)), 0.55), 1)
    else:
        for face in ("back", "right", "left"):
            grid = (masks.get("L2") or {}).get(f"head.{face}") or []
            for v, row in enumerate(grid[:8]):
                for u, bit in enumerate(row[:8]):
                    if bit and not _bit(grid, u, v + 1):
                        canvas.put("head", face, u, v,
                                   shade(shade(shade(base, FACE_SHADE.get(face, 1.0)), 0.80), 0.85), 1)
        fold = shade(base, FACE_SHADE.get("back", 1.0))
        f = canvas.layout.face("body", "back", 1)
        for u in range(f.w):
            canvas.put("body", "back", u, 0, fold, 1)
        for u in (2, 3, 4, 5):
            canvas.put("body", "back", u, 1, shade(fold, 0.82), 1)


def render_preview(canvas, colors: dict, masks: dict, kind: str, mode: str = "hood") -> None:
    """Editor preview: fabric colours from the sampled top garment."""
    base = _four(colors.get("top") or colors["hair"])
    alt = _four(colors.get("top_alt") or shade(base, 0.72))
    apply_hood_masks(canvas, base, alt, kind, masks, mode)
