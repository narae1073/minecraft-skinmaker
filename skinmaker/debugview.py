"""단계별 시각 샘플.

각 단계가 "무엇을 결정했는지" 를 눈으로 확인하기 위한 패널을 만든다.
2단계에서 잘못 남긴 비트는 4단계에서 못 찾으므로 단계마다 그 자리에서 봐야 한다.

패널은 registry 에 등록한다. S1~S3 가 생기면 PANELS 에 한 줄씩 추가한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .quality import PhotoInput, hair_region, shirt_bands, skin_region
from .preview import render_preview
from .uvguide import ACC_COLORS, CORE_COLORS

PANEL_W = 360
PAD = 10
CAPTION_H = 17
NOTE_H = 15
CHAR_W = 6
BG = (24, 24, 28)
FG = (232, 232, 236)
DIM = (140, 140, 150)

REGION_COLORS = {
    "face": (64, 220, 120),
    "skin": (90, 150, 255),
    "hair": (232, 90, 200),
    "shirt": (80, 220, 230),
}


def font(size: int = 11, mono: bool = False) -> ImageFont.ImageFont:
    name = "DejaVuSansMono.ttf" if mono else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


def max_chars(w: int) -> int:
    return max(12, (w - 8) // CHAR_W)


def caption(text: str, w: int, color: tuple = FG) -> Image.Image:
    img = Image.new("RGBA", (w, CAPTION_H), BG)
    ImageDraw.Draw(img).text((2, 3), text[:max_chars(w)], fill=color, font=font(10, mono=True))
    return img


def note_lines(text: str, w: int) -> list[str]:
    step = max_chars(w)
    return [text[i : i + step] for i in range(0, len(text), step)] or [""]


def _fit(img: Image.Image, w: int) -> Image.Image:
    h = max(1, int(img.height * w / img.width))
    return img.resize((w, h), Image.LANCZOS)


def _grid_overlay(draw: ImageDraw.ImageDraw, w: int, h: int, cell: int) -> None:
    for i in range(0, w + 1, cell):
        shade = (255, 255, 255, 46) if (i // cell) % 2 == 0 else (255, 255, 255, 26)
        draw.line([(i, 0), (i, h)], fill=shade, width=1)
        draw.line([(0, i), (w, i)], fill=shade, width=1)


@dataclass
class Panel:
    title: str
    image: Image.Image
    note: str = ""

    def render(self, w: int = PANEL_W) -> Image.Image:
        body = _fit(self.image.convert("RGB"), w) if self.image.width != w else self.image.convert("RGB")
        lines = note_lines(self.note, w) if self.note else []
        total_h = CAPTION_H + body.height + NOTE_H * len(lines)
        out = Image.new("RGBA", (w, total_h), BG)
        out.paste(caption(self.title, w), (0, 0))
        out.paste(body, (0, CAPTION_H))
        for i, line in enumerate(lines):
            out.paste(caption(line, w, DIM), (0, CAPTION_H + body.height + i * NOTE_H))
        return out


# --- S0 -------------------------------------------------------------------

def panel_s0(photo: PhotoInput) -> Panel:
    base = photo.image.convert("RGB")
    w = PANEL_W
    img = _fit(base, w)
    scale = w / base.width
    draw = ImageDraw.Draw(img)
    mono = font(10, mono=True)

    if photo.face is None:
        draw.rectangle([0, 0, img.width - 1, img.height - 1], outline=(220, 60, 60), width=3)
        return Panel("S0 input gate", img, "REJECTED: no face detected")

    f = photo.face
    fx, fy = int(f.x * scale), int(f.y * scale)
    fw, fh = max(2, int(f.w * scale)), max(2, int(f.h * scale))
    for region, box in (
        ("hair", hair_region(f)),
        ("skin", skin_region(f)),
    ):
        x0, y0 = int(box.x * scale), int(box.y * scale)
        x1 = int((box.x + box.w) * scale)
        y1 = int((box.y + box.h) * scale)
        draw.rectangle([x0, y0, x1, y1], outline=REGION_COLORS[region], width=2)

    for i, band in enumerate(shirt_bands(f, base.size)):
        x0, y0 = int(band.x * scale), int(band.y * scale)
        x1 = int((band.x + band.w) * scale)
        y1 = int((band.y + band.h) * scale)
        draw.rectangle([x0, y0, x1, y1], outline=REGION_COLORS["shirt"], width=2)
        draw.text((x0 + 2, y0 + 1), str(i), fill=REGION_COLORS["shirt"], font=mono)

    ok = photo.face is not None and not photo.degrade
    draw.rectangle([fx, fy, fx + fw, fy + fh], outline=REGION_COLORS["face"] if ok else (240, 170, 40), width=3)
    q = photo.quality
    note = ""
    if q:
        note = (
            f"face {f.w}x{f.h} score={q.detection_score:.2f} flags={','.join(photo.degrade) or 'none'} "
            f"bright={q.brightness:.0f} sharp={q.sharpness:.0f} sat={q.saturation:.0f} "
            f"hair={hair_region(f).w}x{hair_region(f).h} skin={skin_region(f).w}x{skin_region(f).h} "
            f"bands={len(shirt_bands(f, base.size))}"
        )
    return Panel("S0 input gate", img, note)


def panel_reject(photo: PhotoInput) -> Panel:
    img = _fit(photo.image.convert("RGB"), PANEL_W)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, img.width - 1, img.height - 1], outline=(220, 60, 60), width=3)
    draw.text((8, 8), "REJECTED", fill=(255, 120, 120), font=font(16, mono=True))
    return Panel("S0 input gate", img, f"REJECTED  flags={','.join(photo.degrade) or 'none'}")


# --- S3 / S4 --------------------------------------------------------------

def panel_atlas(image: Image.Image, scale: int = 8, cell: int = 8) -> Panel:
    w = TEXTURE * scale
    img = image.convert("RGBA").resize((w, w), Image.NEAREST)
    flat = Image.new("RGBA", (w, w), (48, 48, 54, 255))
    flat.paste(img, (0, 0), img)
    draw = ImageDraw.Draw(flat, "RGBA")
    _grid_overlay(draw, w, w, cell)
    return Panel("S3 atlas 64x64", flat, f"grid = {cell} texels")


def panel_uvmap(image: Image.Image, model: str, scale: int = 7) -> Panel:
    layout_regions: list[tuple[tuple[int, int, int, int], tuple[int, int, int]]] = []
    from .format import get_layout

    layout = get_layout(model)
    for part in layout.parts.values():
        palette = CORE_COLORS if part.layer == 0 else ACC_COLORS
        for face in part.faces.values():
            layout_regions.append((face.rect, palette[face.name]))

    w = TEXTURE * scale
    base = Image.new("RGBA", (w, w), (255, 255, 255, 255))
    d = ImageDraw.Draw(base, "RGBA")
    for (x, y, fw, fh), color in layout_regions:
        d.rectangle([x * scale, y * scale, (x + fw) * scale - 1, (y + fh) * scale - 1], fill=color + (255,))

    skin = image.convert("RGBA").resize((w, w), Image.NEAREST)
    out = Image.blend(base, skin, 0.55)
    d2 = ImageDraw.Draw(out, "RGBA")
    for (x, y, fw, fh), _ in layout_regions:
        d2.rectangle(
            [x * scale, y * scale, (x + fw) * scale - 1, (y + fh) * scale - 1],
            outline=(0, 0, 0, 190),
            width=1,
        )
    for label, (tx, ty) in (("HEAD front", (8, 8)), ("BODY front", (20, 20)), ("R ARM front", (44, 20))):
        d2.text((tx * scale + 2, ty * scale + 1), label, fill=(0, 0, 0), font=font(8, mono=True))
    return Panel("S3 skin over UV guide", out, "content = skin, tint = region id")


def panel_preview(image: Image.Image, model: str) -> Panel:
    prev = render_preview(image, model).convert("RGB")
    return Panel("S4 preview front/side/back/top/overlay", prev)


# --- 레지스트리 -----------------------------------------------------------

TEXTURE = 64

PANELS = ("s0", "atlas", "uvmap", "preview")


def build_panels(photo: PhotoInput, skin: Image.Image | None, model: str, which=PANELS) -> list[Panel]:
    out = []
    for name in which:
        if name == "s0":
            out.append(panel_s0(photo) if photo.face is not None else panel_reject(photo))
        elif name == "atlas" and skin is not None:
            out.append(panel_atlas(skin))
        elif name == "uvmap" and skin is not None:
            out.append(panel_uvmap(skin, model))
        elif name == "preview" and skin is not None:
            out.append(panel_preview(skin, model))
    return out


def contact_sheet(panels: list[Panel], w: int = PANEL_W) -> Image.Image:
    if not panels:
        return Image.new("RGBA", (w, CAPTION_H), BG)
    imgs = [p.render(w) for p in panels]
    total_h = sum(i.height for i in imgs) + PAD * (len(imgs) - 1)
    out = Image.new("RGBA", (w, total_h), BG)
    y = 0
    for i in imgs:
        out.paste(i, (0, y))
        y += i.height + PAD
    return out
