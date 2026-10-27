"""S3 파라메트릭 렌더 (네트워크 없음)."""
import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PIL import Image

from skinmaker import attributes as A
from skinmaker import colors as C
from skinmaker import quality as Q
from skinmaker import render as R
from skinmaker.canvas import rgba, shade
from skinmaker.format import get_layout
from skinmaker.validate import validate_image


def sample(hex_value, share=0.5, confident=True, n=100):
    r = int(hex_value[1:3], 16)
    g = int(hex_value[3:5], 16)
    b = int(hex_value[5:7], 16)
    return C.ColorSample(hex_value, share, confident, (r, g, b), n)


def observed(skin="#e0ac69", hair="#3a2a1c", top="#2f6fb5", bottom="#3c4450", top_share=0.5):
    return C.ObservedColors(
        sample(skin), sample(hair), sample(top, top_share), sample(bottom),
        (1.0, 1.0, 1.0), True, (0.5, 0.3, 0.2),
    )


def attrs(**kw):
    base = {
        "top_garment": "tee",
        "bottom_garment": "jeans",
        "pattern": "plain",
        "sleeve_len": "short",
        "hair_length": "short",
        "hair_bbox": [200, 50, 800, 600],
    }
    base.update(kw)
    return A.validate(base)


# --- 머리 스텐신 경로 (Tier 0, 2026-10-15) -------------------------------------

import hashlib

from skinmaker import hairstencil as HS

# rule 스텐실 렌더의 픽셀 베이스라인. 2026-10-21 L2 헤어 오버레이(기본 on)로
# 재기록 — 이전: 2026-10-20 얼굴 템플릿 변경. 이후 rule 경로가 조용히 변하면 잡는다.
NOISE_OFF_GOLDEN = {
    "short": "caf97644ba68acc8",
    "medium": "ec1f203435b90f11",
    "long": "7048dd2c1f3ec782",
    "very_long": "62f319c0c36f4475",
}


@pytest.mark.parametrize("length", ["short", "medium", "long", "very_long"])
def test_rule_stencil_render_golden(length):
    canvas = R.render(observed(), attrs(hair_length=length), ())
    assert hashlib.sha256(canvas.image.tobytes()).hexdigest()[:16] == NOISE_OFF_GOLDEN[length]


def test_face_template_eyes_lowered_and_no_mouth():
    """얼굴 템플릿: 눈 4-5행(한 행 아래), 입 없음 — 사용자 결정 2026-10-20."""
    base = observed()
    canvas = R.render(base, attrs(), ())
    skin = shade(rgba(base.skin.hex), R.FACE_SHADE["front"])[:3]
    sclera = rgba("#f2f2f2")[:3]
    iris = rgba(R.DEFAULT_IRIS)[:3]
    for base_u in (1, 5):
        assert canvas.get("head", "front", base_u, 4)[:3] == sclera
        assert canvas.get("head", "front", base_u + 1, 4)[:3] == iris
        assert canvas.get("head", "front", base_u, 5)[:3] == iris
        assert canvas.get("head", "front", base_u + 1, 5)[:3] == iris
    for u in range(1, 7):  # 옛 눈 높이(3행)는 피부 (옆열은 옆머리)
        assert canvas.get("head", "front", u, 3)[:3] == skin
    for u in range(2, 6):  # 입 없음 — 6행 가운데는 피부
        assert canvas.get("head", "front", u, 6)[:3] == skin


def test_iris_color_from_photo_applied():
    base = dataclasses.replace(observed(), iris=sample("#28468c"))
    canvas = R.render(base, attrs(), ())
    assert canvas.get("head", "front", 2, 4)[:3] == (40, 70, 140)


def test_iris_unmeasured_falls_back_to_template():
    base = dataclasses.replace(observed(), iris=C.MISSING)
    canvas = R.render(base, attrs(), ())
    assert canvas.get("head", "front", 2, 4)[:3] == rgba(R.DEFAULT_IRIS)[:3]


def test_beard_full_fills_jaw_and_chin():
    """수염 full: 6-7행 전체를 머리색으로 (입이 없어 가운데도 채운다)."""
    base = observed()
    canvas = R.render(base, attrs(beard="full"), ())
    hair = shade(rgba(base.hair.hex), R.FACE_SHADE["front"])[:3]
    for v in (6, 7):
        for u in range(8):
            assert canvas.get("head", "front", u, v)[:3] == hair


def test_beard_stubble_is_muted_and_keeps_center_cheeks():
    base = observed()
    canvas = R.render(base, attrs(beard="stubble"), ())
    skin = shade(rgba(base.skin.hex), R.FACE_SHADE["front"])[:3]
    hair = shade(rgba(base.hair.hex), R.FACE_SHADE["front"])[:3]
    stubble = tuple(int(round(0.55 * h + 0.45 * s)) for h, s in zip(hair, skin))
    for u in (0, 1, 6, 7):
        assert canvas.get("head", "front", u, 6)[:3] == stubble
    for u in range(8):
        assert canvas.get("head", "front", u, 7)[:3] == stubble
    assert canvas.get("head", "front", 3, 6)[:3] == skin  # 가운데 볼은 피부


def test_layered_top_renders_collar_tie_and_cuffs():
    """겹쳐 입은 상의: 목 V·라펠에 안쪽 옷, 타이 1px, 소매 끝 커프스 (사용자 결정 2026-10-21)."""
    base = dataclasses.replace(
        observed(), inner=C.ColorSample("#e9eef3", 0.5, True, (233, 238, 243), 80),
        tie=C.ColorSample("#8a1f2a", 0.3, True, (138, 31, 42), 30),
    )
    a = attrs(top_garment="jacket", inner_top="shirt", neckwear="tie", sleeve_len="long")
    canvas = R.render(base, a, ())
    inner = rgba("#e9eef3")[:3]
    tie = rgba("#8a1f2a")[:3]
    for u in (3, 4):
        assert canvas.get("body", "front", u, 0)[:3] == inner
    assert canvas.get("body", "front", 3, 1)[:3] == inner
    assert canvas.get("body", "front", 4, 1)[:3] == tie   # 매듭
    assert canvas.get("body", "front", 3, 2)[:3] == inner
    assert canvas.get("body", "front", 4, 2)[:3] == tie   # 타이
    # 커프스: 장袖 끝행(9) 네 면이 안쪽 색
    for part in ("r_arm", "l_arm"):
        for face, factor in (("front", 1.0), ("back", 0.90), ("right", 0.84), ("left", 0.84)):
            assert canvas.get(part, face, 2, 9)[:3] == shade(rgba("#e9eef3"), factor)[:3], (part, face)


def test_single_top_keeps_skin_neck():
    """단일 상의(기본 inner_top=none)는 기존 목 = 피부 그대로 (회귀 방지)."""
    base = observed()
    canvas = R.render(base, attrs(), ())
    skin = shade(rgba(base.skin.hex), 0.86)[:3]
    assert canvas.get("body", "front", 3, 0)[:3] == skin
    assert canvas.get("body", "front", 4, 1)[:3] == skin


def test_tie_only_when_color_measured():
    """타이 색이 측정되지 않았으면 그리지 않는다 (승인 규칙)."""
    base = dataclasses.replace(observed(), inner=C.ColorSample("#e9eef3", 0.5, True, (233, 238, 243), 80))
    a = attrs(top_garment="jacket", inner_top="shirt", neckwear="tie", sleeve_len="long")
    canvas = R.render(base, a, ())
    inner = rgba("#e9eef3")[:3]
    assert canvas.get("body", "front", 4, 2)[:3] == inner  # 타이 자리도 셔츠
    assert canvas.get("body", "front", 4, 1)[:3] == inner


def test_jacket_prefers_background_rejected_outer_sample():
    """재킷/레이어드면 배경 제거 겉옷 표본을 쓴다 (흰 셔츠/배경이 상의색을 오염시키는 문제)."""
    base = dataclasses.replace(observed(), outer=sample("#24282e"))
    canvas = R.render(base, attrs(top_garment="jacket"), ())
    body = shade(rgba("#24282e"), R.FACE_SHADE["front"])[:3]
    assert canvas.get("body", "front", 2, 6)[:3] == body
    plain = R.render(dataclasses.replace(observed(), outer=sample("#24282e")), attrs(top_garment="tee"), ())
    assert plain.get("body", "front", 2, 6)[:3] == shade(rgba(observed().top.hex), R.FACE_SHADE["front"])[:3]


def test_cuffs_only_for_long_sleeves():
    base = dataclasses.replace(observed(), inner=C.ColorSample("#e9eef3", 0.5, True, (233, 238, 243), 80))
    a = attrs(top_garment="jacket", inner_top="shirt", sleeve_len="short")
    canvas = R.render(base, a, ())
    assert canvas.get("r_arm", "front", 2, 9)[:3] == shade(rgba(base.skin.hex), R.FACE_SHADE["front"])[:3]


def test_hair_overlay_volume_shell_and_fringe():
    """L2 헤어: 실루엣 복제(부피) + 가르마선 낮은 열은 1행 연장 — 눈(4-5행)은 금지."""
    base = observed()
    canvas = R.render(base, attrs(), ())
    hair = shade(rgba(base.hair.hex), R.FACE_SHADE["front"])[:3]
    for u, v in ((0, 0), (4, 1), (7, 1)):
        assert canvas.get("head", "front", u, v, 1)[:3] == hair, (u, v)
    assert canvas.get("head", "front", 4, 2, 1)[:3] == hair  # 연장 행
    for v in (4, 5):  # 눈 행은 오버레이도 비어 있다
        assert canvas.get("head", "front", 4, v, 1)[3] == 0, v
    assert canvas.get("head", "right", 0, 1, 1)[:3] == shade(rgba(base.hair.hex), R.FACE_SHADE["right"])[:3]
    assert canvas.get("head", "right", 0, 2, 1)[3] == 0  # short 옆면은 2행까지


def test_hair_overlay_body_drape_and_switch_off():
    st = dataclasses.replace(HS.rule_stencil("long"), body_rows=3)
    base = dataclasses.replace(observed(), hair_stencil=st)
    canvas = R.render(base, attrs(hair_length="long"), ())
    assert canvas.get("body", "back", 4, 2, 1)[:3] == shade(rgba(base.hair.hex), R.FACE_SHADE["back"])[:3]
    off = R.render(dataclasses.replace(base, hair_overlay=False), attrs(hair_length="long"), ())
    assert off.get("body", "back", 4, 2, 1)[3] == 0
    assert off.get("head", "front", 0, 0, 1)[3] == 0


def test_viewer_js_uv_rects_match_layout():
    """3D 뷰어의 UV rect 상수가 format.get_layout()과 일치 — L2 오프셋 드리프트 방지.

    2026-10-21 버그: 왼팔/왼다리 L2 rect 를 (0,+16)으로 밀어 텍스처 밖을 샘플링해
    한 팔·한 다리가 엉뚱한 색으로 칠해졌다. 좌표가 프론트에 중복돼 있어
    레이아웃과 대조하는 테스트로 고정한다. classic/slim 두 체형 모두 검사한다.
    """
    import re
    from pathlib import Path

    from skinmaker.format import get_layout

    js = (Path(__file__).resolve().parent.parent / "frontend/src/components/Skin3DViewer.jsx").read_text(encoding="utf-8")

    def faces(name: str) -> dict[str, tuple[int, int, int, int]]:
        m = re.search(rf"const {name} = \{{(.*?)\}};", js, re.S)
        assert m, name
        return {
            key: tuple(int(v) for v in vals.split(","))
            for key, vals in re.findall(r"(\w+): \[([\d, ]+)\]", m.group(1))
        }

    pairs = (
        ("HEAD", "head", "classic"), ("BODY", "body", "classic"), ("ARM", "r_arm", "classic"),
        ("LARM", "l_arm", "classic"), ("LEG", "r_leg", "classic"), ("LLEG", "l_leg", "classic"),
        ("SLIM_ARM", "r_arm", "slim"), ("SLIM_LARM", "l_arm", "slim"),
    )
    for js_name, part, model in pairs:
        layout = get_layout(model)
        want = {f.rect for f in layout.part(part, 0).faces.values()}
        assert set(faces(js_name).values()) == want, (part, model, "layer0")
        m2 = re.search(rf"const {js_name}2 = shiftFaces\((\w+), (-?\d+), (-?\d+)\);", js)
        assert m2, f"{js_name}2"
        base, dx, dy = faces(m2.group(1)), int(m2.group(2)), int(m2.group(3))
        shifted = {(x + dx, y + dy, w, h) for x, y, w, h in base.values()}
        want2 = {f.rect for f in layout.part(part, 1).faces.values()}
        assert shifted == want2, (part, model, "layer1", sorted(shifted ^ want2))


def test_stencil_wiring_rule_path_identical():
    """observed.hair_stencil=rule_stencil 경로가 기본 경로와 픽셀 동일."""
    base = observed()
    for length in ("short", "very_long"):
        a = attrs(hair_length=length)
        with_stencil = R.render(
            dataclasses.replace(base, hair_stencil=HS.rule_stencil(length)), a, ())
        without = R.render(base, a, ())
        assert with_stencil.image.tobytes() == without.image.tobytes(), length


def test_render_consumes_mask_stencil():
    """모호크 스텐실 → 옆/뒷면을 머리색으로 못 칠한다 (오늘은 무조건 칠했다).

    스텐실 side_rows 0 → 오른쪽 면이 피부 음영이고, rule(short) 기본과 다르다.
    """
    stencil = HS.HairStencil(
        tuple(tuple(False for _ in range(8)) for _ in range(8)), True,
        {"left": (0,) * 8, "right": (0,) * 8,
         "back": (0, 0, 0, 0, 0, 0, 0, 0)})
    base = observed()
    canvas = R.render(dataclasses.replace(base, hair_stencil=stencil), attrs(), ())
    right = canvas.get("head", "right", 3, 3)[:3]
    assert right == shade(rgba(base.skin.hex), R.FACE_SHADE["right"])[:3], right
    legacy = R.render(base, attrs(hair_length="long"), ())
    assert legacy.get("head", "right", 3, 3)[:3] != right  # 오늘(long)은 옆면 0-5행이 머리색


@pytest.mark.parametrize("model", ["classic", "slim"])
def test_mask_stencil_renders_body_back_sides_and_front_shoulder_strands(model):
    """Long mask hair reaches torso back/sides; front gets only shoulder strands, neck stays visible."""
    stencil = HS.HairStencil(
        tuple(tuple(False for _ in range(8)) for _ in range(8)), True,
        {"left": (0,) * 8, "right": (0,) * 8, "back": (0,) * 8},
        body_rows=3,
    )
    base = observed()
    canvas = R.render(dataclasses.replace(base, hair_stencil=stencil), attrs(), (), model).image
    L = get_layout(model)
    hair = rgba(base.hair.hex)[:3]
    back = L.face("body", "back", 0)
    right = L.face("body", "right", 0)
    front = L.face("body", "front", 0)

    assert canvas.getpixel((back.x + 4, back.y + 2))[:3] == shade(rgba(base.hair.hex), R.FACE_SHADE["back"])[:3]
    assert canvas.getpixel((right.x + 2, right.y + 2))[:3] == shade(rgba(base.hair.hex), R.FACE_SHADE["right"])[:3]
    for u in (0, 1, 6, 7):
        assert canvas.getpixel((front.x + u, front.y + 1))[:3] == hair
    assert canvas.getpixel((front.x + 3, front.y + 0))[:3] == shade(rgba(base.skin.hex), 0.86)[:3]
    assert canvas.getpixel((front.x + 4, front.y + 1))[:3] == shade(rgba(base.skin.hex), 0.86)[:3]
    assert canvas.getpixel((front.x + 3, front.y + 2))[:3] == shade(rgba(base.top.hex), R.FACE_SHADE["front"])[:3]
    assert validate_image(canvas, model) == []


@pytest.mark.parametrize("model", ["classic", "slim"])
def test_render_is_valid(model):
    canvas = R.render(observed(), attrs(), (), model)
    assert validate_image(canvas.image, model) == []


@pytest.mark.parametrize("model", ["classic", "slim"])
def test_head_overlay_empty_when_switch_off(model):
    """L2 스위치 off면 HEAD ACC.는 투명 — 기본(on)은 L2 헤어가 들어간다 (2026-10-21)."""
    canvas = R.render(dataclasses.replace(observed(), hair_overlay=False), attrs(), (), model)
    px = canvas.image.load()
    for face in canvas.layout.part("head", 1).faces.values():
        for y in range(face.y, face.y + face.h):
            for x in range(face.x, face.x + face.w):
                assert px[x, y][3] == 0


def test_hair_base_always_painted_and_overlay_follows_switch():
    """기본 머리는 항상 레이어 0. L2 헤어는 스위치 off면 비어 있다 (2026-10-21)."""
    canvas = R.render(observed(hair="#112233"), attrs(hair_length="long"), (), "classic")
    hair = rgba("#112233")
    front = canvas.layout.face("head", "front", 0)
    assert canvas.image.getpixel((front.x + 4, front.y + 0))[:3] == shade(hair, 1.0)[:3]
    off = R.render(dataclasses.replace(observed(hair="#112233"), hair_overlay=False),
                   attrs(hair_length="long"), (), "classic")
    overlay = off.layout.face("head", "front", 1)
    assert off.image.getpixel((overlay.x + 4, overlay.y + 0))[3] == 0


def test_long_hair_covers_more_than_short():
    short = R.render(observed(), attrs(hair_length="short"), (), "classic")
    long = R.render(observed(), attrs(hair_length="very_long"), (), "classic")
    back = get_layout("classic").face("head", "back", 0)
    x, y = back.x + 2, back.y + 6
    assert short.image.getpixel((x, y)) != long.image.getpixel((x, y))
    assert long.image.getpixel((x, y))[:3] == shade(rgba("#3a2a1c"), 0.90)[:3]


def test_sleeve_long_vs_short():
    short = R.render(observed(), attrs(sleeve_len="short"), (), "classic")
    long = R.render(observed(), attrs(sleeve_len="long"), (), "classic")
    f = get_layout("classic").face("r_arm", "front", 0)
    # v=5: short는 피부, long은 셔츠
    assert short.image.getpixel((f.x + 1, f.y + 5)) != long.image.getpixel((f.x + 1, f.y + 5))
    # 손(v=11)은 둘 다 피부
    skin_hand = shade(rgba("#e0ac69"), 1.0)
    assert long.image.getpixel((f.x + 1, f.y + 11))[:3] == skin_hand[:3]


def test_top_none_renders_bare_body():
    canvas = R.render(observed(), attrs(top_garment="none", sleeve_len="none"), (), "classic")
    f = get_layout("classic").face("body", "front", 0)
    assert canvas.image.getpixel((f.x + 1, f.y + 6))[:3] == shade(rgba("#e0ac69"), 1.0)[:3]


def test_graphic_back_is_plain_while_front_has_print():
    canvas = R.render(observed(), attrs(pattern="graphic"), (), "classic")
    front = get_layout("classic").face("body", "front", 0)
    back = get_layout("classic").face("body", "back", 0)
    assert canvas.image.getpixel((front.x + 4, front.y + 6))[:3] == (242, 242, 242)
    assert canvas.image.getpixel((back.x + 4, back.y + 6))[:3] != (242, 242, 242)


def test_stripe_reaches_back_but_graphic_does_not():
    stripe = R.render(observed(top="#445566"), attrs(pattern="vertical_stripe"), (), "classic")
    front = get_layout("classic").face("body", "front", 0)
    back = get_layout("classic").face("body", "back", 0)
    assert stripe.image.getpixel((front.x + 0, front.y + 6)) != stripe.image.getpixel((front.x + 2, front.y + 6))
    assert stripe.image.getpixel((back.x + 0, back.y + 6)) != stripe.image.getpixel((back.x + 2, back.y + 6))


def test_degrade_forces_plain():
    obs = observed(top="#445566")
    patterned = R.render(obs, attrs(pattern="check"), (), "classic")
    conservative = R.render(obs, attrs(pattern="check"), ("blur",), "classic")
    f = get_layout("classic").face("body", "front", 0)
    assert patterned.image.getpixel((f.x + 0, f.y + 6)) != patterned.image.getpixel((f.x + 2, f.y + 6))
    assert conservative.image.getpixel((f.x + 0, f.y + 6)) == conservative.image.getpixel((f.x + 2, f.y + 6))


def test_uncertain_pattern_forces_plain():
    obs = observed(top="#445566")
    bad = dict(top_garment="tee", bottom_garment="jeans", pattern="???", sleeve_len="short",
                hair_length="short", hair_bbox=[200, 50, 800, 600])
    canvas = R.render(obs, A.validate(bad), (), "classic")
    f = get_layout("classic").face("body", "front", 0)
    assert canvas.image.getpixel((f.x + 0, f.y + 6)) == canvas.image.getpixel((f.x + 2, f.y + 6))


def test_measured_stripes_render_without_vlm():
    """S2 없이 S1 측정만으로 줄무늬. EMPTY attrs(pattern missing) + top_alt."""
    from skinmaker.attributes import EMPTY

    obs = observed(top="#223795")
    alt = sample("#91203b")
    obs2 = C.ObservedColors(obs.skin, obs.hair, obs.top, obs.bottom,
                            obs.wb_gain, obs.wb_confident, obs.skin_chroma, alt, "vertical_stripe")
    canvas = R.render(obs2, EMPTY, (), "classic")
    f = get_layout("classic").face("body", "front", 0)
    cols = {canvas.image.getpixel((f.x + u, f.y + 6))[:3] for u in range(f.w)}
    assert len(cols) > 1
    assert shade(rgba("#91203b"), 1.0)[:3] in cols


def test_measured_stripes_survive_small_flag():
    """얼굴이 작아도 몸통 픽셀이 충분하면 측정 줄무늬를 쓴다 (메시 회귀)."""
    from skinmaker.attributes import EMPTY

    obs = observed(top="#223795")
    alt = sample("#a52847")
    obs2 = C.ObservedColors(obs.skin, obs.hair, obs.top, obs.bottom,
                            obs.wb_gain, obs.wb_confident, obs.skin_chroma, alt, "vertical_stripe")
    canvas = R.render(obs2, EMPTY, ("small",), "classic")
    f = get_layout("classic").face("body", "front", 0)
    cols = {canvas.image.getpixel((f.x + u, f.y + 6))[:3] for u in range(f.w)}
    assert len(cols) > 1


def test_vlm_pattern_wins_over_measurement():
    obs = observed(top="#445566")
    alt = sample("#778899")
    obs2 = C.ObservedColors(obs.skin, obs.hair, obs.top, obs.bottom,
                            obs.wb_gain, obs.wb_confident, obs.skin_chroma, alt, "vertical_stripe")
    canvas = R.render(obs2, attrs(pattern="check"), (), "classic")
    f = get_layout("classic").face("body", "front", 0)
    assert canvas.image.getpixel((f.x + 0, f.y + 6)) != canvas.image.getpixel((f.x + 2, f.y + 6))


def test_vlm_plain_vetoes_measured_stripes():
    """확신된 plain 은 측정 줄무늬를 끈다. 겹쳐 입은 두 벌을 줄무늬로 착각하는 경우."""
    obs = observed(top="#632214")
    alt = sample("#67726f")
    obs2 = C.ObservedColors(obs.skin, obs.hair, obs.top, obs.bottom,
                            obs.wb_gain, obs.wb_confident, obs.skin_chroma, alt, "vertical_stripe")
    canvas = R.render(obs2, attrs(pattern="plain"), (), "classic")
    f = get_layout("classic").face("body", "front", 0)
    cols = {canvas.image.getpixel((f.x + u, f.y + 6))[:3] for u in range(f.w)}
    assert len(cols) == 1


def test_shorts_renders_skin_between_pants_and_shoe():
    canvas = R.render(observed(), attrs(bottom_garment="shorts"), (), "classic")
    f = get_layout("classic").face("r_leg", "front", 0)
    assert canvas.image.getpixel((f.x + 1, f.y + 2))[:3] == shade(rgba("#3c4450"), 1.0)[:3]
    assert canvas.image.getpixel((f.x + 1, f.y + 7))[:3] == shade(rgba("#e0ac69"), 1.0)[:3]


def test_shoes_two_tone_top_and_sole():
    """폴리시 C: 신발 블록은 2톤 — 윗부분(바닥 직전 행까지)은 밝게, 바닥 행은 어둡게.
    단색 블록이 신발로 안 읽히는 문제를 고친다. 측정 신발색에서 톤을 파생한다.
    """
    obs = dataclasses.replace(observed(), shoe=sample("#9a5a30"))
    canvas = R.render(obs, attrs(bottom_garment="pants"), (), "classic")
    f = get_layout("classic").face("r_leg", "front", 0)
    shoe = rgba("#9a5a30")  # front face shade 1.0 → 신발색 그대로에서 톤 파생
    top = canvas.image.getpixel((f.x + 1, f.y + 9))[:3]
    sole = canvas.image.getpixel((f.x + 1, f.y + 11))[:3]
    assert top == shade(shoe, 1.35)[:3], top
    assert sole == shade(shoe, 0.62)[:3], sole
    assert top != sole


def test_shoe_two_tone_off_is_flat():
    """토글 OFF 변형: 신발이 구 단색(shade(shoe, FACE_SHADE))으로 돌아간다."""
    obs = dataclasses.replace(observed(), shoe=sample("#9a5a30"))
    canvas = R.render(obs, attrs(bottom_garment="pants"), (), "classic", shoe_two_tone=False)
    f = get_layout("classic").face("r_leg", "front", 0)
    shoe = rgba("#9a5a30")
    for v in (9, 10, 11):
        c = canvas.image.getpixel((f.x + 1, f.y + v))[:3]
        assert c == shade(shoe, 1.0)[:3], (v, c)


# --- 하체 미관측 → jeans 기본 (사용자 요청 2026-10-13) ----------------------

def test_resolve_bottom_defaults_jeans_when_lower_body_unseen():
    obs = dataclasses.replace(observed(), lower_body_seen=False)
    assert R.resolve_bottom(attrs(bottom_garment="none"), obs) == "jeans"


def test_resolve_bottom_keeps_none_when_legs_visible():
    """맨다리가 보이는 전신 사진은 여전히 none (설계 D3 유지)."""
    obs = dataclasses.replace(observed(), lower_body_seen=True)
    assert R.resolve_bottom(attrs(bottom_garment="none"), obs) == "none"


def test_resolve_bottom_dress_guard():
    """드레스 아래 청바지가 밀려 나오지 않게 — dress면 none 유지."""
    obs = dataclasses.replace(observed(), lower_body_seen=False)
    assert R.resolve_bottom(attrs(bottom_garment="none", top_garment="dress"), obs) == "none"


def test_render_jeans_default_colour_and_rows():
    obs = dataclasses.replace(observed(), lower_body_seen=False)
    canvas = R.render(obs, attrs(bottom_garment="none"), (), "classic")
    f = get_layout("classic").face("r_leg", "front", 0)
    jeans = shade(rgba(R.DEFAULT_JEANS), 1.0)[:3]
    for v in range(9):
        assert canvas.image.getpixel((f.x + 1, f.y + v))[:3] == jeans, v
    shoe = rgba("#2b2b2b")  # 관측 shoe 없음 → SHOE 폴백
    assert canvas.image.getpixel((f.x + 1, f.y + 9))[:3] == shade(shoe, 1.35)[:3]
    assert canvas.image.getpixel((f.x + 1, f.y + 11))[:3] == shade(shoe, 0.62)[:3]


# --- 텍스처 노이즈 (설계 §2: 이산 톤 밴딩, 거울 대칭, 결정론 시드) -----------

def test_noise_same_seed_same_texture():
    a = R.render(observed(), attrs(), (), "classic", noise_seed=7)
    b = R.render(observed(), attrs(), (), "classic", noise_seed=7)
    assert a.image.tobytes() == b.image.tobytes()


def test_noise_changes_pixels():
    flat = R.render(observed(), attrs(), (), "classic")
    noisy = R.render(observed(), attrs(), (), "classic", noise_seed=7)
    f = get_layout("classic").face("body", "front", 0)
    assert any(
        flat.image.getpixel((f.x + u, f.y + v)) != noisy.image.getpixel((f.x + u, f.y + v))
        for u in range(f.w) for v in range(f.h)
    )


def test_noise_seed_varies():
    a = R.render(observed(), attrs(), (), "classic", noise_seed=7)
    b = R.render(observed(), attrs(), (), "classic", noise_seed=8)
    f = get_layout("classic").face("body", "front", 0)
    assert any(
        a.image.getpixel((f.x + u, f.y + v)) != b.image.getpixel((f.x + u, f.y + v))
        for u in range(f.w) for v in range(f.h)
    )


@pytest.mark.parametrize("top,bottom", [("shirt", "pants"), ("none", "skirt"), ("jacket", "jeans")])
def test_noise_passes_validate(top, bottom):
    canvas = R.render(observed(), attrs(top_garment=top, bottom_garment=bottom), (), "classic", noise_seed=42)
    assert validate_image(canvas.image, "classic") == []


def test_noise_asymmetric_pair():
    """개정 (2026-10-12 사용자 피드백): 노이즈는 좌우 비대칭 — 거울 면 텍스처가
    달라질 수 있다 (validate mirror는 이제 톨러런스로 판정한다)."""
    from skinmaker.format import get_layout

    layout = get_layout("classic")
    canvas = R.render(observed(), attrs(), (), "classic", noise_seed=7)
    rf = layout.face("r_leg", "front", 0)
    lf = layout.face("l_leg", "front", 0)
    rp = canvas.image.crop((rf.x, rf.y, rf.x + rf.w, rf.y + rf.h))
    lp = canvas.image.crop((lf.x, lf.y, lf.x + lf.w, lf.y + lf.h))
    assert rp.tobytes() != lp.tobytes()


def test_noise_irregular_clustering():
    """단일 전면 계수가 아니다: body front 면에 서로 다른 톤 밴드가 섞인다."""
    canvas = R.render(observed(), attrs(), (), "classic", noise_seed=7)
    f = get_layout("classic").face("body", "front", 0)
    tones = {canvas.image.getpixel((f.x + u, f.y + v)) for u in range(f.w) for v in range(f.h)}
    assert len(tones) >= 3, tones


# --- 노이즈 세기 noise_level (설계 §9) --------------------------------------

def test_noise_level_zero_is_byte_identical_to_noiseless():
    a = R.render(observed(), attrs(), (), "classic", noise_seed=7, noise_level=0.0)
    b = R.render(observed(), attrs(), (), "classic")
    assert a.image.tobytes() == b.image.tobytes()


def test_noise_level_one_is_default():
    a = R.render(observed(), attrs(), (), "classic", noise_seed=7, noise_level=1.0)
    b = R.render(observed(), attrs(), (), "classic", noise_seed=7)
    assert a.image.tobytes() == b.image.tobytes()


def test_noise_level_scaled_step_helper():
    assert R._scaled_step(0.92, 0.5) == 0.96
    assert R._scaled_step(1.08, 0.5) == 1.04
    assert R._scaled_step(1.0, 0.7) == 1.0
    assert R._scaled_step(0.92, 0.0) == 1.0
    assert R._scaled_step(1.08, 0.0) == 1.0


def test_noise_level_monotone_between():
    """톤된 픽셀의 값은 레벨에 따라 기저색과 최대치 사이에 놓인다 (단조)."""
    base = R.render(observed(), attrs(), (), "classic")
    half = R.render(observed(), attrs(), (), "classic", noise_seed=7, noise_level=0.5)
    full = R.render(observed(), attrs(), (), "classic", noise_seed=7)
    bp, hp, fp = base.image.load(), half.image.load(), full.image.load()
    for y in range(64):
        for x in range(64):
            b, h, f = bp[x, y], hp[x, y], fp[x, y]
            if f == b:
                continue  # 톤 안 된 픽셀
            for ch in range(3):
                lo, hi = sorted((b[ch], f[ch]))
                assert lo <= h[ch] <= hi, (x, y, ch, b, h, f)


def test_noise_level_pattern_cells_invariant():
    """톤 '대상 셀'은 레벨과 무관 — 낮은 레벨에서 달라진 픽셀 집합은
    레벨 1의 집합의 부분집합 (라운딩으로 사라질 수는 있어도 생겨나지는 않는다)."""
    base = R.render(observed(), attrs(), (), "classic")
    lo = R.render(observed(), attrs(), (), "classic", noise_seed=7, noise_level=0.3)
    hi = R.render(observed(), attrs(), (), "classic", noise_seed=7)
    bp, lp, hp = base.image.load(), lo.image.load(), hi.image.load()
    lo_set = {(x, y) for y in range(64) for x in range(64) if lp[x, y] != bp[x, y]}
    hi_set = {(x, y) for y in range(64) for x in range(64) if hp[x, y] != bp[x, y]}
    assert lo_set <= hi_set
    assert len(hi_set) > 0



def test_render_uses_only_binary_alpha():
    alpha = R.render(observed(), attrs(), (), "classic").image.getchannel("A")
    assert {v for _, v in alpha.getcolors(maxcolors=256)} <= {0, 255}


@pytest.mark.parametrize("top", ["tee", "hoodie", "jacket", "shirt", "sweater", "vest", "uniform", "apron", "overalls", "dress", "none"])
@pytest.mark.parametrize("bottom", ["jeans", "shorts", "skirt", "pants", "none"])
def test_all_garment_combos_valid(top, bottom):
    sleeve = "none" if top == "none" else "short"
    canvas = R.render(observed(), attrs(top_garment=top, bottom_garment=bottom, sleeve_len=sleeve), (), "classic")
    assert validate_image(canvas.image, "classic") == []
