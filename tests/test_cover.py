"""커버 측정: 색 절대값 없이 상대 비교만으로 동작한다 (합성 이미지, 모델 없음).

증명 방법: 상식적인 색이 아니라 이상한 색(노랑 셔츠 + 회청 피부)에서도
같은 로직으로 맞추면 범용이다. 메시 전용 분기가 없다는 뜻이다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from skinmaker import attributes as A
from skinmaker import colors as C
from skinmaker import render as R
from skinmaker.pose import Joint, PosePoints

# 상식 밖의 색. 절대값 하드코딩이면 여기서 깨진다.
SKIN_RGB = (0.42, 0.50, 0.62)  # 회청 피부
SHIRT_RGB = (0.85, 0.78, 0.12)  # 노랑 셔츠
PANTS_RGB = (0.55, 0.12, 0.45)  # 자주 하의
BG_RGB = (0.10, 0.60, 0.30)  # 초록 배경 (둘 다 아님)

SKIN = C.chromaticity(np.asarray(SKIN_RGB, dtype=np.float32))
SHIRT = C.chromaticity(np.asarray(SHIRT_RGB, dtype=np.float32))
PANTS = C.chromaticity(np.asarray(PANTS_RGB, dtype=np.float32))

H, W = 200, 160


def canvas():
    arr = np.zeros((H, W, 3), dtype=np.float32)
    arr[:, :] = BG_RGB
    return arr


def dot(arr, x, y, color, r=5):
    arr[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1] = color


def arm_pose():
    joints = {
        11: Joint(50, 20), 13: Joint(50, 60), 15: Joint(50, 100),
        12: Joint(110, 20), 14: Joint(110, 60), 16: Joint(110, 100),
    }
    return PosePoints(20, None, None, 80, 40, joints)


def test_short_sleeves_with_weird_colors():
    arr = canvas()
    for x in (50, 110):
        dot(arr, x, 40, SHIRT_RGB)  # 위팔만 셔츠
        dot(arr, x, 60, SKIN_RGB)
        dot(arr, x, 100, SKIN_RGB)
    cov = C.measure_cover(arr, arm_pose(), [SHIRT], SKIN, None)
    assert cov.sleeve_len == "short" and cov.arms_known == 2


def test_long_sleeves_with_weird_colors():
    arr = canvas()
    for x in (50, 110):
        for y in (40, 60, 100):
            dot(arr, x, y, SHIRT_RGB)
    cov = C.measure_cover(arr, arm_pose(), [SHIRT], SKIN, None)
    assert cov.sleeve_len == "long"


def test_three_quarter_sleeves():
    arr = canvas()
    for x in (50, 110):
        dot(arr, x, 40, SHIRT_RGB)
        dot(arr, x, 60, SHIRT_RGB)
        dot(arr, x, 100, SKIN_RGB)
    cov = C.measure_cover(arr, arm_pose(), [SHIRT], SKIN, None)
    assert cov.sleeve_len == "three_quarter"


def test_bare_arms_is_none():
    arr = canvas()
    for x in (50, 110):
        for y in (40, 60, 100):
            dot(arr, x, y, SKIN_RGB)
    cov = C.measure_cover(arr, arm_pose(), [SHIRT], SKIN, None)
    assert cov.sleeve_len == "none"


def test_background_arms_abstain():
    cov = C.measure_cover(canvas(), arm_pose(), [SHIRT], SKIN, None)
    assert cov.sleeve_len is None and cov.arms_known == 0


def leg_pose():
    joints = {
        23: Joint(60, 110), 25: Joint(60, 150), 27: Joint(60, 190),
        24: Joint(100, 110), 26: Joint(100, 150), 28: Joint(100, 190),
    }
    return PosePoints(90, 110, 150, 80, 30, joints)


def test_shorts_thigh_fabric_calf_skin():
    arr = canvas()
    for x in (60, 100):
        dot(arr, x, 130, PANTS_RGB)
        dot(arr, x, 170, SKIN_RGB)
    cov = C.measure_cover(arr, leg_pose(), None, SKIN, PANTS)
    assert cov.bottom_len == "short" and cov.legs_known == 2


def test_pants_full_cover():
    arr = canvas()
    for x in (60, 100):
        dot(arr, x, 130, PANTS_RGB)
        dot(arr, x, 170, PANTS_RGB)
    cov = C.measure_cover(arr, leg_pose(), None, SKIN, PANTS)
    assert cov.bottom_len == "long"


def test_no_pose_abstains():
    cov = C.measure_cover(canvas(), None, [SHIRT], SKIN, PANTS)
    assert cov.sleeve_len is None and cov.bottom_len is None


def _obs_with_cover(sleeve, bottom, bottom_rgb=(60, 68, 80)):
    from skinmaker.colors import ColorSample

    def s(hexv):
        r = int(hexv[1:3], 16)
        g = int(hexv[3:5], 16)
        b = int(hexv[5:7], 16)
        return ColorSample(hexv, 0.5, True, (r, g, b), 100)

    return C.ObservedColors(
        s("#e0ac69"), s("#3a2a1c"), s("#2f6fb5"),
        ColorSample("#000000", 0.5, True, bottom_rgb, 100),
        (1.0, 1.0, 1.0), True, (0.5, 0.3, 0.2),
        cover=C.CoverEstimate(sleeve, bottom, 2, 2),
    )


def test_resolve_uses_cover_when_vlm_missing():
    assert R.resolve_sleeve(A.EMPTY, _obs_with_cover("short", "short")) == "short"
    assert R.resolve_bottom(A.EMPTY, _obs_with_cover("short", "short")) == "shorts"


def test_resolve_long_blue_bottom_is_jeans():
    assert R.resolve_bottom(A.EMPTY, _obs_with_cover(None, "long", (40, 80, 160))) == "jeans"
    assert R.resolve_bottom(A.EMPTY, _obs_with_cover(None, "long", (150, 40, 40))) == "pants"


def test_resolve_vlm_wins_over_cover():
    good = dict(top_garment="tee", bottom_garment="jeans", pattern="plain",
                sleeve_len="long", hair_length="short", hair_bbox=[200, 50, 800, 600])
    attrs = A.validate(good)
    obs = _obs_with_cover("short", "short")
    assert R.resolve_sleeve(attrs, obs) == "long"
    assert R.resolve_bottom(attrs, obs) == "jeans"


def test_resolve_no_cover_falls_back_to_jeans_default():
    """하체 증거도 cover 도 없으면 jeans 기본 (2026-10-28 정책)."""
    obs = _obs_with_cover(None, None)
    assert R.resolve_sleeve(A.EMPTY, obs) == A.DEFAULTS["sleeve_len"]
    assert R.resolve_bottom(A.EMPTY, obs) == "jeans"
