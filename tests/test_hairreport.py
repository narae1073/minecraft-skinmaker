"""Deterministic hair QA: bottom coverage, sparse L2, profile/drape."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from skinmaker import attributes as A
from skinmaker import hairreport as HR
from skinmaker import render as R
from skinmaker.colors import ColorSample, ObservedColors
from skinmaker.format import get_layout


def sample(h, conf=True):
    return ColorSample(h, 0.6, conf, tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)), 200)


def observed(hair="#112233"):
    return ObservedColors(sample("#e0ac69"), sample(hair), sample("#2f6fb5"), sample("#3c4450"),
                          (1.0, 1.0, 1.0), True, (0.5, 0.3, 0.2))


def attrs(**kw):
    base = {"top_garment": "tee", "bottom_garment": "jeans", "pattern": "plain",
            "sleeve_len": "long", "hair_length": "short", "beard": "none",
            "inner_top": "none", "neckwear": "none",
            "closure_type": "none", "collar_type": "none", "pocket_type": "none",
            "symmetry": "symmetric", "hair_bbox": [200, 50, 800, 600]}
    base.update(kw)
    return A.validate(base)


def render(length="very_long", hair="#112233"):
    canvas = R.render(observed(hair), attrs(hair_length=length), ())
    return canvas.image


def test_report_passes_long_sculpted_skin():
    img = render()
    report = HR.analyze(img, hair="#112233", skin="#e0ac69", hair_length="very_long")
    assert report["ok"], report
    # Reference-style L2: L1 hair stays visible between sculpted strands.
    assert report["l2_holes"] > 0
    assert report["l2_counts"]["top"] <= 0.3 * 64
    assert report["chin_hair"] == 0
    assert report["bottom_rear_hair"] >= report["bottom_rear_total"] * 0.9
    assert report["side_jump"] <= 1
    assert report["body_rows"] >= 6


def test_report_detects_solid_l2_shell():
    """The pre-2026-11-01 silhouette copy (solid L2 face) is a defect."""
    img = render().copy()
    f = get_layout("classic").face("head", "back", 1)
    for v in range(f.h):
        for u in range(f.w):
            img.putpixel((f.x + u, f.y + v), (17, 34, 51, 255))
    report = HR.analyze(img, hair="#112233", skin="#e0ac69", hair_length="very_long")
    assert any("solid L2 shell on back" in p for p in report["problems"])
    assert not report["ok"]


def test_report_detects_chin_hair():
    img = render().copy()
    f = get_layout("classic").face("head", "bottom", 0)
    img.putpixel((f.x + 3, f.y + 7), (17, 34, 51, 255))  # texture row 7 = chin
    report = HR.analyze(img, hair="#112233", skin="#e0ac69", hair_length="very_long")
    assert report["chin_hair"] > 0
    assert not report["ok"]


def test_report_front_hole_and_hairline_checks():
    from skinmaker import render as R
    canvas = R.render(observed(), attrs(hair_length="long", hair_style="long_straight"), ())
    base = canvas.image
    r = HR.analyze(base, hair="#112233", skin="#e0ac69", hair_length="long", hair_style="long_straight")
    assert r["ok"], r
    assert r["front_body_rows"] == 11 and r["back_body_rows"] == 12  # reference drape

    broken = base.copy()
    f = get_layout("classic").face("head", "front", 0)
    for u in range(1, 7):
        broken.putpixel((f.x + u, f.y + 3), (224, 172, 105, 255))
    r2 = HR.analyze(broken, hair="#112233", skin="#e0ac69", hair_length="long", hair_style="long_straight")
    assert r2["row3_hair"] < 6
    assert not r2["ok"]
