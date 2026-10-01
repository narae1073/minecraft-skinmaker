"""64x64 UV 가이드 이미지 생성.

포맷 정확성은 눈으로 대조하는 게 가장 확실하다. 이 모듈은 Layout 에서
색으로 코딩된 가이드를 그려서 위키 템플릿 그림과 1:1 로 비교할 수 있게 한다.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from .format import TEXTURE_SIZE, get_layout

SCALE = 9
LEGEND_GAP = 8

CORE_COLORS = {
    "front": (139, 47, 201),
    "left": (27, 127, 212),
    "right": (208, 32, 32),
    "back": (232, 88, 12),
    "top": (240, 228, 66),
    "bottom": (30, 70, 32),
}

ACC_COLORS = {
    "front": (185, 168, 216),
    "left": (156, 184, 216),
    "right": (208, 160, 160),
    "back": (208, 184, 168),
    "top": (216, 208, 168),
    "bottom": (110, 122, 110),
}

LABELS = {
    "front": "FRONT",
    "left": "LEFT",
    "right": "RIGHT",
    "back": "BACK",
    "top": "TOP",
    "bottom": "BOTTOM",
}

PART_TITLES = {
    "head": "HEAD",
    "body": "BODY",
    "r_arm": "RIGHT ARM",
    "r_leg": "RIGHT LEG",
    "l_arm": "LEFT ARM",
    "l_leg": "LEFT LEG",
}


def _font() -> ImageFont.ImageFont:
    for name in ("DejaVuSansMono.ttf", "DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, 7)
        except OSError:
            continue
    return ImageFont.load_default()


def render_uv_guide(model: str = "classic") -> Image.Image:
    layout = get_layout(model)
    font = _font()
    grid = TEXTURE_SIZE * SCALE
    out = Image.new("RGB", (grid, grid), (255, 255, 255))
    draw = ImageDraw.Draw(out)

    for part_name, layer in sorted(layout.parts, key=lambda k: (k[0], k[1])):
        part = layout.part(part_name, layer)
        palette = CORE_COLORS if layer == 0 else ACC_COLORS
        for face in part.faces.values():
            x0, y0 = face.x * SCALE, face.y * SCALE
            x1, y1 = (face.x + face.w) * SCALE, (face.y + face.h) * SCALE
            draw.rectangle([x0, y0, x1 - 1, y1 - 1], fill=palette[face.name], outline=(20, 20, 20))
            if face.w * SCALE >= 16:
                draw.text((x0 + 1, y0 + 1), LABELS[face.name], fill=(255, 255, 255), font=font)
            title = f"{PART_TITLES[part_name]}{' ACC.' if layer else ''}"
            if face.w * SCALE >= 40 and face.h * SCALE >= 40:
                draw.text((x0 + 1, y0 + 10), title, fill=(255, 255, 255), font=font)

    return out


def save_uv_guide(path: str, model: str = "classic") -> str:
    render_uv_guide(model).save(path)
    return path
