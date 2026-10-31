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
    for v in (4, 5):
        assert canvas.get("head", "front", 1, v, 1)[3] == 0, v


def test_committed_hood_shells_are_solid():
    pack = RP.load_pack()
    assert pack is not None
    for p in pack["hoods"]["up"]:
        for face in RP.HEAD_FACES:
            mask = p["faces"][face]
            if face == "front":
                assert all(v == 1 for row in mask[:3] for v in row)
                assert all(v == 0 for row in mask[3:] for v in row)
            else:
                assert all(v == 1 for row in mask for v in row), face
    assert len(pack["hoods"]["up"]) >= 1


def test_hood_up_has_no_hair_through_crown():
    from skinmaker import render as R
    from test_render import observed, attrs

    canvas = R.render(observed(hair="#3a2a1c"), attrs(top_garment="hoodie", hood="up"), ())
    for v in range(8):
        for u in range(8):
            assert canvas.get("head", "top", u, v, 1)[3], (u, v)
    for v in range(3):
        for u in range(8):
            assert canvas.get("head", "front", u, v, 1)[3], (u, v)
    for u in (1, 2, 5, 6):
        for v in (4, 5):
            assert canvas.get("head", "front", u, v, 1)[3] == 0


def test_hood_variants_use_alt_trim_and_keep_eyes(monkeypatch):
    from skinmaker import render as R
    from skinmaker.colors import ColorSample
    from test_render import observed, attrs

    base = observed(top="#28527a")
    base = __import__("dataclasses").replace(
        base, top_alt=ColorSample("#dbeafe", 0.5, True, (219, 234, 254), 10)
    )
    alt = (219, 234, 254)
    monkeypatch.setattr(R, "hood_variant", lambda seed: 2)
    canvas = R.render(base, attrs(top_garment="hoodie", hood="up"), ())
    colors = {
        canvas.get("head", "top", u, v, 1)[:3]
        for v in range(8) for u in range(8)
        if canvas.get("head", "top", u, v, 1)[3]
    }
    assert any(all(c[i] >= alt[i] - 12 for i in range(3)) for c in colors), colors
    for u in (1, 2, 5, 6):
        for v in (4, 5):
            assert canvas.get("head", "front", u, v, 1)[3] == 0, (u, v)
    assert R.hood_variant("a") in (0, 1, 2)


def test_fur_hood_top_is_connected(monkeypatch):
    from skinmaker import render as R
    from skinmaker.colors import ColorSample
    from test_render import observed, attrs

    base = observed(top="#28527a")
    base = __import__("dataclasses").replace(
        base, top_alt=ColorSample("#dbeafe", 0.5, True, (219, 234, 254), 10)
    )
    monkeypatch.setattr(R, "hood_variant", lambda seed: 2)
    canvas = R.render(base, attrs(top_garment="hoodie", hood="up"), ())
    alt = (219, 234, 254)
    grid = [[canvas.get("head", "top", u, v, 1)[:3] for u in range(8)] for v in range(8)]
    hits = [(u, v) for v in range(8) for u in range(8)
            if all(abs(grid[v][u][i] - alt[i]) <= 14 for i in range(3))]
    assert hits, "fur band missing"
    for u, v in hits:
        neighbors = [(u + du, v + dv) for du, dv in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        assert any(0 <= x < 8 and 0 <= y < 8 and
                   all(abs(grid[y][x][i] - alt[i]) <= 14 for i in range(3))
                   for x, y in neighbors), (u, v)


def test_fur_hood_has_no_accent_pixels_in_band(monkeypatch):
    from skinmaker import render as R
    from skinmaker.colors import ColorSample
    from test_render import observed, attrs

    base = observed(top="#28527a")
    base = __import__("dataclasses").replace(
        base, top_alt=ColorSample("#dbeafe", 0.5, True, (219, 234, 254), 10)
    )
    monkeypatch.setattr(R, "hood_variant", lambda seed: 2)
    canvas = R.render(base, attrs(top_garment="hoodie", hood="up"), ())
    grid = [[canvas.get("head", "top", u, v, 1)[:3] for u in range(8)] for v in range(8)]
    assert len({grid[0][u] for u in range(8)}) == 1, "highlight above fur band"
    for v in range(3, 8):
        assert len({grid[v][u] for u in range(8)}) == 1, ("seam below band", v)


def test_fur_ring_wraps_sides_and_back(monkeypatch):
    from skinmaker import render as R
    from skinmaker.colors import ColorSample
    from test_render import observed, attrs

    base = observed(top="#28527a")
    base = __import__("dataclasses").replace(
        base, top_alt=ColorSample("#dbeafe", 0.5, True, (219, 234, 254), 10)
    )
    monkeypatch.setattr(R, "hood_variant", lambda seed: 2)
    canvas = R.render(base, attrs(top_garment="hoodie", hood="up"), ())
    from skinmaker.canvas import rgba, shade
    alt = rgba("#dbeafe")
    for face in ("right", "left", "back"):
        expected = shade(alt, R.FACE_SHADE[face])[:3]
        for v in (0, 1):
            for u in range(8):
                c = canvas.get("head", face, u, v, 1)[:3]
                assert c == expected, (face, u, v, c, expected)
