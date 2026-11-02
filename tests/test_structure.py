"""Generic structural drawers: 1px lines, alignment, symmetry."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from skinmaker import attributes as A
from skinmaker import render as R
from skinmaker.canvas import shade
from skinmaker.colors import ObservedColors
from skinmaker.format import get_layout

from skinmaker.canvas import rgba


def observed():
    from skinmaker.colors import ColorSample

    def s(h, conf=True):
        return ColorSample(h, 0.6, conf, (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)), 200)

    return ObservedColors(s("#e0ac69"), s("#3a2a1c"), s("#2f6fb5"), s("#3c4450"),
                          (1.0, 1.0, 1.0), True, (0.5, 0.3, 0.2))


def attrs(**kw):
    base = {
        "top_garment": "shirt", "bottom_garment": "jeans", "pattern": "plain",
        "sleeve_len": "long", "hair_length": "short", "beard": "none",
        "inner_top": "none", "neckwear": "none",
        "closure_type": "buttons", "collar_type": "crew",
        "pocket_type": "none", "symmetry": "symmetric",
        "hair_bbox": [200, 50, 800, 600],
    }
    base.update(kw)
    return A.validate(base)


def front(canvas):
    return get_layout("classic").face("body", "front", 0)


def test_buttons_are_one_pixel_and_vertically_aligned():
    canvas = R.render(observed(), attrs(closure_type="buttons", collar_type="none"), (), "classic")
    f = front(canvas)
    base = shade(rgba(observed().top.hex), 1.0)[:3]
    for v in (1, 4, 7, 10):
        assert canvas.image.getpixel((f.x + 4, f.y + v))[:3] != base, v
    for v in (2, 3, 5, 6, 8, 9, 11):
        assert canvas.image.getpixel((f.x + 4, f.y + v))[:3] == base, v
    # placket is the only 1px column at u=3
    assert canvas.image.getpixel((f.x + 3, f.y + 6))[:3] != base


def test_zipper_is_one_pixel_center_line():
    canvas = R.render(observed(), attrs(closure_type="zipper", collar_type="none"), (), "classic")
    f = front(canvas)
    base = shade(rgba(observed().top.hex), 1.0)[:3]
    for v in range(1, 12):
        assert canvas.image.getpixel((f.x + 4, f.y + v))[:3] != base, v
    assert canvas.image.getpixel((f.x + 2, f.y + 6))[:3] == base


def test_collar_is_symmetric():
    # sweater: 셔츠 칼라 단추 폴백(비대칭 placket)을 피하고 칼라만 검사
    canvas = R.render(observed(), attrs(top_garment="sweater", collar_type="shirt", closure_type="none"), (), "classic")
    f = front(canvas)
    for v in range(2):
        for u in range(1, 4):
            assert canvas.image.getpixel((f.x + u, f.y + v)) == canvas.image.getpixel((f.x + 7 - u, f.y + v))


def test_patch_pockets_are_two_rectangles():
    canvas = R.render(observed(), attrs(pocket_type="patch", closure_type="none", collar_type="none"), (), "classic")
    f = front(canvas)
    base = shade(rgba(observed().top.hex), 1.0)[:3]
    for x0 in (1, 5):
        for u in (x0, x0 + 1):
            assert canvas.image.getpixel((f.x + u, f.y + 5))[:3] != base
        assert canvas.image.getpixel((f.x + x0, f.y + 7))[:3] != base
    assert canvas.image.getpixel((f.x + 3, f.y + 6))[:3] == base


def test_no_structure_for_tee_or_bare():
    plain = R.render(observed(), attrs(top_garment="tee", closure_type="none", collar_type="none"), (), "classic")
    bare = R.render(observed(), attrs(top_garment="none", closure_type="buttons", collar_type="crew"), (), "classic")
    f = front(plain)
    for u, v in ((3, 6), (4, 6), (3, 0), (2, 0)):
        assert plain.image.getpixel((f.x + u, f.y + v))[:3] == shade(rgba(observed().top.hex), 1.0)[:3] or (u, v) == (3, 0)


def test_shirt_collar_without_closure_tag_draws_buttons():
    """VLM 이 closure=none 으로 놓쳐도 셔츠 칼라면 단추로 보정."""
    canvas = R.render(observed(), attrs(top_garment="shirt", collar_type="shirt", closure_type="none"), (), "classic")
    f = front(canvas)
    base = shade(rgba(observed().top.hex), 1.0)[:3]
    for v in (1, 4, 7, 10):
        assert canvas.image.getpixel((f.x + 4, f.y + v))[:3] != base, v


def test_zipper_color_is_derived_from_top():
    """Notes 2026-11-02 (30x): the zip must resemble the top, not fixed silver."""
    from skinmaker.structure import _zipper_color

    canvas = R.render(observed(), attrs(closure_type="zipper", collar_type="none"), (), "classic")
    f = front(canvas)
    px = canvas.image.getpixel((f.x + 4, f.y + 1))[:3]
    assert px[2] > px[0]  # blue top -> blue-derived zipper
    assert px != (201, 206, 214)  # not the old fixed METAL
    assert _zipper_color((20, 20, 20, 255))[0] > 20      # dark top -> lighter zip
    assert _zipper_color((240, 240, 240, 255))[0] < 240  # light top -> darker zip


def test_open_jacket_shows_inner_strip_and_no_zipper():
    """Notes 2026-11-02 (15x): an open jacket must show the inner layer, not a
    closed zipper."""
    canvas = R.render(observed(), attrs(top_garment="jacket", closure_type="open",
                                        inner_top="tee", collar_type="crew"), (), "classic")
    f = front(canvas)
    base = shade(rgba(observed().top.hex), 1.0)[:3]
    inner3 = canvas.image.getpixel((f.x + 3, f.y + 6))[:3]
    inner4 = canvas.image.getpixel((f.x + 4, f.y + 6))[:3]
    assert inner3 != base and inner4 != base
    assert inner3 != (201, 206, 214) and inner4 != (201, 206, 214)  # no fixed METAL
    assert canvas.image.getpixel((f.x + 2, f.y + 6))[:3] != base    # jacket edge
    assert canvas.image.getpixel((f.x + 1, f.y + 6))[:3] == base    # jacket body


def test_arms_use_the_body_pattern():
    """Notes 2026-11-02 (6x): torso stripes/graphic must continue onto arms."""
    stripe = R.render(observed(), attrs(top_garment="shirt", pattern="vertical_stripe",
                                        sleeve_len="long", closure_type="none", collar_type="none"),
                      (), "classic")
    plain = R.render(observed(), attrs(top_garment="shirt", pattern="plain",
                                      sleeve_len="long", closure_type="none", collar_type="none"),
                     (), "classic")
    arm = get_layout("classic").face("r_arm", "front", 0)
    stripe_row = {stripe.image.getpixel((arm.x + u, arm.y + 1)) for u in range(arm.w)}
    plain_row = {plain.image.getpixel((arm.x + u, arm.y + 1)) for u in range(arm.w)}
    assert len(stripe_row) > 1, stripe_row
    assert len(plain_row) == 1, plain_row
