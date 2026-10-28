"""Cropped fabric textures: mask-constrained patch -> quantised tiles."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skinmaker import texture as T


def _scene(pattern: bool):
    img = Image.new("RGB", (80, 80), (245, 245, 245))
    arr = np.asarray(img).copy()
    if pattern:
        for y in range(20, 70):
            for x in range(20, 70):
                arr[y, x] = (200, 30, 60) if (x // 4 + y // 4) % 2 else (240, 200, 40)
    else:
        for y in range(20, 70):
            for x in range(20, 70):
                arr[y, x] = (40, 80, 160)
    img = Image.fromarray(arr)
    seg = np.zeros((80, 80), np.uint8)
    seg[20:70, 20:70] = 4
    return img, seg


def test_complex_pattern_yields_quantised_tiles():
    img, seg = _scene(True)
    tex = T.crop_fabric(img, seg, (4,))
    assert tex is not None
    assert tex.body.size == (8, 12) and tex.side.size == (4, 12) and tex.leg.size == (4, 12)
    assert tex.usable and tex.complexity >= T.TEXTURE_COMPLEXITY_MIN, tex.complexity
    assert len(tex.body.getcolors(256) or []) <= T.TEXTURE_COLORS


def test_plain_fabric_is_not_usable():
    img, seg = _scene(False)
    tex = T.crop_fabric(img, seg, (4,))
    assert tex is not None and not tex.usable


def test_too_few_mask_pixels_returns_none():
    img, seg = _scene(True)
    tiny = np.zeros_like(seg)
    tiny[30:33, 30:33] = 4
    assert T.crop_fabric(img, tiny, (4,)) is None
    assert T.crop_fabric(img, None, (4,)) is None


def test_crop_is_deterministic():
    img, seg = _scene(True)
    a = T.crop_fabric(img, seg, (4,))
    b = T.crop_fabric(img, seg, (4,))
    assert a.body.tobytes() == b.body.tobytes() and a.bbox == b.bbox
