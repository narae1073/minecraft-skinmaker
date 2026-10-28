"""Generic structural drawers for tops (2026-10-28).

These are deliberately garment-agnostic primitives: a 1px zipper, aligned
buttons, a collar, patch pockets. The VLM supplies structural tags; the
primitives keep the pixel-art silhouette crisp on top of cropped fabric.

No garment-specific rules (polo vs shirt vs jacket) live here.
"""
from __future__ import annotations

from .attributes import Attributes
from .canvas import Color, SkinCanvas, rgba, shade

METAL = rgba("#c9ced6")


def _put(canvas: SkinCanvas, u: int, v: int, color: Color) -> None:
    try:
        canvas.put("body", "front", u, v, color, 0)
    except ValueError:
        pass


def draw_zipper(canvas: SkinCanvas, attrs: Attributes, colors: dict[str, Color]) -> None:
    """1px centre zip with alternating teeth; front rows 1-11."""
    for v in range(1, 12):
        color = METAL if v % 2 else shade(METAL, 0.65)
        _put(canvas, 4, v, color)


def draw_buttons(canvas: SkinCanvas, attrs: Attributes, colors: dict[str, Color]) -> None:
    """1px buttons aligned down the centre with a subtle placket line."""
    for v in range(0, 12):
        _put(canvas, 3, v, shade(colors["top"], 0.55))
    for v in (1, 4, 7, 10):
        _put(canvas, 4, v, METAL)


def _neck_color(attrs: Attributes, colors: dict[str, Color]) -> Color:
    if attrs.get("inner_top") != "none":
        return colors["inner"]
    return shade(colors["skin"], 0.90)


def draw_collar(canvas: SkinCanvas, attrs: Attributes, colors: dict[str, Color]) -> None:
    """Crew / V / shirt / hood neckline, 1px and symmetric around u=3.5."""
    kind = attrs.get("collar_type")
    dark = shade(colors["top"], 0.55)
    neck = _neck_color(attrs, colors)
    if kind == "crew":
        for u in range(2, 6):
            _put(canvas, u, 0, dark)
    elif kind == "v_neck":
        for u in (3, 4):
            _put(canvas, u, 0, neck)
        for u in (3, 4):
            _put(canvas, u, 1, neck)
        for u in (2, 5):
            _put(canvas, u, 0, dark)
    elif kind == "shirt":
        for u in (2, 5):
            _put(canvas, u, 0, dark)
        for u in (3, 4):
            _put(canvas, u, 0, neck)
            _put(canvas, u, 1, neck)
        _put(canvas, 2, 1, dark)
        _put(canvas, 5, 1, dark)
    elif kind == "hood":
        for u in range(1, 7):
            _put(canvas, u, 0, dark)
        for v in (1, 2):
            _put(canvas, 1, v, dark)
            _put(canvas, 6, v, dark)


def draw_patch_pockets(canvas: SkinCanvas, attrs: Attributes, colors: dict[str, Color]) -> None:
    """Two 1px patch-pocket outlines at rows 5-7."""
    dark = shade(colors["top"], 0.50)
    for x0 in (1, 5):
        x1 = x0 + 1
        for u in (x0, x1):
            _put(canvas, u, 5, dark)
        for v in (5, 6, 7):
            _put(canvas, x0, v, dark)
            _put(canvas, x1, v, dark)


def apply_structure(canvas: SkinCanvas, attrs: Attributes, colors: dict[str, Color]) -> None:
    """Overlay structural tags on the body front. Unknown/absent → no-op."""
    if attrs.get("top_garment") == "none":
        return
    collar = attrs.get("collar_type")
    if collar in ("crew", "v_neck", "shirt", "hood"):
        draw_collar(canvas, attrs, colors)
    closure = attrs.get("closure_type")
    # VLM 이 단추를 놓쳐도 셔츠 칼라면 단추 여밈으로 보수적으로 보정한다
    # (폴로/버튼업 공통; 지퍼를 임의로 그리지는 않는다).
    if (
        closure == "none"
        and attrs.get("collar_type") == "shirt"
        and attrs.get("top_garment") in ("shirt", "uniform")
    ):
        closure = "buttons"
    if closure == "zipper":
        draw_zipper(canvas, attrs, colors)
    elif closure == "buttons":
        draw_buttons(canvas, attrs, colors)
    if attrs.get("pocket_type") == "patch":
        draw_patch_pockets(canvas, attrs, colors)
