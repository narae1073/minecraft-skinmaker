"""Generic structural drawers for tops (2026-10-28).

These are deliberately garment-agnostic primitives: a 1px zipper, aligned
buttons, a collar, patch pockets. The VLM supplies structural tags; the
primitives keep the pixel-art silhouette crisp on top of cropped fabric.

No garment-specific rules (polo vs shirt vs jacket) live here.
"""
from __future__ import annotations

from .attributes import Attributes
from .canvas import Color, SkinCanvas, rgba, shade
from . import attribute_masks as AM

METAL = rgba("#c9ced6")


def _put(canvas: SkinCanvas, u: int, v: int, color: Color, mask=None) -> None:
    if mask is not None:
        if v < 0 or v >= len(mask) or u < 0 or u >= len(mask[v]) or not mask[v][u]:
            return
    try:
        canvas.put("body", "front", u, v, color, 0)
    except ValueError:
        pass


def _zipper_color(top: Color) -> Color:
    """Zipper follows the top garment, not a fixed silver.

    Notes 2026-11-02 (30x): the zip should resemble the top/jacket/hood. Use a
    darker variant for mid/light tops; lighten very dark tops so the teeth stay
    visible. No fixed METAL here.
    """
    r, g, b, a = top
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    if luma < 60:
        t = 0.45
        return (int(round(r * (1 - t) + 255 * t)),
                int(round(g * (1 - t) + 255 * t)),
                int(round(b * (1 - t) + 255 * t)), a)
    return shade(top, 0.72 if luma > 200 else 0.78)


def draw_zipper(canvas: SkinCanvas, attrs: Attributes, colors: dict[str, Color], mask=None) -> None:
    def put(u, v, c):
        _put(canvas, u, v, c, mask)
    """1px centre zip with alternating teeth; colour derived from the top."""
    zip_c = _zipper_color(colors.get("top") or colors["skin"])
    for v in range(1, 12):
        color = zip_c if v % 2 else shade(zip_c, 0.82)
        put(4, v, color)


def draw_buttons(canvas: SkinCanvas, attrs: Attributes, colors: dict[str, Color], mask=None) -> None:
    def put(u, v, c):
        _put(canvas, u, v, c, mask)
    """1px buttons aligned down the centre with a subtle placket line."""
    for v in range(0, 12):
        put(3, v, shade(colors["top"], 0.55))
    for v in (1, 4, 7, 10):
        put(4, v, METAL)


def _neck_color(attrs: Attributes, colors: dict[str, Color]) -> Color:
    if attrs.get("inner_top") != "none":
        return colors["inner"]
    return shade(colors["skin"], 0.90)


def draw_collar(canvas: SkinCanvas, attrs: Attributes, colors: dict[str, Color], mask=None) -> None:
    def put(u, v, c):
        _put(canvas, u, v, c, mask)
    """Crew / V / shirt / hood neckline, 1px and symmetric around u=3.5."""
    kind = attrs.get("collar_type")
    dark = shade(colors["top"], 0.55)
    neck = _neck_color(attrs, colors)
    if kind == "crew":
        for u in range(2, 6):
            put(u, 0, dark)
    elif kind == "v_neck":
        for u in (3, 4):
            put(u, 0, neck)
        for u in (3, 4):
            put(u, 1, neck)
        for u in (2, 5):
            put(u, 0, dark)
    elif kind == "shirt":
        for u in (2, 5):
            put(u, 0, dark)
        for u in (3, 4):
            put(u, 0, neck)
            put(u, 1, neck)
        put(2, 1, dark)
        put(5, 1, dark)
    elif kind == "hood":
        for u in range(1, 7):
            put(u, 0, dark)
        for v in (1, 2):
            put(1, v, dark)
            put(6, v, dark)


def draw_patch_pockets(canvas: SkinCanvas, attrs: Attributes, colors: dict[str, Color], mask=None) -> None:
    def put(u, v, c):
        _put(canvas, u, v, c, mask)
    """Two 1px patch-pocket outlines at rows 5-7."""
    dark = shade(colors["top"], 0.50)
    for x0 in (1, 5):
        x1 = x0 + 1
        for u in (x0, x1):
            put(u, 5, dark)
        for v in (5, 6, 7):
            put(x0, v, dark)
            put(x1, v, dark)


def draw_open_front(canvas: SkinCanvas, attrs: Attributes, colors: dict[str, Color], mask=None) -> None:
    def put(u, v, c):
        _put(canvas, u, v, c, mask)
    """Open jacket: show a 2px inner-layer strip, no zipper/buttons.

    Notes 2026-11-02 (15x): open jacket with an inner tee/hoodie was rendered
    closed. The body base is already the jacket; replace the centre with the
    inner layer and draw darker jacket edges. The collar is drawn afterwards.
    """
    inner = colors.get("inner") or shade(colors["skin"], 0.92)
    edge = shade(colors["top"], 0.62)
    for v in range(12):
        put(3, v, shade(inner, 0.92))
        put(4, v, inner)
    for v in range(1, 12):
        put(2, v, edge)
        put(5, v, edge)
    if attrs.get("neckwear") == "tie":
        tie = colors.get("tie")
        if tie:
            for v in (0, 1, 2):
                put(4, v, tie)


def apply_structure(canvas: SkinCanvas, attrs: Attributes, colors: dict[str, Color], masks: dict | None = None) -> None:
    """Overlay structural tags on the body front. Unknown/absent → no-op."""
    if attrs.get("top_garment") == "none":
        return
    closure = attrs.get("closure_type")
    closure_mask = AM.get_mask(masks or {}, "closure_type", closure, "L1", "body", "front")
    if closure == "open":
        draw_open_front(canvas, attrs, colors, mask=closure_mask)
    collar = attrs.get("collar_type")
    collar_mask = AM.get_mask(masks or {}, "collar_type", collar, "L1", "body", "front")
    if collar in ("crew", "v_neck", "shirt", "hood"):
        draw_collar(canvas, attrs, colors, mask=collar_mask)
    # VLM 이 단추를 놓쳐도 셔츠 칼라면 단추 여밈으로 보수적으로 보정한다
    # (폴로/버튼업 공통; 지퍼를 임의로 그리지는 않는다).
    if (
        closure == "none"
        and attrs.get("collar_type") == "shirt"
        and attrs.get("top_garment") in ("shirt", "uniform")
    ):
        closure = "buttons"
    closure_mask = AM.get_mask(masks or {}, "closure_type", closure, "L1", "body", "front")
    if closure == "zipper":
        draw_zipper(canvas, attrs, colors, mask=closure_mask)
    elif closure == "buttons":
        draw_buttons(canvas, attrs, colors, mask=closure_mask)
    pocket = attrs.get("pocket_type")
    pocket_mask = AM.get_mask(masks or {}, "pocket_type", pocket, "L1", "body", "front")
    if pocket == "patch":
        draw_patch_pockets(canvas, attrs, colors, mask=pocket_mask)
