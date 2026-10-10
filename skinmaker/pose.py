"""전신/상반신용 관절 추정: 어깨·골반·무릎으로 샘플 밴드를 놓는다.

YuNet(얼굴)과 달리 포즈는 선택 계층이다. 모델·패키지가 없으면 None을
돌려주고 호출자는 얼굴 비례 밴드(기존 기하)로 폴백한다. 절대 예외를 던지지
않는다. 서있기/걷기까지가 범위고 과한 액션샷은 보장하지 않는다.

상반신 판정: 골반이 프레임 밖이거나 presence 낮으면 하반신 없음.
하의 밴드가 비어 하의색 MISSING → S3 기본값 + S2 none 규칙이 추론을 맡는다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .quality import FaceBox, clip_to

ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"
POSE_FILE = "pose_landmarker_lite.task"
POSE_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)

# BlazePose 인덱스
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_ELBOW, RIGHT_ELBOW = 13, 14
LEFT_WRIST, RIGHT_WRIST = 15, 16
LEFT_HIP, RIGHT_HIP = 23, 24
LEFT_KNEE, RIGHT_KNEE = 25, 26
LEFT_ANKLE, RIGHT_ANKLE = 27, 28
LEFT_HEEL, RIGHT_HEEL = 29, 30

ARMS = ((LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST), (RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST))
LEGS = ((LEFT_HIP, LEFT_KNEE, LEFT_ANKLE), (RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE))
# 무릎 대용: 25/26이 흐리면 골반-발목 중점으로 역산한다.
HEELS = (LEFT_HEEL, RIGHT_HEEL)

PRESENCE_MIN = 0.30


def pose_path() -> Path:
    return Path(os.environ.get("SKINMAKER_POSE") or (ASSET_DIR / POSE_FILE))


@dataclass(frozen=True)
class Joint:
    x: int
    y: int


@dataclass(frozen=True)
class PosePoints:
    shoulder_y: int
    hip_y: int | None
    knee_y: int | None
    mid_x: int
    half_w: int
    joints: dict[int, Joint] = field(default_factory=dict)

    def joint(self, idx: int) -> Joint | None:
        return self.joints.get(idx)

    @property
    def has_torso(self) -> bool:
        return self.hip_y is not None and self.hip_y > self.shoulder_y + 4

    @property
    def has_legs(self) -> bool:
        return self.hip_y is not None

    def arm_points(self) -> list[tuple[Joint, Joint, Joint]]:
        """(어깨, 팔꿈치, 손목) 쌍. 셋 다 있어야 한 팔로 친다."""
        out = []
        for sh, el, wr in ARMS:
            pts = (self.joint(sh), self.joint(el), self.joint(wr))
            if all(p is not None for p in pts):
                out.append((pts[0], pts[1], pts[2]))  # type: ignore[misc]
        return out

    def leg_points(self) -> list[tuple[Joint, Joint, Joint | None]]:
        """(골반, 무릎, 발목?) 쌍. 무릎이 흐리면 골반-발목 중점으로 역산."""
        out = []
        for hip, knee, ankle in LEGS:
            h = self.joint(hip)
            k = self.joint(knee)
            heel = self.joint(LEFT_HEEL if ankle == LEFT_ANKLE else RIGHT_HEEL)
            a = self.joint(ankle) or heel
            if h is None:
                continue
            if k is None and a is not None and a.y > h.y + 8:
                k = Joint(a.x, (h.y + a.y) // 2)
            if k is None or k.y <= h.y + 4:
                continue
            out.append((h, k, a))
        return out


_LANDMARKER = None


def _landmarker():
    global _LANDMARKER
    if _LANDMARKER is None:
        import mediapipe as mp
        from mediapipe.tasks.python import vision

        path = pose_path()
        if not path.exists():
            raise FileNotFoundError(f"포즈 모델 없음: {path}")
        opts = vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(path)),
            running_mode=vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=0.3,
            min_pose_presence_confidence=0.3,
            min_tracking_confidence=0.3,
        )
        _LANDMARKER = vision.PoseLandmarker.create_from_options(opts)
    return _LANDMARKER


def _usable(landmarks, idx: int, w: int, h: int) -> tuple[int, int] | None:
    p = landmarks[idx]
    if (p.presence if hasattr(p, "presence") else 1.0) < PRESENCE_MIN:
        return None
    x, y = int(round(p.x * w)), int(round(p.y * h))
    if not (0 <= x < w and 0 <= y < h):
        return None
    return (x, y)


def detect_pose(image: Image.Image) -> PosePoints | None:
    """어깨·골반·무릎을 읽는다. 실패(모델 없음 포함)하면 None."""
    try:
        import mediapipe as mp  # noqa: F401
        import numpy as np

        rgb = image.convert("RGB")
        w, h = rgb.size
        lm = _landmarker()
        result = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(rgb)))
    except Exception:
        return None
    if not result.pose_landmarks:
        return None
    pts = result.pose_landmarks[0]
    ids = (
        LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_ELBOW, RIGHT_ELBOW, LEFT_WRIST, RIGHT_WRIST,
        LEFT_HIP, RIGHT_HIP, LEFT_KNEE, RIGHT_KNEE, LEFT_ANKLE, RIGHT_ANKLE,
        LEFT_HEEL, RIGHT_HEEL,
    )
    joints = {i: _usable(pts, i, w, h) for i in ids}
    shoulders = [joints[i] for i in (LEFT_SHOULDER, RIGHT_SHOULDER) if joints[i]]
    hips = [joints[i] for i in (LEFT_HIP, RIGHT_HIP) if joints[i]]
    if not shoulders:
        return None
    shoulder_y = min(p[1] for p in shoulders)
    xs = [p[0] for p in shoulders] + [p[0] for p in hips]
    mid_x = sum(xs) // len(xs)
    half_w = max(8, (max(xs) - min(xs)) // 2 + 6)
    hip_y = (min(p[1] for p in hips)) if hips else None
    knee_pts = [joints[i] for i in (LEFT_KNEE, RIGHT_KNEE) if joints[i]]
    if not knee_pts:
        for hip_i, ank_i in ((LEFT_HIP, LEFT_ANKLE), (RIGHT_HIP, RIGHT_ANKLE)):
            if joints[hip_i] and joints[ank_i] and joints[ank_i][1] > joints[hip_i][1] + 8:
                knee_pts.append(((joints[hip_i][0] + joints[ank_i][0]) // 2,
                                 (joints[hip_i][1] + joints[ank_i][1]) // 2))
    knee_y = (min(p[1] for p in knee_pts)) if knee_pts else None
    if hip_y is not None and hip_y <= shoulder_y + 4:
        hip_y = None
    if knee_y is not None and (hip_y is None or knee_y <= hip_y + 4):
        knee_y = None
    table = {i: Joint(*joints[i]) for i in joints if joints[i] is not None}
    return PosePoints(shoulder_y, hip_y, knee_y, mid_x, half_w, table)


def torso_bands(pose: PosePoints, image_size: tuple[int, int]) -> list[FaceBox]:
    """어깨→골반 사이 상의 밴드 3개. 골반 없으면 빈 리스트."""
    if not pose.has_torso:
        return []
    top, bottom = pose.shoulder_y, pose.hip_y
    assert bottom is not None
    band_h = max(4, (bottom - top) // 3)
    out = []
    for i in range(3):
        y = top + i * band_h
        height = min(band_h, image_size[1] - y)
        if height < 4:
            break
        box = clip_to(FaceBox(pose.mid_x - pose.half_w, y, pose.half_w * 2, height), image_size)
        if box is not None:
            out.append(box)
    return out


def leg_bands(pose: PosePoints, image_size: tuple[int, int]) -> list[FaceBox]:
    """골반→무릎(없으면 이미지 하단) 하의 밴드 2개. 골반 없으면 빈 리스트(상반신)."""
    if not pose.has_legs:
        return []
    assert pose.hip_y is not None
    bottom = pose.knee_y if pose.knee_y is not None else image_size[1]
    band_h = max(4, (bottom - pose.hip_y) // 2)
    out = []
    for i in range(2):
        y = pose.hip_y + i * band_h
        height = min(band_h, image_size[1] - y)
        if height < 4:
            break
        box = clip_to(FaceBox(pose.mid_x - pose.half_w, y, pose.half_w * 2, height), image_size)
        if box is not None:
            out.append(box)
    return out
