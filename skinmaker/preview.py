"""순수 Python 3면 프리뷰. 게임 없이 어긋남을 눈으로 확인하기 위한 QA 장치."""
from __future__ import annotations

from PIL import Image

from .format import get_layout

SCALE = 8
GAP = 4
BACKDROP = (18, 18, 22, 255)

VIEWS: dict[str, list[tuple[str, str, int, int]]] = {
    "front": [
        ("head", "front", 4, 0),
        ("r_arm", "front", 0, 8),
        ("body", "front", 4, 8),
        ("l_arm", "front", 12, 8),
        ("r_leg", "front", 4, 20),
        ("l_leg", "front", 8, 20),
    ],
    "side": [
        ("head", "right", 0, 0),
        ("r_arm", "right", 2, 8),
        ("body", "right", 2, 8),
        ("r_leg", "right", 2, 20),
    ],
    "back": [
        ("head", "back", 4, 0),
        ("l_arm", "back", 0, 8),
        ("body", "back", 4, 8),
        ("r_arm", "back", 12, 8),
        ("l_leg", "back", 4, 20),
        ("r_leg", "back", 8, 20),
    ],
    "top": [
        ("head", "top", 0, 0),
    ],
}

PANELS = (("front", 0), ("side", 0), ("back", 0), ("top", 0), ("front", 1))


def render_view(image: Image.Image, model: str, view: str, layer: int = 0) -> Image.Image:
    layout = get_layout(model)
    cells = VIEWS[view]
    width = max(ox + layout.face(p, f).w for p, f, ox, _oy in cells)
    height = max(oy + layout.face(p, f).h for p, f, _ox, oy in cells)
    out = Image.new("RGBA", (width, height), BACKDROP)
    src = image.load()
    dst = out.load()
    for part, face_name, ox, oy in cells:
        f = layout.face(part, face_name, layer)
        for v in range(f.h):
            for u in range(f.w):
                dst[ox + u, oy + v] = src[f.x + u, f.y + v]
    return out


def render_preview(image: Image.Image, model: str = "classic") -> Image.Image:
    panels = [render_view(image, model, view, layer) for view, layer in PANELS]
    total_w = sum(p.width for p in panels) + GAP * (len(panels) - 1)
    max_h = max(p.height for p in panels)
    out = Image.new("RGBA", (total_w, max_h), (12, 12, 16, 255))
    x = 0
    for p in panels:
        out.paste(p, (x, 0), p)
        x += p.width + GAP
    return out.resize((total_w * SCALE, max_h * SCALE), Image.NEAREST)


def save_preview(image: Image.Image, path: str, model: str = "classic") -> str:
    render_preview(image, model).convert("RGB").save(path)
    return path
