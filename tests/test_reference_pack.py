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
        canvas.get("head", "front", u, 1, 1)[:3]
        for u in range(8)
    }
    assert len(colors) == 1
    c = next(iter(colors))
    assert all(c[i] >= alt[i] - 16 for i in range(3)), c
    for u in (1, 2, 5, 6):
        for v in (4, 5):
            assert canvas.get("head", "front", u, v, 1)[3] == 0, (u, v)
    assert R.hood_variant("a") in (0, 1, 2)


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




def test_fur_hood_uses_front_brim_not_crown_ring(monkeypatch):
    from skinmaker import render as R
    from skinmaker.colors import ColorSample
    from test_render import observed, attrs

    base = observed(top="#28527a")
    base = __import__("dataclasses").replace(
        base, top_alt=ColorSample("#dbeafe", 0.5, True, (219, 234, 254), 10)
    )
    monkeypatch.setattr(R, "hood_variant", lambda seed: 2)
    canvas = R.render(base, attrs(top_garment="hoodie", hood="up"), ())
    top = {canvas.get("head", "top", u, v, 1)[:3] for v in range(8) for u in range(8)}
    assert len(top) == 1, top  # no crown fur that creates edge slivers
    front = {canvas.get("head", "front", u, 1, 1)[:3] for u in range(8)}
    assert len(front) == 1, front  # continuous full-width brim band


def test_fur_hood_has_no_body_light_trim(monkeypatch):
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
    for face in ("front", "back"):
        f = canvas.layout.face("body", face, 1)
        for v in range(4):
            for u in range(f.w):
                c = canvas.get("body", face, u, v, 1)[:3]
                assert not all(abs(c[i] - alt[i]) <= 16 for i in range(3)), (face, u, v, c)


def test_noise_cannot_scatter_fur_hood_crown(monkeypatch):
    from skinmaker import render as R
    from skinmaker.colors import ColorSample
    from test_render import observed, attrs

    base = observed(top="#28527a")
    base = __import__("dataclasses").replace(
        base, top_alt=ColorSample("#dbeafe", 0.5, True, (219, 234, 254), 10)
    )
    monkeypatch.setattr(R, "hood_variant", lambda seed: 2)
    canvas = R.render(base, attrs(top_garment="hoodie", hood="up"), (),
                      noise_seed=12345, noise_level=0.5)
    top = {canvas.get("head", "top", u, v, 1) for v in range(8) for u in range(8)}
    assert len(top) == 1, top  # no noise grid on the hood crown


def test_approved_templates_replace_pack_patterns():
    eyes_ok = {"id": "e1", "sclera": [[0] * 8 for _ in range(2)],
               "iris": [[1] * 8 for _ in range(2)], "sclera_px": 2, "iris_px": 2}
    eyes_no = {"id": "e2", "sclera": [[1] * 8 for _ in range(2)],
               "iris": [[1] * 8 for _ in range(2)]}
    hood = {"id": "h1", "faces": {f: [[1] * 8 for _ in range(8)] for f in RP.HEAD_FACES},
            "coverage": 320}
    pack = {"eyes": [eyes_no], "hoods": {"up": [], "down": []}}
    cand = {"eyes": [eyes_ok, eyes_no], "hood_up": [hood], "hood_down": []}
    approvals = {"eyes": {"e1": {"approved": True}, "e2": {"approved": False}},
                 "hood_up": {"h1": {"approved": True}}}
    out = RP.apply_template_approvals(pack, cand, approvals)
    assert out["eyes"] == [eyes_ok]
    assert out["hoods"]["up"] == [hood]
    assert out["template_approvals"] == {"eyes": ["e1"], "hood_up": ["h1"]}


def test_preferred_eye_is_most_frequent():
    pack = RP.load_pack()
    preferred = "eye-c252cfa113"
    for hooded in (False, True):
        counts: dict[str, int] = {}
        for i in range(300):
            eye = RP.select_eyes(pack, str(i), hooded=hooded)
            counts[eye["id"]] = counts.get(eye["id"], 0) + 1
        assert counts.get(preferred, 0) > max(
            (n for k, n in counts.items() if k != preferred), default=0
        ), (hooded, counts)
        assert counts[preferred] > 120, (hooded, counts)


def test_bang_tip_patterns_are_reference_derived():
    pack = RP.load_pack()
    for length in ("short", "long"):
        tips = pack.get("bang_tips", {}).get(length)
        assert tips and any(0 in t for t in tips), tips
        assert all(len(t) == 8 for t in tips)


def test_eye_source_blocklist_excludes_bad_pupils():
    blocked = RP.load_eye_blocklist()
    assert "c5e01e147580d8c7" in blocked
    assert RP.eye_source_blocked("c5e01e147580d8c7")
    assert not RP.eye_source_blocked("definitely-not-blocked")
    # The blocklist must not remove hair/bang data; only eye extraction is filtered.
    pack = RP.load_pack()
    assert pack.get("hair") and pack.get("bang_tips")


def test_reference_edge_masks_are_present_and_bounded():
    pack = RP.load_pack()
    masks = pack.get("edge_masks", {})
    for face in ("right", "left", "back"):
        assert masks.get(face)
        for m in masks[face]:
            assert len(m) == 8
    # Nan test: L2 notches only remove cells where L1 hair remains.
    from skinmaker import render as R
    from test_render import observed, attrs
    canvas = R.render(observed(), attrs(hair_length="long", hair_style="long_straight"), ())
    for face in ("right", "left", "back"):
        f = canvas.layout.face("head", face, 1)
        for v in range(4, 8):
            for u in range(f.w):
                if canvas.get("head", face, u, v, 1)[3] == 0:
                    assert canvas.get("head", face, u, v)[3] == 255, (face, u, v)


def test_edge_masks_are_length_specific():
    pack = RP.load_pack()
    by_len = pack.get("edge_masks_by_length", {})
    assert by_len["long"]["right"][0] == [0, 0, 0, 0, 1, 1, 1, 0]
    assert by_len["short"]["right"][0] == [0, 0, 0, 0, 1, 1, 0, 0]


# --- L2 hair sculpt templates (2026-11-01) ----------------------------------

def _mask(cells: dict[str, list[tuple[int, int]]]) -> dict[str, np.ndarray]:
    out = {f: np.zeros((8, 8), dtype=bool) for f in RP.MASK_FACES}
    for f, uv in cells.items():
        for u, v in uv:
            out[f][v, u] = True
    return out


def test_hair_mask_rejects_non_hair_colour_l2():
    im = _skin()
    f0 = L.face("head", "top", 0)
    for v in range(8):
        for u in range(8):
            im.putpixel((f0.x + u, f0.y + v), (60, 40, 30, 255))
    back = L.face("head", "back", 1)
    for v in range(8):
        im.putpixel((back.x + 0, back.y + v), (62, 41, 31, 255))  # hair strand
        im.putpixel((back.x + 7, back.y + v), (62, 41, 31, 255))
        im.putpixel((back.x + 4, back.y + v), (40, 220, 60, 255))  # green ribbon
    m = RP.extract_hair_mask(im)
    assert m is not None
    assert m["back"][:, 0].all() and m["back"][:, 7].all()
    assert not m["back"][:, 4].any()


def test_cluster_majority_vote_and_min_count():
    common = _mask({"front": [(u, 1) for u in range(2, 6)], "back": [(0, v) for v in range(8)]})
    noisy = []
    for i in range(12):
        m = {f: a.copy() for f, a in common.items()}
        m["top"][i % 8, i % 8] = True  # one-off pixel per skin
        noisy.append(m)
    outlier = _mask({"top": [(u, v) for u in range(8) for v in range(8)]})
    out = RP.cluster_hair_masks(noisy + [outlier], k=2, min_count=3)
    assert len(out) == 1 and out[0]["count"] == 12
    t = out[0]["faces"]
    assert sum(map(sum, t["top"])) == 0  # one-offs voted out
    assert [row[0] for row in t["back"]] == [1] * 8
    assert RP.cluster_hair_masks(noisy + [outlier], k=2, min_count=3) == out  # deterministic


def test_committed_hair_masks_are_sparse_reference_sculpts():
    pack = RP.load_pack()
    for length in ("short", "long"):
        items = pack["hair_masks"][length]
        assert items and all(t["count"] >= 10 for t in items)
        for t in items:
            cov = {f: sum(map(sum, t["faces"][f])) / 64 for f in RP.MASK_FACES}
            # Reference L2 is never a solid shell (median top 0.12, sides 0.20).
            assert cov["top"] <= 0.3 and cov["right"] <= 0.5 and cov["back"] <= 0.6
            assert cov["front"] > 0.2  # fringe arc present
        assert RP.select_hair_mask(pack, length, "short", "s") is RP.select_hair_mask(pack, length, "short", "s")


def test_template_l2_is_sparse_and_spares_eyes():
    from skinmaker import render as R
    from tests.test_render import attrs, observed
    for style, length in (("long_straight", "long"), ("short", "short"), ("bob", "medium")):
        im = R.render(observed(), attrs(hair_length=length, hair_style=style), ()).image
        top = L.face("head", "top", 1)
        n_top = sum(im.getpixel((top.x + u, top.y + v))[3] > 0 for v in range(8) for u in range(8))
        assert n_top <= 0.3 * 64, style
        front = L.face("head", "front", 1)
        for v in (5, 6):
            for u in range(1, 7):
                assert im.getpixel((front.x + u, front.y + v))[3] == 0, (style, u, v)
        # L2 head pixels on top/sides/back only sit over L1 hair (never skin).
        for name in ("top", "right", "left", "back"):
            f1, f2 = L.face("head", name, 0), L.face("head", name, 1)
            skin = R.shade(R.resolve_colors(observed())["skin"], R.FACE_SHADE[name])
            for v in range(8):
                for u in range(8):
                    if im.getpixel((f2.x + u, f2.y + v))[3]:
                        assert im.getpixel((f1.x + u, f1.y + v)) != skin, (style, name, u, v)


# --- L1 hair shading (2026-11-01) ---------------------------------------------

def test_l1_tones_are_absolute_luma_deltas():
    im = _skin()
    for name in RP.L1_TONE_FACES:
        f = L.face("head", name, 0)
        for v in range(8):
            for u in range(8):
                c = 40 if u % 2 else 30  # 1px strands on near-black hair
                im.putpixel((f.x + u, f.y + v), (c, c, c, 255))
    t = RP.extract_l1_tones(im)
    assert t is not None
    side = t["right"]
    assert {int(side[0, 0]), int(side[0, 1])} == {-5, 5}  # +-5 around the 35 median


def test_l1_tones_reject_partial_hair_sides():
    im = _skin()
    for name in RP.L1_TONE_FACES:
        f = L.face("head", name, 0)
        for v in range(8):
            for u in range(8):
                im.putpixel((f.x + u, f.y + v), (60, 40, 30, 255))
    _head_face(im, "back", 0)  # back is skin, not hair
    assert RP.extract_l1_tones(im) is None


def test_committed_l1_tones_render_reference_spread():
    """Rendered side/back luma p10-p90 span tracks the reference: ~14 dark, ~28 light."""
    from skinmaker import render as R
    pack = RP.load_pack()
    items = pack["hair_l1_tones"]
    assert items and all(t["count"] >= 10 for t in items)
    for hc, target in (((25, 20, 18, 255), 14), ((200, 160, 90, 255), 28)):
        spans = []
        for t in items:
            lum = [0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
                   for f in ("right", "back") for v in range(8) for u in range(8)
                   for c in [R._hair_tone(hc, f, u, v, t)]]
            spans.append(np.percentile(lum, 90) - np.percentile(lum, 10))
        w = np.average(spans, weights=[t["count"] for t in items])
        assert 0.75 * target <= w <= 1.25 * target, (hc, w)
    assert R._hair_tone((50, 40, 30, 255), "right", 0, 0, None) == R.shade((50, 40, 30, 255), R.FACE_SHADE["right"])


def test_noise_spares_reference_shaded_hair_only():
    from skinmaker import render as R
    from tests.test_render import attrs, observed
    a = attrs(hair_length="long", hair_style="long_straight")
    clean = R.render(observed(), a, ()).image
    noisy = R.render(observed(), a, (), noise_seed=11).image
    skin = R.resolve_colors(observed())["skin"]
    checked = 0
    for name in ("top", "right", "back"):
        f = L.face("head", name, 0)
        skin_c = R.shade(skin, R.FACE_SHADE[name])
        for v in range(8):
            for u in range(8):
                if clean.getpixel((f.x + u, f.y + v)) == skin_c:
                    continue  # skin keeps its noise
                checked += 1
                assert clean.getpixel((f.x + u, f.y + v)) == noisy.getpixel((f.x + u, f.y + v)), (name, u, v)
    assert checked > 100
    f2 = L.face("head", "back", 1)
    assert all(clean.getpixel((f2.x + u, f2.y + v)) == noisy.getpixel((f2.x + u, f2.y + v))
               for v in range(8) for u in range(8))
    body = L.face("body", "front", 0)
    assert any(clean.getpixel((body.x + u, body.y + v)) != noisy.getpixel((body.x + u, body.y + v))
               for v in range(body.h) for u in range(body.w))
