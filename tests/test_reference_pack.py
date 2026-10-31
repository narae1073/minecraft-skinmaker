"""Reference pack extraction/selection and hood overlay contracts."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest
from PIL import Image

from skinmaker import reference_pack as RP
from skinmaker.format import get_layout

L = get_layout("classic")


def _skin() -> Image.Image:
    return Image.new("RGBA", (64, 64), (0, 0, 0, 0))


def _head_face(im: Image.Image, name: str, layer: int = 0):
    f = L.face("head", name, layer)
    for v in range(f.h):
        for u in range(f.w):
            im.putpixel((f.x + u, f.y + v), (224, 172, 105, 255))


def test_committed_pack_shape_and_counts():
    pack = RP.load_pack()
    assert pack is not None
    assert pack["source_counts"]["long_hair"] >= 1
    assert pack["source_counts"]["short_hair"] >= 1
    for length in ("short", "long"):
        assert pack["hair"][length]
        for p in pack["hair"][length]:
            assert set(p["faces"]) == set(RP.HEAD_FACES)
            assert len(p["faces"]["top"]) == 8
    for p in pack["eyes"]:
        assert len(p["sclera"]) == 2 and len(p["sclera"][0]) == 8
        assert p["sclera"][0][1:3] == p["sclera"][0][5:7][::-1]
    assert pack["hoods"]["up"] and pack["hoods"]["down"]


def test_hair_pattern_extracts_l2_tones():
    im = _skin()
    for face in ("top", "front", "back", "right", "left"):
        _head_face(im, face, 0)
        f = L.face("head", face, 1)
        for v in range(f.h):
            for u in range(f.w):
                im.putpixel((f.x + u, f.y + v), (40, 40, 40, 255) if u % 3 else (80, 80, 80, 255))
    p = RP.extract_hair_pattern(im)
    assert p is not None
    assert p["coverage"] > 40
    assert set(p["faces"]) == set(RP.HEAD_FACES)


def test_eye_pattern_mirrors_left_to_right():
    im = _skin()
    _head_face(im, "front", 0)
    f = L.face("head", "front", 0)
    for v in (4, 5):
        for u in (1, 5):
            im.putpixel((f.x + u, f.y + v), (245, 245, 245, 255))
        for u in (2, 6):
            im.putpixel((f.x + u, f.y + v), (40, 70, 140, 255))
    p = RP.extract_eye_pattern(im)
    assert p is not None
    for v in range(2):
        assert p["sclera"][v][1:3] == p["sclera"][v][5:7][::-1]
        assert p["iris"][v][1:3] == p["iris"][v][5:7][::-1]


def test_hood_masks_extract_up_and_down():
    up = _skin()
    for face in RP.HEAD_FACES:
        _head_face(up, face, 0)
        _head_face(up, face, 1)
    p = RP.extract_hood_up(up)
    assert p is not None and p["coverage"] >= 40

    down = _skin()
    for name in ("front", "back"):
        f = L.face("body", name, 1)
        for v in range(4):
            for u in range(f.w):
                down.putpixel((f.x + u, f.y + v), (60, 80, 120, 255))
    q = RP.extract_hood_down(down)
    assert q is not None and q["coverage"] == 64


def test_selectors_are_deterministic_and_length_aware():
    pack = RP.load_pack()
    assert RP.select_hair(pack, "long", "long_straight", "x") is RP.select_hair(pack, "long", "long_straight", "x")
    assert RP.select_hair(pack, "long", "long_straight", "x") is not None
    assert RP.select_hair(pack, "short", "pixie", "x") is not None
    assert RP.select_eyes(pack, "x") is not None
    assert RP.select_hood(pack, "up", "x") is not None


def test_hood_overlay_paints_top_and_keeps_face(monkeypatch):
    from skinmaker import render as R
    from test_render import observed, attrs

    mask = {
        "faces": {
            "top": [[1] * 8 for _ in range(8)],
            "front": [[1] * 8 for _ in range(8)],
            "back": [[1] * 8 for _ in range(8)],
            "right": [[1] * 8 for _ in range(8)],
            "left": [[1] * 8 for _ in range(8)],
            "front_body": [[1] * 8 for _ in range(4)],
            "back_body": [[1] * 8 for _ in range(4)],
        }
    }
    monkeypatch.setattr(R.RP, "load_pack", lambda: {})
    monkeypatch.setattr(R.RP, "select_hood", lambda pack, kind, seed="": mask)
    base = observed(skin="#e0ac69", hair="#112233")
    canvas = R.render(base, attrs(top_garment="hoodie", hood="up"), ())
    top = canvas.get("head", "top", 0, 0, 1)
    assert top[3] and top[:3] != (0, 0, 0)
    # Face rows 3-7 stay open (eyes are L1 and must not get a hood shell).
    for v in (3, 4, 5, 6, 7):
        assert canvas.get("head", "front", 1, v, 1)[3] == 0, v
