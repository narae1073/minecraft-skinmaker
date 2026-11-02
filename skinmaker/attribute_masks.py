"""General attribute-value shape stencils (2026-11-02).

The mask editor edits binary occupancy for shape-defining attribute values:
``hood.up``, ``hood.down``, later ``headwear.cap``, ``hair_style.bob``, etc.
Colors/patterns/shadows remain in the render pipeline; a mask only decides
which cells of a part/layer/face are drawn for that value.

Asset shape::

    {"version": 1, "masks": {
        "hood.up": {"L1": {"head.front": [[0,1,...], ...]}, "L2": {...}},
        "hair_style.bob": {"L1": {"head.front": [...]}}
    }}

Extra keys (headwear, hair, body) are added by the editor and approved with a
SHA in ``attribute_masks_approval.json``. Values without a mask keep the
procedural renderer (fallback).
"""
from __future__ import annotations

import json
from pathlib import Path

from .attributes import ENUMS

ROOT = Path(__file__).resolve().parent.parent
ASSET_PATH = ROOT / "assets" / "attribute_masks.json"
APPROVAL_PATH = ROOT / "assets" / "attribute_masks_approval.json"
POLICY = "attribute-masks-2026-11-02"
LAYERS = ("L1", "L2")


def load_asset(path: str | Path | None = None) -> dict:
    try:
        data = json.loads(Path(path or ASSET_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_masks(path: str | Path | None = None) -> dict:
    """Return ``{attribute.value: {L1/L2: {part.face: grid}}}``.

    Legacy hood assets (``{up:..., down:...}``) are converted to
    ``hood.up``/``hood.down`` for the migration path.
    """
    data = load_asset(path)
    masks = data.get("masks", data)
    if not isinstance(masks, dict):
        return {}
    if ("up" in masks or "down" in masks) and not any(k.startswith("hood.") for k in masks):
        masks = {f"hood.{k}": v for k, v in masks.items()}
    return masks


def _split_key(key: str) -> tuple[str, str] | None:
    if not isinstance(key, str) or "." not in key:
        return None
    attr, value = key.split(".", 1)
    if attr not in ENUMS or value not in ENUMS[attr]:
        return None
    return attr, value


def validate_asset(data: dict) -> list[str]:
    """Schema validation; the editor/approval script must reject on any error."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["asset must be an object"]
    masks = data.get("masks", data)
    if not isinstance(masks, dict):
        return ["masks must be an object"]
    for key, entry in masks.items():
        if _split_key(key) is None:
            errors.append(f"invalid key: {key!r}")
            continue
        if not isinstance(entry, dict):
            errors.append(f"{key}: layers must be an object")
            continue
        for layer, face_map in entry.items():
            if layer not in LAYERS:
                errors.append(f"{key}: invalid layer {layer!r}")
                continue
            if not isinstance(face_map, dict):
                errors.append(f"{key}.{layer}: faces must be an object")
                continue
            for face, grid in face_map.items():
                if not isinstance(face, str) or "." not in face:
                    errors.append(f"{key}.{layer}: invalid face {face!r}")
                    continue
                if not isinstance(grid, list) or not grid:
                    errors.append(f"{key}.{layer}.{face}: grid must be a non-empty list")
                    continue
                for v, row in enumerate(grid):
                    if not isinstance(row, list) or not row:
                        errors.append(f"{key}.{layer}.{face}: row {v} must be a non-empty list")
                        continue
                    for u, bit in enumerate(row):
                        if bit not in (0, 1, True, False):
                            errors.append(f"{key}.{layer}.{face}[{v}][{u}]: expected 0/1")
    return errors


def has_mask(masks: dict, key: str, value: str) -> bool:
    return f"{key}.{value}" in (masks or {})


def get_mask(masks: dict, key: str, value: str, layer: str, part: str, face: str):
    entry = (masks or {}).get(f"{key}.{value}") or {}
    return (entry.get(layer) or {}).get(f"{part}.{face}")


def legacy_hood_masks(masks: dict) -> dict | None:
    """Adapt the general masks to the hood renderer's ``{up/down}`` shape."""
    out: dict = {}
    for kind in ("up", "down"):
        entry = (masks or {}).get(f"hood.{kind}")
        if entry:
            out[kind] = entry
    return out or None
