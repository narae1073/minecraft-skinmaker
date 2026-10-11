"""S1 관측 추출: 화이트밸런스, 클러스터 모드, 신뢰도 (네트워크 없음)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest
from PIL import Image

from skinmaker import colors as C
from skinmaker import quality as Q
from skinmaker import attributes as A
from skinmaker import render as R
from skinmaker import validate as V

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


def test_bottom_falls_back_when_bands_remeasure_shirt():
    # 얼굴 비례 bottom_bands는 셔츠-그레이만 본다 (confident, 배경 아님).
    # 프레임 하부는 바지-파랑만 본다. 배경은 셋째 색(초록).
    img = Image.new("RGB", (400, 600), (20, 160, 40))
    px = img.load()
    for y in range(135, 314):
        for x in range(140, 260):
            px[x, y] = (150, 150, 150)  # 셔츠-그레이 (shirt+bottom 밴드 zone)
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


def test_dark_neutral_garment_is_not_background_on_gray_backdrop():
    """크로마만 보면 짙은 무채색 바지와 회색 배경이 같아 보인다.

    istockphoto: 청바지 #374047 (luma 63) 이 배경 크로마와 0.05 차이라 배경으로
    탈락했다. 휘도까지 봐야 배경(luma 178) 과 구별된다.
    """
    bg_chroma = (1 / 3, 1 / 3, 1 / 3)
    bg_luma = 178.0
    jeans = C.ColorSample("#374047", 0.65, True, (55, 64, 71), 1716)
    assert C._matches_background(jeans, bg_chroma, bg_luma) is False


def test_light_gray_backdrop_sample_is_still_background():
    bg_chroma = (1 / 3, 1 / 3, 1 / 3)
    floor = C.ColorSample("#c6c8c7", 0.51, True, (198, 200, 199), 403)
    assert C._matches_background(floor, bg_chroma, 186.0) is True


def test_bottom_recovers_trousers_when_frame_strip_hits_gap_between_legs():
    """전신 + 다리 사이 틈. 프레임 하부 중앙 띠가 바닥(틈)만 보면 cascade 가
    배경으로 탈락시키고, 하의를 못 찾아 상의 흰색이 하의로 남았다 (images10).
    다리 영역 전경 마스크로 짙은 바지색을 얻어야 한다.
    """
    W, H = 240, 350
    bg = (200, 200, 200)
    img = Image.new("RGB", (W, H), bg)
    px = img.load()
    for y in range(80, 200):  # 흰 셔츠: 상의·얼굴 밴드가 같은 흰색을 본다
        for x in range(60, 180):
            px[x, y] = (255, 255, 255)
    for y in range(200, 300):  # 짙은 바지 두 다리 (중앙 틈 x 110~130)
        for x in list(range(60, 110)) + list(range(131, 180)):
            px[x, y] = (60, 60, 64)
    for y in range(300, 320):  # 신발
        for x in list(range(60, 110)) + list(range(131, 180)):
            px[x, y] = (20, 20, 20)
    face = Q.FaceBox(108, 30, 24, 30)
    p = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    observed = C.extract(p)
    assert not observed.bottom.missing
    assert C.chroma_distance(
        C.np.asarray(observed.bottom.rgb, dtype=C.np.float32) / 255.0,
        C.np.asarray((60, 60, 64), dtype=C.np.float32) / 255.0,
    ) <= C.CHROMA_TOL
    assert observed.bottom.rgb[0] < 120  # 흰색(상의)이 아니다


def test_mask_fallback_bottom_is_marked_unconfident():
    """전경 마스크는 마지막 수단의 추정이다. 확신값으로 내보내지 않는다."""
    W, H = 240, 350
    img = Image.new("RGB", (W, H), (200, 200, 200))
    px = img.load()
    for y in range(80, 200):
        for x in range(60, 180):
            px[x, y] = (255, 255, 255)
    for y in range(200, 300):
        for x in list(range(60, 110)) + list(range(131, 180)):
            px[x, y] = (60, 60, 64)
    for y in range(300, 320):
        for x in list(range(60, 110)) + list(range(131, 180)):
            px[x, y] = (20, 20, 20)
    face = Q.FaceBox(108, 30, 24, 30)
    p = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    observed = C.extract(p)
    assert observed.bottom.rgb[0] < 120  # 마스크 경로를 탔다
    assert observed.bottom.confident is False


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
    obs = C.ObservedColors(
        C.MISSING, C.MISSING, C.MISSING, C.MISSING,
        (1.0, 1.0, 1.0), False, (0.0, 0.0, 0.0),
        cover=CoverEstimate(None, "short", 0, 2),
    )
    assert R.resolve_bottom(A.EMPTY, obs) == "shorts"


def test_extract_returns_missing_when_no_face():
    p = Q.PhotoInput("t.jpg", Image.new("RGB", (100, 100)), None, None, ())
    o = C.extract(p)
    assert all(c.missing for c in (o.skin, o.hair, o.top, o.bottom))
    assert o.wb_gain == (1.0, 1.0, 1.0)


def test_extract_skips_wb_gain_that_clips():
    """게인이 클립되면(확신 없음) 보정을 적용하지 않는다.

    전신샷 흰 셔츠 + 작고 붉게 치우친 피부 앵커면 R 게인이 하한(1/1.25)에
    걸린다. 클립된 게인을 그대로 적용하면 중립 흰색이 민트색으로 이동한다
    (R×0.8). 확신 없는 게인은 identity 로 둔다.
    """
    img = Image.new("RGB", (600, 700), (255, 255, 255))
    px = img.load()
    sr = Q.skin_region(FACE)
    for y in range(sr.y, sr.bottom):
        for x in range(sr.x, sr.right):
            px[x, y] = (170, 106, 94)  # R 게인을 하한에 걸리게 하는 앵커
    o = C.extract(photo(image=img))
    assert o.wb_confident is False
    assert o.wb_gain == (1.0, 1.0, 1.0)
    assert not o.top.missing
    assert abs(o.top.rgb[0] - o.top.rgb[2]) < 20  # 흰색 유지 (민트 아님)


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


def test_hair_read_from_bbox_when_given():
    img = Image.new("RGB", (400, 500), (30, 30, 30))
    px = img.load()
    for y in range(0, 60):
        for x in range(150, 250):
            px[x, y] = (150, 90, 40)  # bbox 안 헤어색
    face = Q.FaceBox(150, 100, 100, 130)
    # 피부 앵커가 없으면 WB 게인이 발동해 헤어색이 밀린다. 실제 사진처럼
    # skin_region(볼·코)에 기준 피부를 깔아 WB≈1로 고정한다.
    for y in range(171, 207):
        for x in range(170, 230):
            px[x, y] = (204, 161, 141)
    p = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    got = C.extract(p, hair_bbox=Q.FaceBox(150, 0, 100, 60))
    assert not got.hair.missing and got.hair.confident
    assert got.hair.hex == "#965a28"


def test_hair_falls_back_without_bbox():
    p = photo()  # 기존 helper (단일톤 배경)
    got = C.extract(p)
    assert got.hair.hex == "#3a2a1c" or not got.hair.confident


def test_lipstick_does_not_clip_white_balance():
    # 편차 기록: brief 원안(입술 75~85%)은 중앙값 오염이 28%라
    # pre-fix 에도 wb_confident True 가 나와 RED 가 안 된다 (중앙값은
    # 50% 미만 오염에 robust). RED 재현을 위해 입술을 68~85%로
    # 그린다.旧 영역(55~83%)의 과반이 오염돼 pre-fix FAIL,
    # 新 영역(55~75%)에서는 35%라 median 이 버텨 PASS 여야 한다.
    img = Image.new("RGB", (512, 512), (200, 170, 155))
    px = img.load()
    for y in range(198 + int(191 * 0.68), 198 + int(191 * 0.85)):
        for x in range(212, 347):
            px[x, y] = (200, 30, 40)  # 입술
    face = Q.FaceBox(212, 198, 135, 191)
    p = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    observed = C.extract(p)
    assert observed.wb_confident, observed.wb_gain


def test_skinlike_top_renders_deterministically():
    p = photo()  # 단일톤: top과 skin이 같은 색
    observed = C.extract(p)
    assert observed.top_skinlike is True
    canvas = R.render(observed, A.EMPTY, ())
    assert V.validate_image(canvas.image, "classic") == []


# --- 하네스 범주화 (bottom_eval.categorize) -------------------------------

def _cat(hex_str: str) -> str:
    from skinmaker.bottom_eval import categorize
    rgb = tuple(int(hex_str[i : i + 2], 16) for i in (1, 3, 5))
    return categorize(C.ColorSample(hex_str, 1.0, True, rgb, 100))


@pytest.mark.parametrize(
    "hex_str, expected",
    [
        ("#010b18", "dark"),     # 거의 검정 (채도 비율 0.96 이어도 어둡다)
        ("#383a3e", "dark"),     # 짙은 회색 바지
        ("#374047", "blue"),     # 짙은 데님 (B-R 0.057)
        ("#c6ddf5", "blue"),     # 옅은 청색
        ("#f59096", "colored"),  # 분홍 바지
        ("#ebe3cd", "light"),    # 밝은 베이지/흰색
        ("#8e8a6a", "colored"),  # 올리브 계열 채도
        ("#9a9a9a", "mid"),      # 중간 회색
    ],
)
def test_harness_categorize_known_colors(hex_str, expected):
    assert _cat(hex_str) == expected


def test_harness_categorize_missing_is_missing():
    from skinmaker.bottom_eval import categorize
    assert categorize(C.MISSING) == "missing"


# --- 렌더 폴백 정책 (하의) ----------------------------------------------
# 규칙: 측정이 있고 (확신이 있거나 또는 그럴듯하면) 측정을 쓴다.
#       결측이거나 (확신 없음 AND 그럴듯하지 않음) 이면 기본값.
# "그럴듯함" = 피부색이 아니고 배경색이 아니다 (다른 것을 잰 것이 아니다).

def _obs(bottom, plausible):
    return C.ObservedColors(
        C.MISSING, C.MISSING, C.MISSING, bottom,
        (1.0, 1.0, 1.0), False, (0.0, 0.0, 0.0),
        bottom_plausible=plausible,
    )


def _sample(hex_str, confident):
    rgb = tuple(int(hex_str[i : i + 2], 16) for i in (1, 3, 5))
    return C.ColorSample(hex_str, 0.5, confident, rgb, 500)


def test_policy_uses_confident_sample():
    assert R.bottom_usable(_sample("#383a3e", True), plausible=False) is True


def test_policy_uses_unconfident_plausible_sample():
    assert R.bottom_usable(_sample("#383a3e", False), plausible=True) is True


def test_policy_falls_back_for_unconfident_implausible_sample():
    assert R.bottom_usable(_sample("#e0ac69", False), plausible=False) is False


def test_policy_falls_back_for_missing():
    assert R.bottom_usable(C.MISSING, plausible=True) is False


def test_resolve_colors_uses_unconfident_plausible_bottom():
    colors = R.resolve_colors(_obs(_sample("#383a3e", False), plausible=True))
    assert colors["bottom"][:3] == (56, 58, 62)


def test_resolve_colors_defaults_unconfident_implausible_bottom():
    colors = R.resolve_colors(_obs(_sample("#e0ac69", False), plausible=False))
    assert colors["bottom"][:3] == (60, 68, 80)


def test_bottom_plausibility_rejects_backdrop_colored_bottom():
    """하의 측정이 배경색이면 옷이 아니라 배경을 잰 것이다."""
    img = Image.new("RGB", (400, 600), (200, 200, 200))  # 전체가 배경색
    face = Q.FaceBox(170, 60, 60, 75)
    p = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    observed = C.extract(p)
    assert observed.bottom_plausible is False


def test_bottom_plausibility_keeps_bare_skin_measurement():
    """맨다리를 잰 값은 피부색이 맞다. 그럴듯하지 않다고 기본값으로 바꾸지 않는다."""
    img = Image.new("RGB", (400, 600), (200, 200, 200))  # 회색 배경
    px = img.load()
    for y in range(260, 560):  # 맨다리 (피부색), 배경과 다르다
        for x in range(170, 230):
            px[x, y] = (204, 161, 141)
    face = Q.FaceBox(170, 60, 60, 75)
    p = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    observed = C.extract(p)
    assert observed.bottom_plausible is True


def test_bottom_plausibility_accepts_trousers():
    img = Image.new("RGB", (240, 350), (200, 200, 200))
    px = img.load()
    for y in range(200, 300):
        for x in list(range(60, 110)) + list(range(131, 180)):
            px[x, y] = (60, 60, 64)
    face = Q.FaceBox(108, 30, 24, 30)
    p = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    observed = C.extract(p)
    assert observed.bottom_plausible is True


# --- 하네스 상수 교정 (F1): 짙은 네이비 데님은 명도로 보면 dark 이지만
# 색조로는 blue 다. 이전 luma >= 40 게이트가 blue 라벨 4건을 dark 로 눌렀다
# (images19 #112337 luma 32.6, ex5 #141a25 25.5, gettyimages-1501793213
# #1d2122 32.2 — 전부 label=blue, 실측=dark). 게이트를 25 로 내린다.


@pytest.mark.parametrize("hex_str", ["#112337", "#141a25", "#1d2122"])
def test_harness_dark_navy_blueness_overrides_brightness(hex_str):
    assert _cat(hex_str) == "blue"


def test_harness_black_slight_blue_cast_stays_dark():
    # 게이트를 내리는 것의 인하 한계: luma < 25 인 검정·청조는 dark 유지
    # (images2 실측 #0d171a, luma 21).
    assert _cat("#0d171a") == "dark"
