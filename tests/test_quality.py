"""S0 입력 판정: 품질 지표, 저하 계획, 영역 기하 (네트워크 없음)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest
from PIL import Image

from skinmaker import quality as Q
from skinmaker.measure import analyze, collect, report

FIXTURES = Path(__file__).resolve().parent.parent / "out" / "s0_photos"


def solid(color, size=(64, 64)) -> Image.Image:
    return Image.new("RGB", size, color)


def gradient(size=(64, 64), seed=0) -> Image.Image:
    rng = np.random.default_rng(seed)
    arr = np.linspace(0, 255, size[0], dtype=np.float32)
    arr = np.tile(arr, (size[1], 1))
    return Image.fromarray(np.stack([arr, arr, arr], axis=-1).astype(np.uint8))


def noise(size=(64, 64), seed=1) -> Image.Image:
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 256, (*size, 3), dtype=np.uint8))


BOX = Q.FaceBox(0, 0, 64, 64)


# --- 지표 수학 -----------------------------------------------------------

def test_brightness_of_flat_images():
    assert Q.measure_quality(solid((128, 128, 128)), BOX).brightness == pytest.approx(128, abs=1)
    assert Q.measure_quality(solid((255, 255, 255)), BOX).brightness == pytest.approx(255, abs=1)
    assert Q.measure_quality(solid((0, 0, 0)), BOX).brightness == pytest.approx(0, abs=1)


def test_sharpness_of_flat_image_is_zero_and_noise_is_high():
    assert Q.measure_quality(solid((128, 128, 128)), BOX).sharpness == pytest.approx(0, abs=1)
    assert Q.measure_quality(noise(), BOX).sharpness > 100


def test_saturation_of_solid_primaries():
    assert Q.measure_quality(solid((255, 0, 0)), BOX).saturation == pytest.approx(255, abs=2)
    assert Q.measure_quality(solid((255, 255, 255)), BOX).saturation == pytest.approx(0, abs=2)
    assert Q.measure_quality(solid((128, 128, 128)), BOX).saturation == pytest.approx(0, abs=2)


def test_gradient_is_mid_sharpness():
    g = Q.measure_quality(gradient(), BOX)
    assert 0 < g.sharpness < 100


def test_tiny_face_is_unmeasured():
    q = Q.measure_quality(solid((120, 120, 120)), Q.FaceBox(0, 0, 10, 10))
    assert q.measured is False
    assert Q.plan_degradation(q) == ("small",)


def test_quality_keeps_face_px_and_score():
    q = Q.measure_quality(solid((120, 120, 120)), Q.FaceBox(2, 3, 40, 20), score=0.83)
    assert q.face_px == 800
    assert q.detection_score == pytest.approx(0.83)


# --- 저하 계획 -----------------------------------------------------------

def make_q(**kw) -> Q.Quality:
    base = dict(detection_score=1.0, face_px=5000, brightness=128.0, sharpness=800.0, saturation=120.0, measured=True)
    base.update(kw)
    return Q.Quality(**base)


def test_clean_photo_has_no_flags():
    assert Q.plan_degradation(make_q()) == ()


def test_blur_flag_boundary():
    assert Q.plan_degradation(make_q(sharpness=Q.SHARPNESS_BLUR - 1)) == ("blur",)
    assert Q.plan_degradation(make_q(sharpness=Q.SHARPNESS_BLUR)) == ()
    assert Q.plan_degradation(make_q(sharpness=Q.SHARPNESS_BLUR + 1)) == ()


def test_dark_and_bright_are_mutually_exclusive():
    assert Q.plan_degradation(make_q(brightness=Q.BRIGHTNESS_DARK - 1)) == ("dark",)
    assert Q.plan_degradation(make_q(brightness=Q.BRIGHTNESS_BRIGHT + 1)) == ("bright",)
    both = Q.plan_degradation(make_q(brightness=Q.BRIGHTNESS_BRIGHT + 1, sharpness=1.0))
    assert both == ("blur", "bright")


def test_small_face_flag_boundary():
    assert Q.plan_degradation(make_q(face_px=Q.FACE_PX_SMALL - 1)) == ("small",)
    assert Q.plan_degradation(make_q(face_px=Q.FACE_PX_SMALL)) == ()


def test_flat_saturation_flag():
    assert Q.plan_degradation(make_q(saturation=Q.SATURATION_DARK - 1)) == ("flat",)
    assert Q.plan_degradation(make_q(saturation=Q.SATURATION_DARK)) == ()


def test_multiple_flags_stack_in_fixed_order():
    q = make_q(brightness=10.0, sharpness=5.0, face_px=10, saturation=1.0)
    assert Q.plan_degradation(q) == ("blur", "dark", "small", "flat")


# --- 영역 기하 -----------------------------------------------------------

def test_skin_region_avoids_eyes_and_mouth():
    face = Q.FaceBox(100, 100, 100, 100)
    r = Q.skin_region(face)
    assert (r.x, r.right) == (120, 180)
    assert r.y == 155 and r.bottom == 183
    assert r.y >= face.y + int(face.h * 0.55)
    assert r.bottom <= face.bottom


def test_hair_region_extends_beyond_face_box():
    """긴머리는 얼굴 박스 밖에 있으므로 사방으로 확장해야 한다."""
    face = Q.FaceBox(50, 60, 90, 90)
    r = Q.hair_region(face)
    assert r.y < face.y
    assert r.x < face.x and r.right > face.right
    assert r.bottom <= face.y + int(face.h * 0.80)


def test_clip_to_keeps_overlapping_part():
    clipped = Q.clip_to(Q.FaceBox(-20, -10, 100, 100), (200, 200))
    assert clipped == Q.FaceBox(0, 0, 80, 90)


def test_clip_to_returns_none_when_fully_outside():
    assert Q.clip_to(Q.FaceBox(300, 300, 50, 50), (200, 200)) is None
    assert Q.clip_to(Q.FaceBox(0, 0, 1, 1), (200, 200)) is None


def test_clip_to_on_real_hair_region_stays_valid():
    face = Q.FaceBox(0, 0, 40, 40)
    clipped = Q.clip_to(Q.hair_region(face), (60, 60))
    assert clipped is not None
    assert clipped.x >= 0 and clipped.y >= 0
    assert clipped.right <= 60 and clipped.bottom <= 60


def test_hair_region_never_zero_height():
    r = Q.hair_region(Q.FaceBox(0, 0, 8, 3))
    assert r.h >= 1


def test_shirt_bands_are_below_face_and_centered():
    face = Q.FaceBox(100, 50, 100, 100)
    bands = Q.shirt_bands(face, (400, 400))
    assert len(bands) == 3
    for b in bands:
        assert b.y >= face.bottom
        assert b.x > face.x
        assert b.right <= 400
        assert b.bottom <= 400
        assert b.w == 70


def test_shirt_bands_clamp_last_band_to_image_bottom():
    face = Q.FaceBox(0, 0, 100, 100)
    bands = Q.shirt_bands(face, (200, 220))
    assert len(bands) == 3
    assert bands[-1].bottom == 220
    assert bands[-1].h < bands[0].h
    for b in bands:
        assert b.bottom <= 220


def test_shirt_bands_empty_when_no_room():
    assert Q.shirt_bands(Q.FaceBox(0, 0, 100, 100), (200, 102)) == []


def test_shirt_bands_respect_small_image_width():
    bands = Q.shirt_bands(Q.FaceBox(0, 0, 20, 20), (30, 200))
    for b in bands:
        assert b.right <= 30


# --- 배치 계측 -----------------------------------------------------------

def test_collect_filters_non_images(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "b.PNG").write_bytes(b"x")
    (tmp_path / "c.txt").write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "d.jpeg").write_bytes(b"x")
    names = [p.name for p in collect(tmp_path)]
    assert sorted(names) == ["a.jpg", "b.PNG", "d.jpeg"]


def test_analyze_survives_unreadable_file(tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not an image")
    results = analyze([bad], 0.6)
    assert results[0].rejected
    assert results[0].degrade[0].startswith("error:")


def test_report_handles_empty(tmp_path):
    assert "이미지 없음" in report(analyze([], 0.6))


def test_report_counts_and_percentages(tmp_path):
    from skinmaker.measure import PhotoInput

    ok = PhotoInput("a.jpg", None, Q.FaceBox(0, 0, 80, 80), make_q(), ())
    rej = PhotoInput("b.jpg", None, None, None, ())
    out = report([ok, rej, rej, rej], show=0)
    assert "거절율 75.0%" in out
    assert "검출 성공 1" in out


# --- 실사진 종단간 ( 픽스처가 있을 때만 ) ----------------------------------

def test_yunet_model_loads():
    assert Q.yunet_path().exists(), "YuNet 모델 없음. README의 assets 설치 참고"
    assert Q._detector() is not None


@pytest.mark.skipif(not (FIXTURES / "lena.jpg").exists(), reason="픽스처 없음")
def test_detects_real_face():
    result = Q.inspect(FIXTURES / "lena.jpg")
    assert not result.rejected
    assert result.face.w > 60
    assert result.quality.measured


@pytest.mark.skipif(not (FIXTURES / "messi5.jpg").exists(), reason="픽스처 없음")
def test_flags_small_face_in_wide_shot():
    result = Q.inspect(FIXTURES / "messi5.jpg")
    assert not result.rejected
    assert "small" in result.degrade
