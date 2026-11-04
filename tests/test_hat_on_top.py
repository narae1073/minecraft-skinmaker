"""A per-skin cap must sit on top of the hair; production renders stay unchanged."""
from __future__ import annotations

import json
from pathlib import Path

from skinmaker import attribute_masks as AM
from skinmaker import attributes as A
from skinmaker import production_qa as Q
from skinmaker import render as R
from skinmaker.canvas import rgba
from skinmaker.format import get_layout
from skinmaker.render import FACE_SHADE, shade

ROOT = Path(__file__).resolve().parent.parent
DRAFT = json.loads((ROOT / "assets" / "headwear_cap.draft.json").read_text(encoding="utf-8"))["masks"]["headwear.cap"]


def _cap_texels(image, grid_by_face):
    lay = get_layout("classic")
    cap = rgba("#e9eef3")
    total = kept = 0
    for name, grid in grid_by_face.items():
        face = name.split(".", 1)[1]
        f = lay.face("head", face, 0)
        target = tuple(shade(cap, FACE_SHADE.get(face, 1.0)))[:3]
        for v, row in enumerate(grid):
            for u, bit in enumerate(row):
                if bit:
                    total += 1
                    kept += image.getpixel((f.x + u, f.y + v))[:3] == target
    return total, kept


def test_hat_on_top_keeps_the_whole_draft_cap_visible():
    masks = dict(AM.load_masks())
    masks["headwear.cap"] = DRAFT
    attrs = A.validate(dict(Q._attrs("short", "short", "none").values, headwear="cap"))
    plain = R.render(Q._observed(), attrs, (), mask_override=masks, model="classic").image.convert("RGBA")
    top = R.render(Q._observed(), attrs, (), mask_override=masks, model="classic",
                   hat_on_top=True).image.convert("RGBA")
    total, kept_plain = _cap_texels(plain, DRAFT["L1"])
    total2, kept_top = _cap_texels(top, DRAFT["L1"])
    assert total == total2 == 152
    assert kept_top == total
    assert kept_plain < total  # the hair overwrites most of it without the pass


def test_production_render_is_unchanged_without_the_flag():
    attrs = A.validate(dict(Q._attrs("short", "short", "none").values, headwear="cap"))
    a = R.render(Q._observed(), attrs, (), mask_override=AM.load_masks(), model="classic")
    b = R.render(Q._observed(), attrs, (), mask_override=AM.load_masks(), model="classic", hat_on_top=False)
    assert a.image.tobytes() == b.image.tobytes()
