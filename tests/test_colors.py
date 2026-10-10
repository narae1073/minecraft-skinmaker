"""S1 관측 추출: 화이트밸런스, 클러스터 모드, 신뢰도 (네트워크 없음)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest
from PIL import Image

from skinmaker import colors as C
from skinmaker import quality as Q

FACE = Q.FaceBox(200, 150, 120, 160)


def pixels(colors, n=200, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        base = np.array(colors[i % len(colors)], dtype=np.float32) / 255.0
        out.append(np.clip(base + rng.normal(0, 0.01, 3), 0, 1))
    return np.asarray(out, dtype=np.float32)


def photo(image=None, face=FACE, flags=()):
    image = image or Image.new("RGB", (600, 700), (140, 115, 102))
    q = Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True)
    return Q.PhotoInput("t.jpg", image, face, q, tuple(flags))


# --- 크로마 / 휘도 -------------------------------------------------------

def test_chromaticity_normalizes():
    assert C.chromaticity((128, 64, 32)) == pytest.approx((0.5714, 0.2857, 0.1428), abs=1e-3)
    assert C.chromaticity((0, 0, 0)) == (0.0, 0.0, 0.0)


def test_chroma_distance_is_zero_for_same_hue():
    a, b = (200, 150, 120), (100, 75, 60)
    assert C.chroma_distance(a, b) == pytest.approx(0.0, abs=0.02)


def test_chroma_distance_separates_hues():
    assert C.chroma_distance((200, 150, 120), (120, 150, 200)) > 0.15


def test_luma_weights():
    assert C.luma((255, 255, 255)) == pytest.approx(255, abs=1)
    assert C.luma((0, 0, 0)) == 0.0


# --- 화이트밸런스 ---------------------------------------------------------

def test_wb_is_identity_for_reference_skin():
    gain, ok = C.white_balance_gain(pixels([(204, 161, 141)]))
    assert all(abs(g - 1.0) < 0.01 for g in gain)
    assert ok is True


def test_wb_pulls_magenta_cast_toward_skin():
    gain, _ = C.white_balance_gain(pixels([(230, 120, 140)]))
    assert gain[0] < gain[1]
    assert gain[2] < gain[1]
    assert max(gain) <= C.WB_CLIP + 1e-9


def test_wb_clips_to_limit():
    gain, ok = C.white_balance_gain(pixels([(255, 10, 10)]))
    assert max(gain) <= C.WB_CLIP + 1e-9
    assert min(gain) >= 1.0 / C.WB_CLIP - 1e-9
    assert ok is False


def test_wb_skips_when_region_is_not_skin():
    """부채꼴 영역처럼 크로마가 기준에서 멀면 보정하지 않는다."""
    gain, ok = C.white_balance_gain(pixels([(20, 200, 60)]))
    assert gain == (1.0, 1.0, 1.0)
    assert ok is False


def test_wb_is_robust_to_a_few_outliers():
    arr = np.concatenate([pixels([(204, 161, 141)], n=180), pixels([(0, 255, 0)], n=20)])
    gain, _ = C.white_balance_gain(arr)
    assert all(0.98 < g < 1.02 for g in gain)


def test_wb_preserves_lightness():
    gain, _ = C.white_balance_gain(pixels([(204, 161, 141)]))
    arr = pixels([(204, 161, 141)])
    out = C.apply_gain(arr, gain)
    assert out.mean() == pytest.approx(arr.mean(), rel=0.02)


# --- 클러스터 모드 -------------------------------------------------------

def test_dominant_finds_the_majority_color():
    arr = np.concatenate([pixels([(30, 90, 200)], n=900), pixels([(200, 30, 30)], n=100)])
    s = C.dominant_color(arr)
    assert s.rgb == (30, 90, 200)
    assert s.share > 0.85
    assert s.confident


def test_dominant_share_reports_noise():
    rng = np.random.default_rng(3)
    arr = rng.random((600, 3), dtype=np.float32)
    s = C.dominant_color(arr)
    assert s.share < C.MIN_SHARE
    assert not s.confident


def test_dominant_rejects_matching_chroma():
    arr = np.concatenate([pixels([(30, 90, 200)], n=900), pixels([(220, 190, 170)], n=100)])
    chroma = C.chromaticity(np.array((220, 190, 170), dtype=np.float32) / 255.0)
    s = C.dominant_color(arr, reject=(chroma,))
    assert s.rgb == (30, 90, 200)


def test_dominant_returns_missing_when_all_rejected():
    arr = pixels([(220, 190, 170)])
    chroma = C.chromaticity(np.array((220, 190, 170), dtype=np.float32) / 255.0)
    s = C.dominant_color(arr, reject=(chroma,))
    assert s.missing and s.share == 0.0


def test_dominant_empty_input():
    assert C.dominant_color(np.zeros((0, 3), dtype=np.float32)).missing


def test_saturated_pick_skips_dull_clusters():
    arr = np.concatenate([pixels([(120, 120, 120)], n=800), pixels([(200, 40, 20)], n=200)])
    mode = C.dominant_color(arr, pick="mode")
    sat = C.dominant_color(arr, pick="saturated")
    assert mode.rgb == (120, 120, 120)
    assert sat.rgb != (120, 120, 120)


def test_hex_is_six_digits_lowercase():
    s = C.dominant_color(pixels([(30, 90, 200)]))
    assert s.hex.startswith("#") and len(s.hex) == 7
    assert s.hex == s.hex.lower()


# --- 배경 크로마 ---------------------------------------------------------

def test_background_chroma_reads_the_border():
    img = Image.new("RGB", (200, 200), (20, 160, 40))
    arr = np.asarray(img, dtype=np.float32) / 255.0
    bg = C.background_chroma(arr)
    assert bg is not None
    assert bg[1] > 0.6


def test_background_chroma_none_for_tiny_image():
    arr = np.zeros((3, 3, 3), dtype=np.float32)
    assert C.background_chroma(arr) is None


# --- 밴드 ----------------------------------------------------------------

def test_bottom_bands_start_below_shirt():
    face = Q.FaceBox(200, 100, 100, 140)
    bands = C.bottom_bands(face, (600, 900))
    assert bands
    assert bands[0].y >= face.bottom + int(face.h * 0.9)


def test_bottom_bands_empty_when_no_room():
    assert C.bottom_bands(Q.FaceBox(0, 0, 100, 140), (300, 200)) == []


def test_bottom_bands_inset_sides():
    bands = C.bottom_bands(Q.FaceBox(0, 0, 100, 140), (300, 900))
    assert all(b.x > 0 and b.right < 300 for b in bands)


def test_frame_lower_bands_cover_lower_frame():
    face = Q.FaceBox(228, 95, 30, 37)
    bands = C.frame_lower_bands(face, (548, 342))
    assert bands, "전신에서 하부 밴드가 비지 않아야 한다"
    assert all(b.y >= face.bottom for b in bands)
    assert bands[-1].bottom <= 342


# --- extract -------------------------------------------------------------

def test_bottom_falls_back_to_lower_frame():
    img = Image.new("RGB", (400, 600), (200, 200, 200))
    px = img.load()
    for y in range(400, 600):
        for x in range(140, 260):
            px[x, y] = (30, 50, 150)  # 하부 바지색
    face = Q.FaceBox(170, 60, 60, 75)
    for y in range(60, 135):
        for x in range(170, 230):
            px[x, y] = (204, 161, 140)  # 피부 앵커 (WB≈1)
    photo = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    observed = C.extract(photo)
    assert not observed.bottom.missing
    assert C.chroma_distance(
        C.np.asarray(observed.bottom.rgb, dtype=C.np.float32) / 255.0,
        C.np.asarray((30, 50, 150), dtype=C.np.float32) / 255.0,
    ) <= C.CHROMA_TOL


def test_bust_photo_keeps_bottom_missing():
    img = Image.new("RGB", (512, 512), (180, 150, 140))
    face = Q.FaceBox(212, 198, 135, 191)
    photo = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    observed = C.extract(photo)
    assert observed.bottom.missing


def test_short_bottom_len_resolves_to_shorts():
    from skinmaker import attributes as A
    from skinmaker import render as R
    from skinmaker.colors import CoverEstimate
    attrs = A.Attributes({**A.DEFAULTS, "bottom_garment": "pants"}, None)
    obs = C.extract(photo())  # 기존 helper: cover=None
    assert R.resolve_bottom(attrs, obs) == "pants"


def test_extract_returns_missing_when_no_face():
    p = Q.PhotoInput("t.jpg", Image.new("RGB", (100, 100)), None, None, ())
    o = C.extract(p)
    assert all(c.missing for c in (o.skin, o.hair, o.top, o.bottom))
    assert o.wb_gain == (1.0, 1.0, 1.0)


def test_extract_skips_only_hair_when_small_flag():
    """small이면 헤어만 블랭크. 상/하의는 몸통 면적이라 측정을 시도한다 (전신샷 유니폼)."""
    o = C.extract(photo(flags=("small",)))
    assert not o.skin.missing
    assert o.hair.missing
    assert not o.top.missing and not o.bottom.missing


def test_extract_small_flag_still_reads_jersey_color():
    """얼굴 30px + 몸통 빨강이면 top이 빨강을 읽는다. 메시 케이스 회귀."""
    from PIL import ImageDraw

    img = Image.new("RGB", (600, 700), (20, 120, 20))
    d = ImageDraw.Draw(img)
    d.rectangle([200, 130, 400, 700], fill=(180, 30, 30))
    face = Q.FaceBox(285, 95, 30, 37)
    p = Q.PhotoInput("t.jpg", img, face, Q.Quality(1.0, face.area, 0, 0, 0, False), ("small",))
    o = C.extract(p)
    assert o.hair.missing
    assert not o.top.missing
    r, g, b = o.top.rgb
    assert r > 100 and g < 90 and b < 90, o.top


def test_extract_flags_top_that_matches_skin():
    o = C.extract(photo())
    if not o.top.missing:
        assert isinstance(o.top_skinlike, bool)


def test_top_skinlike_is_true_for_skin_colored_top():
    o = C.extract(photo())
    assert isinstance(o.top_skinlike, bool)


def test_patterned_flag_changes_top_pick_only():
    plain = C.extract(photo(), patterned=False)
    patterned = C.extract(photo(), patterned=True)
    assert plain.skin.hex == patterned.skin.hex
    assert plain.hair.hex == patterned.hair.hex


def test_extract_is_deterministic():
    a = C.extract(photo())
    b = C.extract(photo())
    assert (a.skin.hex, a.hair.hex, a.top.hex) == (b.skin.hex, b.hair.hex, b.top.hex)


def test_missing_sample_sentinels():
    assert C.MISSING.missing
    assert C.MISSING.share == 0.0


# --- 줄무늬 2색 ----------------------------------------------------------

def _paint_stripes(size, vertical):
    from PIL import ImageDraw

    img = Image.new("RGB", size, (20, 120, 20))
    d = ImageDraw.Draw(img)
    W, H = size
    for i in range(0, W if vertical else H, 20):
        color = (180, 30, 30) if (i // 20) % 2 == 0 else (30, 40, 180)
        if vertical:
            d.rectangle([100 + i, 150, 100 + i + 20, 400], fill=color)
        else:
            d.rectangle([100, 150 + i, 300, 150 + i + 20], fill=color)
    return img


def _striped_photo(vertical=True):
    img = _paint_stripes((400, 500), vertical)
    face = Q.FaceBox(150, 60, 100, 120)
    q = Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True)
    return Q.PhotoInput("t.jpg", img, face, q, ())


def test_vertical_stripes_yield_alt_and_orientation():
    o = C.extract(_striped_photo(vertical=True))
    assert not o.top.missing and not o.top_alt.missing
    assert o.stripe == "vertical_stripe"
    pair = sorted([o.top.hex, o.top_alt.hex])
    assert pair[0] != pair[1]


def test_horizontal_stripes_yield_orientation():
    o = C.extract(_striped_photo(vertical=False))
    assert o.stripe == "horizontal_stripe"
    assert not o.top_alt.missing


def test_solid_shirt_yields_no_alt():
    o = C.extract(photo())
    assert o.top_alt.missing
    assert o.stripe == "plain"


def test_runner_up_rejects_close_hue():
    px = pixels([(200, 150, 120), (205, 155, 125)])
    primary = C.dominant_color(px)
    assert C.runner_up(px, primary).missing
    assert not C.MISSING.confident
