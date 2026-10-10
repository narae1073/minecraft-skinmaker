"""Minecraft 64x64 스킨 텍스처의 UV 레이아웃.

위키 수치(레이어당 classic 1632 / slim 1568 사용 가능 픽셀)를 이 모듈이 재현하는지
자체검증한다. 검증 실패하면 스킨이 게임에서 깨지므로 이 상수를 단일 진실 소스로 쓴다.
"""
from __future__ import annotations

from dataclasses import dataclass

TEXTURE_SIZE = 64

PART_NAMES = ("head", "body", "r_arm", "r_leg", "l_arm", "l_leg")

MIRRORED_PAIRS = {"r_arm": "l_arm", "r_leg": "l_leg"}

LEFT_PARTS = frozenset(MIRRORED_PAIRS.values())

CUBOID_FACE_ORDER = ("top", "bottom", "right", "front", "left", "back")
LIMB_FACE_ORDER = ("front", "right", "back", "left", "top", "bottom")

PART_LAYERS = (0, 1)

# HEAD / HEAD ACC. 레이어 규칙 (S3 렌더 불변식).
# 기본 HEAD(layer=0, 영역 (0,0,32,16)): 얼굴(눈·코·입) + 기본 머리카락(앞·옆·뒤·정수리).
# HEAD ACC.(layer=1, 영역 (32,0,32,16)): 기본 투명. 모자/헬멧/안경/귀/3D 오버레이 머리카락만.
# 머리카락 텍스처는 무조건 HEAD(layer=0)에만 할당한다. S3 렌더러는 이 상수를 쓴다.
HEAD_HAIR_LAYER = 0
HEAD_ACCESSORY_LAYER = 1
HEAD_BASE_REGION = (0, 0, 32, 16)
HEAD_OVERLAY_REGION = (32, 0, 32, 16)


@dataclass(frozen=True)
class Face:
    name: str
    x: int
    y: int
    w: int
    h: int

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)

    def contains(self, u: int, v: int) -> bool:
        return 0 <= u < self.w and 0 <= v < self.h


@dataclass(frozen=True)
class Part:
    name: str
    layer: int
    x: int
    y: int
    w: int
    h: int
    box: tuple[int, int, int]
    faces: dict[str, Face]

    @property
    def region(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)

    def face(self, name: str) -> Face:
        try:
            return self.faces[name]
        except KeyError as exc:
            raise KeyError(f"{self.name}[layer={self.layer}]에 없는 면: {name}") from exc

    @property
    def face_area(self) -> int:
        return sum(f.w * f.h for f in self.faces.values())


def _cuboid_faces(x: int, y: int, w: int, h: int, d: int) -> dict[str, Face]:
    return {
        "top": Face("top", x + d, y, w, d),
        "bottom": Face("bottom", x + d + w, y, w, d),
        "right": Face("right", x, y + d, d, h),
        "front": Face("front", x + d, y + d, w, h),
        "left": Face("left", x + d + w, y + d, d, h),
        "back": Face("back", x + d + w + d, y + d, w, h),
    }


def _limb_faces(x: int, y: int, w: int, h: int, d: int) -> dict[str, Face]:
    return {
        "top": Face("top", x + d, y, w, d),
        "bottom": Face("bottom", x + d + w, y, w, d),
        "front": Face("front", x + d, y + d, w, h),
        "right": Face("right", x + d + w, y + d, d, h),
        "back": Face("back", x + d + w + d, y + d, w, h),
        "left": Face("left", x, y + d, d, h),
    }


class Layout:
    """한 모델에 대한 UV 배치. classic=4px 팔, slim=3px 팔."""

    def __init__(self, model: str = "classic"):
        if model not in ("classic", "slim"):
            raise ValueError(f"알 수 없는 모델: {model!r} (classic 또는 slim)")
        self.model = model
        arm_w = 3 if model == "slim" else 4

        boxes: dict[str, tuple[int, int, int]] = {
            "head": (8, 8, 8),
            "body": (8, 12, 4),
            "r_arm": (arm_w, 12, 4),
            "r_leg": (4, 12, 4),
            "l_arm": (arm_w, 12, 4),
            "l_leg": (4, 12, 4),
        }

        regions: dict[str, tuple[int, int, int, int]] = {
            "head": (0, 0, 32, 16),
            "body": (16, 16, 24, 16),
            "r_arm": (40, 16, 16, 16),
            "r_leg": (0, 16, 16, 16),
            "l_leg": (16, 48, 16, 16),
            "l_arm": (32, 48, 16, 16),
        }

        overlay_regions = {
            "head": (32, 0, 32, 16),
            "body": (16, 32, 24, 16),
            "r_arm": (40, 32, 16, 16),
            "r_leg": (0, 32, 16, 16),
            "l_leg": (0, 48, 16, 16),
            "l_arm": (48, 48, 16, 16),
        }

        self.boxes = boxes
        self.parts: dict[tuple[str, int], Part] = {}
        for name in PART_NAMES:
            w, h, d = boxes[name]
            for layer, table in ((0, regions), (1, overlay_regions)):
                x, y, rw, rh = table[name]
                faces = _cuboid_faces(x, y, w, h, d) if name in ("head", "body") else _limb_faces(x, y, w, h, d)
                self.parts[(name, layer)] = Part(name, layer, x, y, rw, rh, (w, h, d), faces)

    def part(self, name: str, layer: int = 0) -> Part:
        if layer not in PART_LAYERS:
            raise ValueError(f"레이어는 0 또는 1이어야 합니다: {layer!r}")
        try:
            return self.parts[(name, layer)]
        except KeyError as exc:
            raise KeyError(f"알 수 없는 파트: {name!r}") from exc

    def face(self, name: str, face: str, layer: int = 0) -> Face:
        return self.part(name, layer).face(face)

    def usable_pixels(self) -> int:
        return sum(p.face_area for p in self.parts.values() if p.layer == 0) * 2

    def expected_usable_pixels(self) -> int:
        return 1568 * 2 if self.model == "slim" else 1632 * 2

    def all_face_rects(self) -> list[Face]:
        return [f for p in self.parts.values() for f in p.faces.values()]

    def check(self) -> None:
        for p in self.parts.values():
            for f in p.faces.values():
                inside = (
                    p.x <= f.x
                    and p.y <= f.y
                    and f.x + f.w <= p.x + p.w
                    and f.y + f.h <= p.y + p.h
                )
                if not inside:
                    raise AssertionError(f"{p.name}[{p.layer}].{f.name}가 파트 영역 밖: {f.rect} not in {p.region}")
                if f.x + f.w > TEXTURE_SIZE or f.y + f.h > TEXTURE_SIZE:
                    raise AssertionError(f"{p.name}[{p.layer}].{f.name}가 64x64 밖: {f.rect}")
        seen: set[tuple[int, int]] = set()
        for p in self.parts.values():
            for f in p.faces.values():
                for py in range(f.y, f.y + f.h):
                    for px in range(f.x, f.x + f.w):
                        if (px, py) in seen:
                            raise AssertionError(f"면이 겹침: {p.name}[{p.layer}].{f.name} {f.rect}")
                        seen.add((px, py))
        got = self.usable_pixels()
        want = self.expected_usable_pixels()
        if got != want:
            raise AssertionError(f"{self.model} 사용 가능 픽셀 {got} != 위키 기준 {want}")


_LAYOUTS: dict[str, Layout] = {}


def get_layout(model: str = "classic") -> Layout:
    layout = _LAYOUTS.get(model)
    if layout is None:
        layout = Layout(model)
        layout.check()
        _LAYOUTS[model] = layout
    return layout
