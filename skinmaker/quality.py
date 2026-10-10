"""사진 입력 판정: 얼굴 검출, 품질 신호, 저하 계획.

하드 게이트는 "얼굴을 찾았는가" 하나뿐이다. 나머지 품질 신호는 거부가 아니라
렌더러 파라미터로 전달한다. 같은 결과를 내되 더 보수적으로 그린다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

try:
    import pillow_avif  # noqa: F401  (AVIF 읽기 등록. 없으면 해당 형식만 건너뜀)
except ImportError:
    pass

DETECT_SCORE_MIN = 0.60
FACE_PX_SMALL = 48
FACE_PX_METRIC_MIN = 32
BRIGHTNESS_DARK = 45.0
BRIGHTNESS_BRIGHT = 215.0
SHARPNESS_BLUR = 100.0
SATURATION_DARK = 35.0
SATURATION_FLAT = 200.0

ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"
YUNET_FILE = "face_detection_yunet_2023mar.onnx"
YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)

Image.MAX_IMAGE_PIXELS = 40_000_000


@dataclass(frozen=True)
class FaceBox:
    x: int
    y: int
    w: int
    h: int

    @property
    def area(self) -> int:
        return self.w * self.h

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h


@dataclass(frozen=True)
class Quality:
    detection_score: float
    face_px: int
    brightness: float
    sharpness: float
    saturation: float
    measured: bool


@dataclass(frozen=True)
class PhotoInput:
    path: str
    image: Image.Image
    face: FaceBox | None
    quality: Quality | None
    degrade: tuple[str, ...]
    pose: Any = None

    @property
    def rejected(self) -> bool:
        return self.face is None

    @property
    def degraded(self) -> bool:
        return bool(self.degrade)


_UNMEASURED = Quality(0.0, 0, 0.0, 0.0, 0.0, False)


def yunet_path() -> Path:
    return Path(os.environ.get("SKINMAKER_YUNET") or (ASSET_DIR / YUNET_FILE))


_DETECTOR = None


def _detector():
    global _DETECTOR
    if _DETECTOR is None:
        path = yunet_path()
        if not path.exists():
            raise FileNotFoundError(
                f"YuNet 모델 없음: {path}\n{path.parent.mkdir(parents=True, exist_ok=True)}\n"
                f"curl -sSLf -o {path} {YUNET_URL}"
            )
        _DETECTOR = cv2.FaceDetectorYN.create(str(path), "", (320, 320), DETECT_SCORE_MIN, 0.3, 5000)
    return _DETECTOR


def detect_face(image: Image.Image, score_min: float = DETECT_SCORE_MIN) -> FaceBox | None:
    model = _detector()
    rgb = np.asarray(image.convert("RGB"))
    h, w = rgb.shape[:2]
    model.setInputSize((w, h))
    model.setScoreThreshold(score_min)
    _n, faces = model.detect(rgb)
    if faces is None or len(faces) == 0:
        return None
    best = max(faces, key=lambda f: float(f[-1]))
    x, y, fw, fh = (int(round(float(v))) for v in best[:4])
    return FaceBox(x, y, fw, fh)


def crop(image: Image.Image, box: FaceBox) -> np.ndarray:
    return np.asarray(image.convert("RGB").crop((box.x, box.y, box.right, box.bottom)))


def measure_quality(image: Image.Image, face: FaceBox, score: float = 1.0) -> Quality:
    patch = crop(image, face)
    if min(face.w, face.h) < FACE_PX_METRIC_MIN:
        return Quality(score, face.area, 0.0, 0.0, 0.0, False)
    gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(patch, cv2.COLOR_RGB2HSV)
    return Quality(
        detection_score=score,
        face_px=face.area,
        brightness=float(gray.mean()),
        sharpness=float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        saturation=float(hsv[:, :, 1].mean()),
        measured=True,
    )


def plan_degradation(q: Quality) -> tuple[str, ...]:
    if not q.measured:
        return ("small",)
    flags = []
    if q.sharpness < SHARPNESS_BLUR:
        flags.append("blur")
    if q.brightness < BRIGHTNESS_DARK:
        flags.append("dark")
    elif q.brightness > BRIGHTNESS_BRIGHT:
        flags.append("bright")
    if q.face_px < FACE_PX_SMALL:
        flags.append("small")
    if q.saturation < SATURATION_DARK:
        flags.append("flat")
    return tuple(flags)


def inspect(path: str | Path, score_min: float = DETECT_SCORE_MIN) -> PhotoInput:
    p = Path(path)
    with Image.open(p) as im:
        image = im.convert("RGB")
        face = detect_face(image, score_min)
        if face is None:
            return PhotoInput(str(p), image, None, None, (), None)
        quality = measure_quality(image, face)
    degrade = plan_degradation(quality)
    try:
        from .pose import detect_pose

        pose = detect_pose(image)
    except Exception:
        pose = None
    return PhotoInput(str(p), image, face, quality, degrade, pose)


def clip_to(box: FaceBox, size: tuple[int, int]) -> FaceBox | None:
    """영역 자르기. 이미지를 벗어나면 None.

    hair_region 은 얼굴 박스 밖까지 확장하므로 음수 좌표가 나올 수 있다.
    자르는 책임은 샘플러에 두되 이 헬퍼를 쓰게 한다.
    """
    img_w, img_h = size
    x0, y0 = max(0, box.x), max(0, box.y)
    x1, y1 = min(img_w, box.right), min(img_h, box.bottom)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    return FaceBox(x0, y0, x1 - x0, y1 - y0)


def skin_region(face: FaceBox) -> FaceBox:
    """볼·코 영역. 눈(얼굴 높이의 45~55%)과 입(75~85%)을 피한다.

    얼굴 박스를 통째로 쓰면 눈 흰자국과 속눈썹이 중앙값을 끌어간다.
    하단은 75%에서 끊는다. 입술(붉은색)은 영역 중앙값의 R 크로마를
    끌어올려 채널 상대 게인 중 R을 클립 하한(1/1.25)까지 몰아가므로
    볼·코만 쓴다.
    """
    x = int(face.w * 0.20)
    top = int(face.h * 0.55)
    return FaceBox(face.x + x, face.y + top, int(face.w * 0.60), int(face.h * 0.20))


def hair_region(face: FaceBox, up: float = 0.35, top: float = 0.45, out: float = 0.10) -> FaceBox:
    """얼굴 박스 위쪽과 좌우로 확장한 헤어 샘플 영역.

    얼굴 박스는 얼굴에 밀착하므로 박스 안쪽만 보면 모자 챙이나 이마만 잡는다.
    긴머리는 머리 위뿐 아니라 얼굴 옆으로도 흘러내리므로 사방 확장한다.
    이미지를 벗어날 수 있으므로 clip_to 로 자른다.
    남은 배경은 S1 의 클러스터 탈락이 처리한다.
    """
    up_px = int(face.h * up)
    out_px = int(face.w * out)
    return FaceBox(
        face.x - out_px,
        face.y - up_px,
        face.w + 2 * out_px,
        up_px + int(face.h * top),
    )


def shirt_bands(face: FaceBox, image_size: tuple[int, int], expand: float = 1.5) -> list[FaceBox]:
    """얼굴 아래 상의 후보. 좌우 15% 는 잘라 배경 혼입을 막는다.

    pose 추정 없이 세로 밴드만 사용한다. 밴드가 여러 개면 최빈값을 쓴다.
    """
    img_w, img_h = image_size
    band_h = max(4, int(face.h * expand / 3))
    inset = int(face.w * 0.15)
    left = min(max(0, face.x + inset), img_w - 1)
    usable_w = min(face.w - 2 * inset, img_w - left)
    bands = []
    for i in range(3):
        top = face.bottom + i * band_h
        height = min(band_h, img_h - top)
        if height < 4 or usable_w < 4:
            break
        bands.append(FaceBox(left, top, usable_w, height))
    return bands
