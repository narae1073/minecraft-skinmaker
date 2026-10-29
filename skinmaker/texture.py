"""Cropped fabric textures for complex patterns (2026-10-28).

Pure parametric drawing cannot reproduce floral/plaid detail at 64x64. This
module samples the real garment from the photo when the pattern is complex:

    mask (SCHP classes) -> best pattern patch -> 8x12 / 4x12 tiles
    -> <=12-colour quantisation

The renderer overlays structural primitives (zipper/collar/buttons) on top so
the result still reads as pixel art. Plain garments never use this path.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

COMPLEX_PATTERNS = frozenset({"plaid", "check", "graphic", "floral"})
TEXTURE_COLORS = 12
TEXTURE_COMPLEXITY_MIN = 10.0  # high-frequency fabric energy that counts as "patterned"
PATCH_FRACTION = 0.35
MIN_MASK_PIXELS = 200
BODY_SIZE = (8, 12)
SIDE_SIZE = (4, 12)


@dataclass(frozen=True)
class FabricTexture:
    """Quantised fabric tiles. body=8x12 (front/back), side/leg=4x12."""

    body: Image.Image
    side: Image.Image
    leg: Image.Image
    complexity: float
    bbox: tuple[int, int, int, int]

    @property
    def usable(self) -> bool:
        return self.complexity >= TEXTURE_COMPLEXITY_MIN


def _quantise(patch: Image.Image, size: tuple[int, int], colors: int = TEXTURE_COLORS) -> Image.Image:
    tile = patch.resize(size, Image.BOX)
    tile = tile.quantize(colors=colors, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    return tile.convert("RGB")


def _complexity(patch: Image.Image) -> float:
    """High-frequency fabric energy (0-255). Plain shading is low-frequency;
    floral/plaid/check have strong local edges. A shaded white tee scores ~7,
    floral ~20+, jeans ~3.
    """
    gray = np.asarray(patch.convert("L").resize((32, 32), Image.BOX), dtype=np.float32)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    return round(float(np.abs(gray - blur).mean()), 2)


def _best_window(image: Image.Image, mask: np.ndarray, bbox: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Central fabric window of the garment bbox.

    A sliding max-variance window can land on a phone/hand and poison the tile;
    the garment centre is fabric by construction. 35% keeps one or two pattern
    repeats instead of averaging the whole garment.
    """
    x0, y0, x1, y1 = bbox
    width, height = x1 - x0, y1 - y0
    size = max(16, int(min(width, height) * PATCH_FRACTION))
    size = min(size, width, height)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    left = max(x0, min(cx - size // 2, x1 - size))
    top = max(y0, min(cy - size // 2, y1 - size))
    return (left, top, left + size, top + size)

def _masked_patch(image: Image.Image, mask: np.ndarray, window: tuple[int, int, int, int]) -> Image.Image:
    """Fabric-only patch: non-garment pixels filled with the median fabric colour."""
    x0, y0, x1, y1 = window
    patch = np.asarray(image.convert("RGB").crop(window), dtype=np.uint8).copy()
    m = mask[y0:y1, x0:x1]
    if m.any():
        fill = np.median(patch[m], axis=0).astype(np.uint8)
        patch[~m] = fill
    return Image.fromarray(patch)


def crop_fabric(image: Image.Image, seg: np.ndarray | None, classes: tuple[int, ...]) -> FabricTexture | None:
    """Garment mask -> quantised tiles. None when the mask has too little fabric."""
    if seg is None:
        return None
    mask = np.isin(np.asarray(seg), classes)
    if int(mask.sum()) < MIN_MASK_PIXELS:
        return None
    ys, xs = np.where(mask)
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    window = _best_window(image, mask, bbox)
    crop = _masked_patch(image, mask, window)
    body = _quantise(crop, BODY_SIZE)
    side = _quantise(crop, SIDE_SIZE)
    leg = _quantise(crop, SIDE_SIZE)
    complexity = _complexity(crop)
    return FabricTexture(body=body, side=side, leg=leg, complexity=complexity, bbox=bbox)
