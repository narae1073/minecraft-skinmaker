"""64x64 RGBA 스킨 캔버스. 좌우 파트 미러를 이 계층에서 강제한다."""
from __future__ import annotations

from PIL import Image

from .format import LEFT_PARTS, TEXTURE_SIZE, Layout, get_layout

Color = tuple[int, int, int, int]


def rgba(hex_color: str, alpha: int = 255) -> Color:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"RRGGBB 여야 합니다: {hex_color!r}")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def shade(color: Color, factor: float) -> Color:
    r, g, b, a = color
    clamp = lambda v: max(0, min(255, round(v)))
    if factor >= 1.0:
        f = factor
        return (clamp(r + (255 - r) * (f - 1.0)), clamp(g + (255 - g) * (f - 1.0)), clamp(b + (255 - b) * (f - 1.0)), a)
    return (clamp(r * factor), clamp(g * factor), clamp(b * factor), a)


TRANSPARENT: Color = (0, 0, 0, 0)


class SkinCanvas:
    def __init__(self, model: str = "classic"):
        self.layout: Layout = get_layout(model)
        self.model = model
        self.image = Image.new("RGBA", (TEXTURE_SIZE, TEXTURE_SIZE), TRANSPARENT)

    def put(self, part: str, face: str, u: int, v: int, color: Color, layer: int = 0) -> None:
        f = self.layout.face(part, face, layer)
        if not f.contains(u, v):
            raise ValueError(f"{part}.{face} 범위 밖: u={u} v={v} (크기 {f.w}x{f.h})")
        if part in LEFT_PARTS:
            u = f.w - 1 - u
        self.image.putpixel((f.x + u, f.y + v), color)

    def get(self, part: str, face: str, u: int, v: int, layer: int = 0) -> Color:
        f = self.layout.face(part, face, layer)
        if not f.contains(u, v):
            raise ValueError(f"{part}.{face} 범위 밖: u={u} v={v}")
        if part in LEFT_PARTS:
            u = f.w - 1 - u
        return self.image.getpixel((f.x + u, f.y + v))

    def fill_face(self, part: str, face: str, color: Color, layer: int = 0) -> None:
        f = self.layout.face(part, face, layer)
        for v in range(f.h):
            for u in range(f.w):
                self.put(part, face, u, v, color, layer)

    def fill_part(self, part: str, color: Color, layer: int = 0) -> None:
        for face in self.layout.part(part, layer).faces:
            self.fill_face(part, face, color, layer)

    def fill_part_region(self, part: str, color: Color, layer: int = 0) -> None:
        x, y, w, h = self.layout.part(part, layer).region
        for py in range(y, y + h):
            for px in range(x, x + w):
                self.image.putpixel((px, py), color)

    def is_used(self, x: int, y: int) -> bool:
        for f in self.layout.all_face_rects():
            if f.x <= x < f.x + f.w and f.y <= y < f.y + f.h:
                return True
        return False
