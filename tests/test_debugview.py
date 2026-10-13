"""단계별 시각 샘플 패널 (네트워크 없음)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PIL import Image

from skinmaker import quality as Q
from skinmaker import debugview as DV
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


# --- 처리 과정 패널 (설계 §12): 마스크 패널 + 간단/QA 두 벌 -----------------

def test_panel_mask_overlays_class_colours():
    """SCHP class map을 반투명 색으로 얹는다 — pants 픽셀은 기저색과 달라진다."""
    import numpy as np
    from skinmaker import parsing as P

    img = Image.new("RGB", (120, 160), (30, 30, 30))
    face = Q.FaceBox(40, 20, 40, 50)
    photo = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    seg = np.zeros((160, 120), np.uint8)
    seg[100:140, 40:80] = 6  # Pants
    panel = DV.panel_mask(photo, seg)
    px = panel.image.load()
    # 팬츠는 사진 (40..80,100..140) → 패널은 PANEL_W(360)로 3배 확대 → (120..240, 300..420)
    assert px[180, 360][:3] != (30, 30, 30)  # 팬츠 영역에 마스크 색이 섞였다


def test_steps_sheets_clean_and_full():
    """간단(s0+mask+s1+atlas)과 전체 QA(s0+s1+atlas+uvmap+preview+mask) 두 벌."""
    img = Image.new("RGB", (200, 300), (120, 100, 90))
    face = Q.FaceBox(60, 40, 80, 100)
    photo = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    skin = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    clean, full = DV.steps_sheets(photo, skin, "classic")
    assert clean.width == full.width
    assert full.height >= clean.height  # 전체 QA가 패널이 더 많다


def test_contact_sheet_columns_grid_is_compact():
    """columns>1: 세로 스택 대신 격자 — 인라인 썸네일이 6000px 벽이 되지 않게."""
    img = Image.new("RGB", (200, 300), (120, 100, 90))
    face = Q.FaceBox(60, 40, 80, 100)
    photo = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    panels = build_panels(photo, build_placeholder("classic").image, "classic", which=("s0", "atlas"))
    stacked = contact_sheet(panels)
    grid = contact_sheet(panels, columns=2)
    assert grid.width > stacked.width          # 가로로 펼쳐졌다
    assert grid.height < stacked.height         # 세로로 짧아졌다
    assert grid.width == 2 * PANEL_W + 10       # 2열 + PAD


def test_extract_reuses_provided_seg(monkeypatch):
    """seg를 제공하면 bottom_mask를 다시 부르지 않는다 (파서 2회 비행 방지)."""
    import numpy as np
    from skinmaker import parsing as P
    from skinmaker import colors as CC

    monkeypatch.setenv(P.PARSING_ENV, "1")

    def boom(image):
        raise AssertionError("seg 제공됐는데 bottom_mask가 다시 불렸다")

    monkeypatch.setattr(P, "bottom_mask", boom)
    img = Image.new("RGB", (512, 512), (180, 150, 140))
    face = Q.FaceBox(212, 198, 135, 191)
    photo = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    seg = np.zeros((512, 512), np.uint8)
    seg[300:400, 200:300] = 6
    obs = CC.extract(photo, seg=seg)
    assert obs.lower_body_seen is True


def test_build_panels_skips_mask_without_seg():
    """seg 없으면 mask 패널은 조용히 생략 (CLI/파서-off 경로 무변)."""
    rejected = Q.PhotoInput("t.jpg", Image.new("RGB", (300, 300), (0, 0, 0)), None, None, ())
    panels = build_panels(rejected, build_placeholder("classic").image, "classic", which=DV.PANEL_STRIP)
    assert len(panels) == 2  # s0(reject) + atlas — mask는 seg 없어 생략, s1은 observed 없어 생략
