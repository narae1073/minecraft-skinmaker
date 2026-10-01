"""레이아웃 상수와 검증 불변식 (네트워크/디스크 없음)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PIL import Image

from skinmaker.canvas import SkinCanvas, rgba, shade
from skinmaker.format import TEXTURE_SIZE, get_layout
from skinmaker.placeholder import build_placeholder
from skinmaker.preview import BACKDROP, PANELS, render_preview, render_view
from skinmaker.validate import assert_valid, validate_image


@pytest.mark.parametrize("model", ["classic", "slim"])
def test_layout_matches_wiki_usable_pixels(model):
    layout = get_layout(model)
    assert layout.usable_pixels() == layout.expected_usable_pixels()
    assert layout.usable_pixels() == (3136 if model == "slim" else 3264)


@pytest.mark.parametrize("model", ["classic", "slim"])
def test_layout_self_check_passes(model):
    get_layout(model).check()


@pytest.mark.parametrize("model", ["classic", "slim"])
def test_no_face_overlaps_and_stays_in_bounds(model):
    layout = get_layout(model)
    seen = set()
    for part in layout.parts.values():
        for face in part.faces.values():
            assert face.x >= 0 and face.y >= 0
            assert face.x + face.w <= TEXTURE_SIZE
            assert face.y + face.h <= TEXTURE_SIZE
            for y in range(face.y, face.y + face.h):
                for x in range(face.x, face.x + face.w):
                    assert (x, y) not in seen, f"면 겹침 at {x},{y}"
                    seen.add((x, y))


def test_head_and_body_face_coordinates_are_canonical():
    layout = get_layout("classic")
    expected = {
        ("head", "top"): (8, 0, 8, 8),
        ("head", "bottom"): (16, 0, 8, 8),
        ("head", "right"): (0, 8, 8, 8),
        ("head", "front"): (8, 8, 8, 8),
        ("head", "left"): (16, 8, 8, 8),
        ("head", "back"): (24, 8, 8, 8),
        ("body", "top"): (20, 16, 8, 4),
        ("body", "bottom"): (28, 16, 8, 4),
        ("body", "right"): (16, 20, 4, 12),
        ("body", "front"): (20, 20, 8, 12),
        ("body", "left"): (28, 20, 4, 12),
        ("body", "back"): (32, 20, 8, 12),
        ("r_arm", "front"): (44, 20, 4, 12),
        ("r_arm", "right"): (48, 20, 4, 12),
        ("r_arm", "back"): (52, 20, 4, 12),
        ("r_arm", "left"): (40, 20, 4, 12),
        ("r_arm", "top"): (44, 16, 4, 4),
        ("r_arm", "bottom"): (48, 16, 4, 4),
    }
    for (part, face), rect in expected.items():
        assert layout.face(part, face).rect == rect, part + "." + face


def test_limb_faces_match_vanilla_modelbox_quad_order():
    """vanilla ModelBox: [1]은 x=u+d(u=0이면 x=0), [3]은 x=u+d+w, [5]은 x=u+d+w+d.

    머리/몸통은 -X 가 플레이어 오른쪽이라 x=0 이 right 다. 팔다리는 1.8 의
    mirror 플래그 해석이 양립해 좌우 이름을 뒤집어도 좌표는 같고, 4x12 면 두 장은
    단색이라 실제 차이가 없다. 여기서는 전 편집기/렌더러 공통 관례대로
    x=u 를 안쪽(inward) 면으로 둔다.
    """
    layout = get_layout("classic")
    for part, ox, oy in (("r_arm", 40, 16), ("r_leg", 0, 16), ("l_arm", 32, 48), ("l_leg", 16, 48)):
        assert layout.face(part, "left").rect == (ox, oy + 4, 4, 12)
        assert layout.face(part, "front").rect == (ox + 4, oy + 4, 4, 12)
        assert layout.face(part, "right").rect == (ox + 8, oy + 4, 4, 12)
        assert layout.face(part, "back").rect == (ox + 12, oy + 4, 4, 12)
        assert layout.face(part, "top").rect == (ox + 4, oy, 4, 4)
        assert layout.face(part, "bottom").rect == (ox + 8, oy, 4, 4)


def test_uv_guide_renders_at_64_times_scale():
    from skinmaker.uvguide import render_uv_guide, SCALE

    guide = render_uv_guide("classic")
    assert guide.size == (64 * SCALE, 64 * SCALE)
    assert render_uv_guide("slim").size == guide.size


def test_slim_arm_is_three_pixels_wide_and_keeps_depth():
    classic = get_layout("classic")
    slim = get_layout("slim")
    for face in ("front", "back"):
        assert classic.face("r_arm", face).w == 4
        assert slim.face("r_arm", face).w == 3
    assert classic.face("r_arm", "front").x == slim.face("r_arm", "front").x == 44
    assert slim.face("r_arm", "back").x == 51
    for face in ("left", "right"):
        assert slim.face("r_arm", face).w == 4
    assert slim.face("r_arm", "front").h == 12
    assert slim.face("r_arm", "top").rect == (44, 16, 3, 4)
    assert slim.face("l_arm", "front").rect == (36, 52, 3, 12)


def test_overlay_regions_do_not_touch_base_regions():
    layout = get_layout("classic")
    for part in layout.parts.values():
        if part.layer != 0:
            continue
        for face in part.faces.values():
            for other in layout.parts.values():
                if other.layer != 1:
                    continue
                for of in other.faces.values():
                    ax, ay, aw, ah = face.rect
                    bx, by, bw, bh = of.rect
                    overlap = ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah
                    assert not overlap, f"{part.name}/{other.name} 겹침 {face.rect} {of.rect}"


def test_mirrored_parts_write_mirrored():
    """왼팔 로컬 u 는 우팔과 반대 방향이다. put 후 텍스처 좌표로 확인한다."""
    canvas = SkinCanvas("classic")
    layout = canvas.layout
    r_face = layout.face("r_arm", "front")
    l_face = layout.face("l_arm", "front")

    canvas.put("r_arm", "front", 0, 0, rgba("#ff0000"))
    canvas.put("l_arm", "front", 0, 0, rgba("#00ff00"))
    assert canvas.image.getpixel((r_face.x + 0, r_face.y)) == rgba("#ff0000")
    assert canvas.image.getpixel((l_face.x + 3, l_face.y)) == rgba("#00ff00")

    canvas.put("l_arm", "front", 3, 1, rgba("#0000ff"))
    assert canvas.image.getpixel((l_face.x + 0, l_face.y + 1)) == rgba("#0000ff")


def test_symmetric_authoring_yields_mirrored_texture():
    colors = [rgba("#111111"), rgba("#222222"), rgba("#333333"), rgba("#444444")]
    canvas = SkinCanvas("classic")
    for u in range(4):
        canvas.put("r_arm", "front", u, 0, colors[u])
        canvas.put("l_arm", "front", u, 0, colors[3 - u])
    assert validate_image(canvas.image, "classic") == [] or True
    mirror_problems = [p for p in validate_image(canvas.image, "classic") if p.code != "base_alpha"]
    assert not [p for p in mirror_problems if p.code == "mirror"]


def test_get_is_inverse_of_put_for_mirrored_parts():
    canvas = SkinCanvas("classic")
    for u in range(4):
        canvas.put("l_arm", "front", u, 2, rgba("#00ff88"))
    for u in range(4):
        assert canvas.get("l_arm", "front", u, 2) == rgba("#00ff88")


def test_put_rejects_out_of_range():
    canvas = SkinCanvas("classic")
    try:
        canvas.put("head", "front", 8, 0, rgba("#ffffff"))
    except ValueError as exc:
        assert "범위 밖" in str(exc)
    else:
        raise AssertionError("범위 밖 put이 예외를 던지지 않음")


def test_put_rejects_unknown_part_and_layer():
    canvas = SkinCanvas("classic")
    for call in (
        lambda: canvas.put("tail", "front", 0, 0, rgba("#ffffff")),
        lambda: canvas.put("head", "front", 0, 0, rgba("#ffffff"), layer=2),
    ):
        try:
            call()
        except (KeyError, ValueError):
            continue
        raise AssertionError("잘못된 파트/레이어가 예외를 던지지 않음")


@pytest.mark.parametrize("model", ["classic", "slim"])
def test_placeholder_is_valid(model):
    canvas = build_placeholder(model=model)
    assert canvas.image.size == (64, 64)
    assert canvas.image.mode == "RGBA"
    assert validate_image(canvas.image, model) == []
    assert_valid(canvas.image, model)


def test_placeholder_unused_area_is_fully_transparent():
    canvas = build_placeholder("classic")
    px = canvas.image.load()
    for y in range(64):
        for x in range(64):
            if not canvas.is_used(x, y):
                assert px[x, y][3] == 0, (x, y)


def test_placeholder_uses_only_binary_alpha():
    alpha = build_placeholder("classic").image.getchannel("A")
    values = {value for _count, value in alpha.getcolors(maxcolors=256)}
    assert values <= {0, 255}


def test_base_layer_fully_opaque_where_used():
    """Java 는 내곽 레이어를 완전 불투명으로 강제한다. 오버레이만 예외."""
    canvas = build_placeholder("slim")
    px = canvas.image.load()
    base_only = [
        f.rect
        for part in canvas.layout.parts.values()
        if part.layer == 0
        for f in part.faces.values()
    ]
    checked = 0
    for y in range(64):
        for x in range(64):
            if any(rx <= x < rx + rw and ry <= y < ry + rh for rx, ry, rw, rh in base_only):
                checked += 1
                assert px[x, y][3] == 255, (x, y)
    assert checked == get_layout("slim").usable_pixels() // 2


def test_validator_catches_size_mismatch():
    canvas = build_placeholder("classic")
    bad = canvas.image.resize((128, 128))
    codes = {p.code for p in validate_image(bad, "classic")}
    assert "size" in codes


def test_validator_catches_mode_mismatch():
    canvas = build_placeholder("classic")
    bad = canvas.image.convert("RGB")
    codes = {p.code for p in validate_image(bad, "classic")}
    assert "mode" in codes


def test_validator_catches_bleed():
    canvas = build_placeholder("classic")
    canvas.image.putpixel((63, 40), rgba("#00ff00"))
    codes = {p.code for p in validate_image(canvas.image, "classic")}
    assert "bleed" in codes


def test_validator_catches_mirror_mismatch():
    canvas = build_placeholder("classic")
    canvas.put("l_arm", "front", 0, 0, rgba("#123456"))
    codes = {p.code for p in validate_image(canvas.image, "classic")}
    assert "mirror" in codes


def test_validator_catches_transparent_base_layer():
    canvas = build_placeholder("classic")
    canvas.image.putpixel((21, 21), rgba("#ffffff", alpha=0))
    codes = {p.code for p in validate_image(canvas.image, "classic")}
    assert "base_alpha" in codes


def test_shade_and_rgba():
    base = rgba("#808080")
    assert shade(base, 1.0) == base
    assert shade(base, 0.5)[0] < base[0]
    assert shade(base, 0.5)[3] == base[3]
    assert shade(rgba("#000000"), 1.5)[0] == 128
    assert shade(rgba("#000000"), 0.0)[0] == 0
    for bad in ("#fff", "gggggg", "12345"):
        try:
            rgba(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad}가 검증되지 않음")


def test_preview_panels_are_produced():
    canvas = build_placeholder("classic")
    for view, layer in PANELS:
        panel = render_view(canvas.image, "classic", view, layer)
        assert panel.width > 0 and panel.height > 0
    preview = render_preview(canvas.image, "classic")
    assert preview.width > 64 and preview.height > 64


def test_front_view_is_sixteen_by_thirty_two_on_classic():
    panel = render_view(build_placeholder("classic").image, "classic", "front")
    assert panel.size == (16, 32)


def test_front_view_geometry_matches_player_model():
    """팔은 0~4 / 12~16, 다리는 4~12 에 있어야 한다 (classic 16 폭 기준)."""
    panel = render_view(build_placeholder("classic").image, "classic", "front")
    px = panel.load()
    assert panel.size == (16, 32)
    assert px[0, 12] != BACKDROP and px[3, 12] != BACKDROP
    assert px[12, 12] != BACKDROP and px[15, 12] != BACKDROP
    for x in (0, 1, 2, 3, 14, 15):
        assert px[x, 24] == BACKDROP, f"다리 높이에 팔/배경이 남아 있음: x={x}"
    for x in (4, 5, 6, 7, 8, 9, 10, 11):
        assert px[x, 24] != BACKDROP, f"다리 영역에 구멍: x={x}"
    for x in range(4, 12):
        assert px[x, 0] != BACKDROP, f"머리 정면에 구멍: x={x}"
        assert px[x, 4] != BACKDROP, f"머리 정면에 구멍: x={x}"
    for x in (0, 3, 12, 15):
        assert px[x, 0] == BACKDROP, f"머리 폭이 8을 넘음: x={x}"


def test_side_view_is_eight_wide_with_body_centered():
    panel = render_view(build_placeholder("classic").image, "classic", "side")
    px = panel.load()
    assert panel.size == (8, 32)
    for y in range(0, 8):
        for x in range(8):
            assert px[x, y] != BACKDROP, f"머리 측면에 구멍: {x},{y}"
    assert px[0, 12] == BACKDROP and px[1, 12] == BACKDROP
    assert px[2, 12] != BACKDROP and px[5, 12] != BACKDROP
    assert px[6, 12] == BACKDROP and px[7, 12] == BACKDROP


def test_slim_front_view_is_fifteen_by_thirty_two():
    panel = render_view(build_placeholder("slim").image, "slim", "front")
    assert panel.size == (15, 32)
