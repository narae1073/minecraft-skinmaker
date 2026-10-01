"""단계별 시각 샘플 패널 (네트워크 없음)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PIL import Image

from skinmaker import quality as Q
from skinmaker.debugview import (
    CAPTION_H,
    NOTE_H,
    PANEL_W,
    Panel,
    build_panels,
    contact_sheet,
    max_chars,
    note_lines,
    panel_atlas,
    panel_preview,
    panel_reject,
    panel_s0,
    panel_uvmap,
)
from skinmaker.placeholder import build_placeholder

PHOTO = Q.FaceBox(200, 180, 130, 180)


def photo_input(image=None, face=PHOTO, flags=(), model_note=""):
    image = image or Image.new("RGB", (640, 640), (90, 80, 70))
    q = Q.Quality(0.93, face.area, 120.0, 400.0, 110.0, True)
    return Q.PhotoInput("t.jpg", image, face, q if face else None, tuple(flags))


# --- 캡션 / 줄바꿈 -------------------------------------------------------

def test_max_chars_shrinks_with_width():
    assert max_chars(360) < max_chars(720)
    assert max_chars(60) >= 12


def test_note_lines_wrap_and_cover_all_text():
    text = "x" * 200
    lines = note_lines(text, PANEL_W)
    assert len(lines) > 1
    assert "".join(lines) == text


def test_note_lines_of_empty_text_is_one_blank():
    assert note_lines("", PANEL_W) == [""]


def test_panel_height_grows_with_note_lines():
    img = Image.new("RGB", (PANEL_W, 50), (0, 0, 0))
    short = Panel("t", img, "a").render(PANEL_W)
    long = Panel("t", img, "y" * 200).render(PANEL_W)
    assert long.height - short.height == NOTE_H * (len(note_lines("y" * 200, PANEL_W)) - 1)
    assert short.height == CAPTION_H + 50 + NOTE_H


def test_panel_body_is_scaled_to_panel_width():
    img = Image.new("RGB", (64, 32), (0, 0, 0))
    out = Panel("t", img).render(200)
    assert out.size == (200, CAPTION_H + 100)


# --- S0 패널 -------------------------------------------------------------

def test_s0_panel_draws_regions_and_metrics():
    panel = panel_s0(photo_input(flags=("blur",)))
    assert "S0" in panel.title
    assert "blur" in panel.note
    assert "score=0.93" in panel.note
    assert "hair=" in panel.note and "bands=" in panel.note
    assert panel.image.size[0] == PANEL_W


def test_s0_panel_clean_has_no_flags():
    assert "flags=none" in panel_s0(photo_input()).note


def test_reject_panel_when_no_face():
    p = Q.PhotoInput("t.jpg", Image.new("RGB", (400, 400), (30, 30, 30)), None, None, ())
    panel = panel_s0(p)
    assert "REJECTED" in panel.note
    assert "no face" in panel.note


def test_reject_panel_for_error_flags():
    p = Q.PhotoInput("t.jpg", Image.new("RGB", (400, 400), (30, 30, 30)), None, None, ("error:OSError",))
    assert "error:OSError" in panel_reject(p).note


# --- S3 / S4 패널 --------------------------------------------------------

@pytest.mark.parametrize("model", ["classic", "slim"])
def test_atlas_panel_is_square(model):
    skin = build_placeholder(model).image
    assert panel_atlas(skin).image.width == panel_atlas(skin).image.height


def test_uvmap_panel_keeps_region_colors_visible():
    skin = build_placeholder("classic").image
    panel = panel_uvmap(skin, "classic")
    assert panel.image.size[0] == 64 * 7
    assert "UV guide" in panel.title


def test_preview_panel_documented_order():
    panel = panel_preview(build_placeholder("classic").image, "classic")
    for word in ("front", "side", "back", "top", "overlay"):
        assert word in panel.title


# --- 조립 ----------------------------------------------------------------

def test_contact_sheet_stacks_with_padding():
    from skinmaker.debugview import PAD

    img = Image.new("RGB", (PANEL_W, 40), (0, 0, 0))
    panels = [Panel(f"p{i}", img) for i in range(3)]
    rendered = [p.render(PANEL_W) for p in panels]
    out = contact_sheet(panels)
    assert out.size == (PANEL_W, sum(r.height for r in rendered) + PAD * 2)


def test_contact_sheet_of_nothing():
    assert contact_sheet([]).size == (PANEL_W, CAPTION_H)


def test_build_panels_full_set():
    skin = build_placeholder("classic").image
    panels = build_panels(photo_input(), skin, "classic")
    assert [p.title.split()[0] for p in panels] == ["S0", "S3", "S3", "S4"]


def test_build_panels_without_skin_only_renders_s0():
    panels = build_panels(photo_input(), None, "classic")
    assert len(panels) == 1
    assert panels[0].title.startswith("S0")


def test_build_panels_rejected_still_renders_skin_panels():
    skin = build_placeholder("classic").image
    rejected = Q.PhotoInput("t.jpg", Image.new("RGB", (300, 300), (0, 0, 0)), None, None, ())
    panels = build_panels(rejected, skin, "classic")
    assert "REJECTED" in panels[0].note
    assert len(panels) == 4
