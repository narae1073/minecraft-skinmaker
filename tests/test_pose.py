"""포즈 계층: 어깨/골반 밴드 + 상반신 하의 추론 (모델 없이)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw

from skinmaker import colors as C
from skinmaker import quality as Q
from skinmaker.pose import PosePoints, detect_pose, leg_bands, torso_bands

SIZE = (600, 700)
TORSO = PosePoints(shoulder_y=130, hip_y=220, knee_y=320, mid_x=300, half_w=60)
UPPER = PosePoints(shoulder_y=380, hip_y=None, knee_y=None, mid_x=240, half_w=70)


def test_torso_bands_span_shoulder_to_hip():
    bands = torso_bands(TORSO, SIZE)
    assert len(bands) == 3
    assert bands[0].y >= 130
    assert bands[-1].bottom <= 220 + 4
    assert all(b.x == 240 and b.w == 120 for b in bands)


def test_torso_bands_empty_without_hips():
    assert torso_bands(UPPER, SIZE) == []


def test_leg_bands_span_hip_to_knee():
    bands = leg_bands(TORSO, SIZE)
    assert len(bands) == 2
    assert bands[0].y >= 220
    assert bands[-1].bottom <= 320 + 4


def test_leg_bands_reach_image_bottom_without_knees():
    p = PosePoints(shoulder_y=130, hip_y=220, knee_y=None, mid_x=300, half_w=60)
    bands = leg_bands(p, SIZE)
    assert len(bands) == 2
    assert bands[-1].bottom > 400


def test_leg_bands_empty_for_upper_body():
    """상반신: 골반이 프레임 밖이라 하의 밴드 없음 → MISSING → 추론 경로."""
    assert leg_bands(UPPER, SIZE) == []


def test_detect_pose_returns_none_without_model(monkeypatch, tmp_path):
    monkeypatch.setenv("SKINMAKER_POSE", str(tmp_path / "없음.task"))
    import skinmaker.pose as P

    monkeypatch.setattr(P, "_LANDMARKER", None)
    assert detect_pose(Image.new("RGB", (100, 100))) is None
    monkeypatch.setattr(P, "_LANDMARKER", None)


def striped_shirt():
    img = Image.new("RGB", SIZE, (20, 120, 20))
    d = ImageDraw.Draw(img)
    d.rectangle([240, 130, 360, 220], fill=(180, 30, 30))
    d.rectangle([240, 220, 360, 320], fill=(30, 30, 180))
    return img


def test_extract_prefers_pose_torso_over_face_geometry():
    face = Q.FaceBox(285, 60, 30, 37)
    q = Q.Quality(1.0, face.area, 120.0, 400.0, 100.0, True)
    p = Q.PhotoInput("t.jpg", striped_shirt(), face, q, (), TORSO)
    o = C.extract(p)
    r, g, b = o.top.rgb
    assert r > 100 and b < 90, o.top


def test_extract_upper_body_pose_leaves_bottom_missing():
    img = Image.new("RGB", SIZE, (20, 120, 20))
    face = Q.FaceBox(200, 150, 120, 160)
    q = Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True)
    p = Q.PhotoInput("t.jpg", img, face, q, (), UPPER)
    o = C.extract(p)
    assert o.bottom.missing


def test_extract_without_pose_uses_old_geometry():
    img = Image.new("RGB", SIZE, (140, 115, 102))
    face = Q.FaceBox(200, 150, 120, 160)
    q = Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True)
    p = Q.PhotoInput("t.jpg", img, face, q, ())
    assert p.pose is None
    o = C.extract(p)
    assert not o.top.missing
