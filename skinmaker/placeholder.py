"""동작 확인용 flat 더미 스킨. AI 없이 6면 배치/미러/레이어 분리를 검증한다."""
from __future__ import annotations

from .canvas import Color, SkinCanvas, rgba, shade

FACE_SHADE = {
    "top": 1.12,
    "front": 1.0,
    "back": 0.90,
    "left": 0.84,
    "right": 0.84,
    "bottom": 0.72,
}

SLEEVE_END_ROW = 7
LEG_END_ROW = 9
SHOE = rgba("#2b2b2b")


def _shaded_part(canvas: SkinCanvas, part: str, base: Color, layer: int = 0) -> None:
    for face_name, face in canvas.layout.part(part, layer).faces.items():
        canvas.fill_face(part, face_name, shade(base, FACE_SHADE[face_name]), layer)


def _head_front_features(canvas: SkinCanvas, skin: Color, hair: Color) -> None:
    for u in range(8):
        for v in (0, 1):
            canvas.put("head", "front", u, v, hair, 0)
    for v in (2, 3):
        canvas.put("head", "front", 0, v, hair, 0)
        canvas.put("head", "front", 7, v, hair, 0)
    sclera = rgba("#f2f2f2")
    iris = rgba("#3b2a1a")
    for base_u in (1, 5):
        canvas.put("head", "front", base_u, 3, sclera)
        canvas.put("head", "front", base_u + 1, 3, iris)
        for v in (4,):
            canvas.put("head", "front", base_u, v, iris)
            canvas.put("head", "front", base_u + 1, v, iris)
    for u in range(2, 6):
        canvas.put("head", "front", u, 6, shade(skin, 0.72))


def build_placeholder(
    model: str = "classic",
    skin: str = "#e0ac69",
    hair: str = "#3a2a1c",
    shirt: str = "#2f6fb5",
    pants: str = "#3c4450",
) -> SkinCanvas:
    c = SkinCanvas(model)
    skin_c, hair_c = rgba(skin), rgba(hair)
    shirt_c, pants_c = rgba(shirt), rgba(pants)

    _shaded_part(c, "head", skin_c)
    _head_front_features(c, skin_c, hair_c)

    _shaded_part(c, "body", shirt_c)
    for v in range(2, 4):
        c.put("body", "front", 3, v, shade(skin_c, 0.86))
        c.put("body", "front", 4, v, shade(skin_c, 0.86))

    for part in ("r_arm", "l_arm"):
        _shaded_part(c, part, shirt_c)
        for face_name in c.layout.part(part).faces:
            f = c.layout.face(part, face_name)
            if f.h < 12:
                continue
            for u in range(f.w):
                c.put(part, face_name, u, SLEEVE_END_ROW, shade(shirt_c, 0.66))
                for v in range(SLEEVE_END_ROW + 1, f.h):
                    c.put(part, face_name, u, v, shade(skin_c, FACE_SHADE[face_name]))

    for part in ("r_leg", "l_leg"):
        _shaded_part(c, part, pants_c)
        for face_name in c.layout.part(part).faces:
            f = c.layout.face(part, face_name)
            if f.h < 12:
                continue
            for u in range(f.w):
                c.put(part, face_name, u, LEG_END_ROW, shade(pants_c, 0.66))
                for v in range(LEG_END_ROW + 1, f.h):
                    c.put(part, face_name, u, v, shade(SHOE, FACE_SHADE[face_name]))

    # HEAD ACC.(head layer=1, 영역 (32,0,32,16))는 기본 투명 유지.
    # 모자/헬멧/안경/귀/3D 오버레이 머리카락 전용. 기본 머리카락은
    # 반드시 HEAD(layer=0)에만 그린다. 더미는 악세서리 없으므로 비운다.
    return c
