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
from skinmaker import texture as TX


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

# rule 스텐실 렌더의 픽셀 베이스라인. 2026-10-27 L2 헤어를 성긴 가닥으로 개정하며
# 재기록 — 2026-11-01 chin-row flip + reference body drape (이전: reference L1 shape/tones/L2). 이전: 2026-10-21 L2 부피 셸 도입. 이후 rule 경로가 조용히 변하면 잡는다.
NOISE_OFF_GOLDEN = {
    "short": "f9d45ddc0d3b6ab1",
    "medium": "d4419820289f130a",
    "long": "aad4f2e43b6ed7a0",
    "very_long": "54bd7befaed3252e",
}


@pytest.mark.parametrize("length", ["short", "medium", "long", "very_long"])
def test_rule_stencil_render_golden(length):
    canvas = R.render(observed(), attrs(hair_length=length), ())
    assert hashlib.sha256(canvas.image.tobytes()).hexdigest()[:16] == NOISE_OFF_GOLDEN[length]

def _hairish(px, hair_hex: str, face: str, tol: int = 45) -> bool:
    """Within the reference strand-shading range of the flat hair shade."""
    ref = shade(rgba(hair_hex), R.FACE_SHADE[face])[:3]
    return max(abs(a - b) for a, b in zip(px[:3], ref)) <= tol



def test_face_template_eyes_lowered_and_no_mouth(monkeypatch):
    """Eyes occupy rows 5-6; only row 7 remains below them. No mouth."""
    monkeypatch.setattr(R.RP, "load_pack", lambda: None)
    base = observed()
    canvas = R.render(base, attrs(), ())
    skin = shade(rgba(base.skin.hex), R.FACE_SHADE["front"])[:3]
    sclera = rgba("#f2f2f2")[:3]
    iris = rgba(R.DEFAULT_IRIS)[:3]
    for base_u in (1, 5):
        assert canvas.get("head", "front", base_u, 5)[:3] == sclera
        assert canvas.get("head", "front", base_u + 1, 5)[:3] == iris
        assert canvas.get("head", "front", base_u, 6)[:3] == iris
        assert canvas.get("head", "front", base_u + 1, 6)[:3] == iris
    for u in (3, 4):  # old eye rows / mouth area are skin
        assert canvas.get("head", "front", u, 3)[:3] == skin
        assert canvas.get("head", "front", u, 4)[:3] == skin
    for u in range(2, 6):  # single chin row below eyes
        assert canvas.get("head", "front", u, 7)[:3] == skin


def test_iris_color_from_photo_applied(monkeypatch):
    monkeypatch.setattr(R.RP, "load_pack", lambda: None)
    base = dataclasses.replace(observed(), iris=sample("#28468c"))
    canvas = R.render(base, attrs(), ())
    assert canvas.get("head", "front", 2, 6)[:3] == (40, 70, 140)


def test_iris_unmeasured_falls_back_to_template(monkeypatch):
    monkeypatch.setattr(R.RP, "load_pack", lambda: None)
    base = dataclasses.replace(observed(), iris=C.MISSING)
    canvas = R.render(base, attrs(), ())
    assert canvas.get("head", "front", 2, 6)[:3] == rgba(R.DEFAULT_IRIS)[:3]


def test_beard_is_not_drawn():
    """Beard classification is kept for compatibility, but the renderer never paints it."""
    base = observed()
    skin = shade(rgba(base.skin.hex), R.FACE_SHADE["front"])[:3]
    for beard in ("full", "stubble"):
        canvas = R.render(base, attrs(beard=beard), ())
        for u in range(8):  # eyes occupy row 6; row 7 must remain chin skin
            assert canvas.get("head", "front", u, 7)[:3] == skin, (beard, u, 7)
        for u in (3, 4):
            assert canvas.get("head", "front", u, 6)[:3] == skin, (beard, u, 6)


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


def _opaque_cells(canvas, part: str, layer: int) -> set[tuple[str, int, int]]:
    cells = set()
    for face in canvas.layout.part(part, layer).faces.values():
        for v in range(face.h):
            for u in range(face.w):
                if canvas.image.getpixel((face.x + u, face.y + v))[3]:
                    cells.add((face.name, u, v))
    return cells


def test_hair_overlay_is_reference_sculpt_not_silhouette_copy():
    """L2 is a sparse reference sculpt over L1 (2026-11-01: solid shell → template)."""
    base = observed(hair="#112233")
    canvas = R.render(base, attrs(hair_length="short"), ())
    from skinmaker import reference_pack as RP
    stencil = HS.reference_stencil(RP.select_l1_shape(RP.load_pack(), "short"), HS.rule_stencil("short"))

    l1_cells = sum(1 for row in stencil.front for on in row if on) + 64
    l1_cells += sum(sum(stencil.side_profiles[f]) for f in ("right", "back", "left"))
    l2_cells = sum(1 for (face, _, _) in _opaque_cells(canvas, "head", 1) if face != "bottom")
    assert 0 < l2_cells < 0.5 * l1_cells  # not a copy of the L1 silhouette
    top = sum(1 for (face, _, _) in _opaque_cells(canvas, "head", 1) if face == "top")
    assert top <= 0.3 * 64

    # 눈(5-6행)은 L2 로 덮지 않는다.
    for u in range(1, 7):
        for v in (5, 6):
            assert canvas.get("head", "front", u, v, 1)[3] == 0, (u, v)

    # L1 은 on/off 와 무관하게 픽셀 동일.
    off = R.render(dataclasses.replace(base, hair_overlay=False), attrs(hair_length="short"), ())
    for part in ("head", "body"):
        for face in canvas.layout.part(part, 0).faces.values():
            for v in range(face.h):
                for u in range(face.w):
                    assert (canvas.image.getpixel((face.x + u, face.y + v))
                            == off.image.getpixel((face.x + u, face.y + v))), (part, face.name, u, v)


def test_hair_overlay_body_drape_is_reference_strands_and_switch_off():
    """Body L2 = reference strand template over the L1 drape, not a solid copy."""
    base = observed()
    canvas = R.render(base, attrs(hair_length="long", hair_style="long_straight"), ())
    cells = _opaque_cells(canvas, "body", 1)
    back = {(u, v) for (face, u, v) in cells if face == "back"}
    assert back and len(back) < 0.6 * 8 * 12  # sparse bands, L1 shows between
    assert {u for u, _ in back} <= {1, 2, 3, 4, 5, 6}  # outer columns stay L1
    for face, u, v in cells:  # every strand sits on L1 drape hair
        assert _hairish(canvas.get("body", face, u, v, 0), base.hair.hex, face), (face, u, v)
    off = R.render(dataclasses.replace(base, hair_overlay=False), attrs(hair_length="long"), ())
    assert not _opaque_cells(off, "body", 1)
    assert off.get("head", "front", 0, 0, 1)[3] == 0


def test_head_bottom_rear_is_hair_and_chin_is_skin():
    from skinmaker.render import FACE_SHADE
    for length, rear in (("short", 1), ("long", 3), ("very_long", 4)):
        canvas = R.render(observed(hair="#112233"), attrs(hair_length=length), ())
        hair = shade(rgba("#112233"), FACE_SHADE["bottom"])[:3]
        skin = shade(rgba(observed().skin.hex), FACE_SHADE["bottom"])[:3]
        for v in range(8):  # physical rows: v0 = chin, v7 = back
            for u in (3, 4):
                got = canvas.get("head", "bottom", u, R.bottom_row(v))[:3]
                if v >= 8 - rear:
                    assert got == hair, (length, u, v, got)
                else:
                    assert got == skin, (length, u, v, got)


def test_long_hair_extends_body_drape_and_bangs():
    short = R.render(observed(hair="#112233"), attrs(hair_length="short"), ())
    long = R.render(observed(hair="#112233"), attrs(hair_length="long", hair_style="long_straight"), ())
    # Reference drape: back to the waist (u0/u7 11 rows), chest locks u0-1/u6-7.
    for v in range(11):
        assert _hairish(long.get("body", "back", 0, v), "#112233", "back"), v
    assert not _hairish(long.get("body", "back", 0, 11), "#112233", "back")
    for v in range(10):
        assert _hairish(long.get("body", "front", 1, v), "#112233", "front"), v
    assert not _hairish(long.get("body", "front", 3, 3), "#112233", "front")
    # Head L1 hair carries reference strand shading (2026-11-01): near, not equal.
    hair_front = shade(rgba("#112233"), R.FACE_SHADE["front"])[:3]
    for u in (2, 5):
        assert sum(abs(a - b) for a, b in zip(long.get("head", "front", u, 4)[:3], hair_front)) <= 45
    skin_front = shade(rgba(observed().skin.hex), R.FACE_SHADE["front"])[:3]
    for u in (1, 6):
        assert long.get("head", "front", u, 4)[:3] == skin_front
    assert not _hairish(short.get("body", "back", 0, 0), "#112233", "back")


def test_hood_up_hides_back_drape_and_keeps_chest_locks():
    """Hood up covers the back of the head/upper back: no hair down the back.
    The chest locks stay and must start at the shoulder — the hood cowl is
    clothing and the hair falls over it (regression: locks were cut two rows
    below the head in production)."""
    base = observed(hair="#112233")
    kw = dict(top_garment="hoodie", hair_length="long", hair_style="long_straight")
    bare = R.render(base, attrs(hood="none", **kw), ())
    up = R.render(base, attrs(hood="up", **kw), ())

    assert _hairish(bare.get("body", "back", 3, 6), base.hair.hex, "back")
    for u in range(8):
        for v in range(12):
            assert not _hairish(up.get("body", "back", u, v), base.hair.hex, "back"), (u, v)

    for u in (0, 1, 6, 7):
        l2 = up.get("body", "front", u, 0, 1)
        visible = l2 if l2[3] else up.get("body", "front", u, 0, 0)
        assert _hairish(visible, base.hair.hex, "front"), (u, visible)


def test_hood_up_keeps_only_chest_facing_side_lock():
    """Side faces author u in the same order as the head: right u0=back,
    left u0=front. Hood up keeps the chest-facing edge column, drops the back."""
    base = observed(hair="#112233")
    up = R.render(base, attrs(top_garment="hoodie", hair_length="long",
                              hair_style="long_straight", hood="up"), ())
    assert not _hairish(up.get("body", "right", 0, 6), base.hair.hex, "right")
    assert _hairish(up.get("body", "right", 3, 6), base.hair.hex, "right")
    assert not _hairish(up.get("body", "left", 3, 6), base.hair.hex, "left")
    assert _hairish(up.get("body", "left", 0, 6), base.hair.hex, "left")


def test_hood_down_uses_head_mask_without_body_front_cowl():
    """Final head-only masks replace the pack cowl: hood down paints head L2
    nape/sides and a one-row upper-back fold, with no body-front cowl."""
    canvas = R.render(observed(), attrs(top_garment="hoodie", hood="down"), ())
    no_hood = R.render(observed(), attrs(top_garment="hoodie", hood="none"), ())
    for v in range(12):
        for u in range(8):
            assert canvas.get("body", "front", u, v, 1) == no_hood.get("body", "front", u, v, 1), (u, v)
    for u in range(8):
        assert canvas.get("body", "back", u, 0, 1)[3] == 255
    for u in (2, 3, 4, 5):
        assert canvas.get("body", "back", u, 1, 1)[3] == 255
    for u in range(8):
        assert canvas.get("head", "back", u, 7, 1)[3] == 255


def test_viewer_js_uv_rects_match_layout():
    """3D 모델의 UV rect 상수(skinModel.js)가 format.get_layout()과 일치 — 드리프트 방지.

    2026-10-21 버그: 왼팔/왼다리 L2 rect 를 (0,+16)으로 밀어 텍스처 밖을 샘플링해
    한 팔·한 다리가 엉뚱한 색으로 칠해졌다. 좌표가 프론트에 중복돼 있어
    레이아웃과 대조하는 테스트로 고정한다. classic/slim 두 체형 모두 검사한다.
    2026-10-27: 뷰어와 QA 하네스가 같은 skinModel.js 를 쓰도록 추출 — 검사 대상도 그 파일이다.
    """
    import re
    from pathlib import Path

    from skinmaker.format import get_layout

    js = (Path(__file__).resolve().parent.parent / "frontend/src/skinModel.js").read_text(encoding="utf-8")

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


def test_render_consumes_mask_stencil_evidence_not_shape():
    """2026-11-01: the photo stencil supplies evidence (bald, length, bangs);
    the silhouette comes from the reference skeleton."""
    bald = HS.HairStencil(
        tuple(tuple(False for _ in range(8)) for _ in range(8)), False,
        {"left": (0,) * 8, "right": (0,) * 8, "back": (0,) * 8})
    base = observed()
    skin_right = shade(rgba(base.skin.hex), R.FACE_SHADE["right"])[:3]
    canvas = R.render(dataclasses.replace(base, hair_stencil=bald), attrs(), ())
    assert canvas.get("head", "right", 3, 3)[:3] == skin_right  # bald stays bald
    mohawk = dataclasses.replace(bald, top_hair=True)
    canvas = R.render(dataclasses.replace(base, hair_stencil=mohawk), attrs(), ())
    assert canvas.get("head", "right", 3, 3)[:3] != skin_right  # reference full sides


@pytest.mark.parametrize("model", ["classic", "slim"])
def test_mask_stencil_renders_body_back_sides_and_front_shoulder_strands(model):
    """Long mask hair reaches torso back/sides; front gets only shoulder strands, neck stays visible."""
    stencil = HS.HairStencil(
        tuple(tuple(False for _ in range(8)) for _ in range(8)), True,
        {"left": (0,) * 8, "right": (0,) * 8, "back": (0,) * 8},
        body_rows=3,
    )
    base = observed()
    canvas = R.render(dataclasses.replace(base, hair_stencil=stencil),
                          attrs(hair_length="long", hair_style="long_straight"), (), model).image
    L = get_layout(model)
    hair = rgba(base.hair.hex)[:3]
    back = L.face("body", "back", 0)
    right = L.face("body", "right", 0)
    front = L.face("body", "front", 0)

    # Reference drape (2026-11-01): full back, side edge columns, chest locks.
    assert _hairish(canvas.getpixel((back.x + 4, back.y + 2)), base.hair.hex, "back")
    assert _hairish(canvas.getpixel((right.x + 0, right.y + 2)), base.hair.hex, "right")
    for u in (0, 1, 6, 7):
        assert _hairish(canvas.getpixel((front.x + u, front.y + 1)), base.hair.hex, "front")
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
    """Reference heads have a full back for short hair too; length shows in the
    body drape and the ear notch (short exposes ears, long covers them)."""
    short = R.render(observed(), attrs(hair_length="short"), (), "classic")
    long = R.render(observed(), attrs(hair_length="very_long"), (), "classic")
    skin = shade(rgba(observed().skin.hex), R.FACE_SHADE["back"])[:3]
    for c in (short, long):
        assert all(c.get("head", "back", u, 7)[:3] != skin for u in range(8))
    assert long.get("body", "back", 2, 0)[:3] != short.get("body", "back", 2, 0)[:3]
    skin_r = shade(rgba(observed().skin.hex), R.FACE_SHADE["right"])[:3]
    assert short.get("head", "right", 5, 5)[:3] == skin_r  # ear notch
    assert long.get("head", "right", 5, 5)[:3] != skin_r

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


def test_graphic_has_no_placeholder_square():
    """graphic 태그만으로는 회색 사각형을 그리지 않는다 (2026-10-28).

    세부 정보가 없으면 측정 상의색 단색으로 접는다 — Phase 3 의 크롭 텍스처가
    있으면 그쪽이 실제 무늬를 공급한다.
    """
    obs = observed()
    canvas = R.render(obs, attrs(pattern="graphic"), (), "classic")
    front = get_layout("classic").face("body", "front", 0)
    base = shade(rgba(obs.top.hex), R.FACE_SHADE["front"])[:3]
    neck = {(3, 0), (4, 0), (3, 1), (4, 1)}  # inner_top=none → 맨목
    for v in range(12):
        for u in range(8):
            got = canvas.image.getpixel((front.x + u, front.y + v))[:3]
            assert got != (242, 242, 242), (u, v)
            if (u, v) not in neck:
                assert got == base, (u, v, got, base)


def test_stripe_defaults_to_one_pixel():
    canvas = R.render(observed(top="#445566"), attrs(pattern="vertical_stripe"), (), "classic")
    f = get_layout("classic").face("body", "front", 0)
    cols = [canvas.image.getpixel((f.x + u, f.y + 6))[:3] for u in range(4)]
    assert cols[0] != cols[1] and cols[1] != cols[2], cols


def test_stripe_thickness_follows_measurement():
    obs = dataclasses.replace(observed(top="#445566"), stripe_px=2)
    canvas = R.render(obs, attrs(pattern="vertical_stripe"), (), "classic")
    f = get_layout("classic").face("body", "front", 0)
    cols = [canvas.image.getpixel((f.x + u, f.y + 6))[:3] for u in range(4)]
    assert cols[0] == cols[1] and cols[1] != cols[2], cols


def test_check_defaults_to_one_pixel():
    canvas = R.render(observed(top="#445566"), attrs(pattern="check"), (), "classic")
    f = get_layout("classic").face("body", "front", 0)
    assert canvas.image.getpixel((f.x + 0, f.y + 6)) != canvas.image.getpixel((f.x + 1, f.y + 6))


def test_stripe_reaches_back_but_graphic_does_not():
    stripe = R.render(observed(top="#445566"), attrs(pattern="vertical_stripe"), (), "classic")
    front = get_layout("classic").face("body", "front", 0)
    back = get_layout("classic").face("body", "back", 0)
    assert stripe.image.getpixel((front.x + 0, front.y + 6)) != stripe.image.getpixel((front.x + 1, front.y + 6))
    assert stripe.image.getpixel((back.x + 0, back.y + 6)) != stripe.image.getpixel((back.x + 1, back.y + 6))


def test_degrade_forces_plain():
    obs = observed(top="#445566")
    patterned = R.render(obs, attrs(pattern="check"), (), "classic")
    conservative = R.render(obs, attrs(pattern="check"), ("blur",), "classic")
    f = get_layout("classic").face("body", "front", 0)
    assert patterned.image.getpixel((f.x + 0, f.y + 6)) != patterned.image.getpixel((f.x + 1, f.y + 6))
    assert conservative.image.getpixel((f.x + 0, f.y + 6)) == conservative.image.getpixel((f.x + 1, f.y + 6))


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
    assert canvas.image.getpixel((f.x + 0, f.y + 6)) != canvas.image.getpixel((f.x + 1, f.y + 6))


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

def _flags(**kw):
    """관측 플래그만 바꾼 ObservedColors. 새 증거 필드는 기본 None."""
    base = dict(lower_body_seen=None, lower_body_clothed=None, lower_body_bare=None, fullbody=None)
    base.update(kw)
    return dataclasses.replace(observed(), **base)


def _missing_bottom(top="tee"):
    return A.validate({
        "top_garment": top,
        "pattern": "plain",
        "sleeve_len": "short",
        "hair_length": "short",
        "beard": "none",
        "inner_top": "none",
        "neckwear": "none",
        "hair_bbox": [0, 0, 1000, 1000],
    })


def test_resolve_bottom_defaults_jeans_when_lower_body_unseen():
    obs = _flags(lower_body_seen=False, lower_body_clothed=False, lower_body_bare=False, fullbody=False)
    assert R.resolve_bottom_ex(_missing_bottom(), obs) == ("jeans", True)


def test_resolve_bottom_missing_null_defaults_jeans_when_upper_body():
    """VLM이 bottom을 비우거나 null/빈 문자열로 줘도 상반신이면 jeans (2026-10-28)."""
    obs = _flags(lower_body_seen=False, lower_body_clothed=False, lower_body_bare=False, fullbody=False)
    assert R.resolve_bottom_ex(_missing_bottom(), obs) == ("jeans", True)
    empty = A.validate({**{k: v for k, v in {"top_garment": "tee", "pattern": "plain",
                                             "sleeve_len": "short", "hair_length": "short"}.items()},
                        "bottom_garment": ""})
    assert R.resolve_bottom_ex(empty, obs) == ("jeans", True)
    null = A.validate({"top_garment": "tee", "bottom_garment": None, "pattern": "plain",
                       "sleeve_len": "short", "hair_length": "short"})
    assert R.resolve_bottom_ex(null, obs) == ("jeans", True)


def test_resolve_bottom_missing_defaults_jeans_when_parser_off_portrait():
    obs = _flags(fullbody=False)  # 파서 꺼짐 → 모든 증거 None
    assert R.resolve_bottom_ex(_missing_bottom(), obs) == ("jeans", True)


def test_resolve_bottom_missing_keeps_none_when_parser_off_fullbody():
    obs = _flags(fullbody=True)
    assert R.resolve_bottom_ex(_missing_bottom(), obs) == ("none", False)


def test_resolve_bottom_missing_uses_measured_pants_when_clothed():
    """VLM은 비었지만 파서가 바지를 봤다 → 측정색 바지, bare skin 아님."""
    obs = _flags(lower_body_seen=True, lower_body_clothed=True, lower_body_bare=False, fullbody=True)
    assert R.resolve_bottom_ex(_missing_bottom(), obs) == ("pants", False)


def test_resolve_bottom_keeps_none_when_only_legs_seen():
    """맨다리가 보이는 전신 사진은 여전히 none (설계 D3 유지)."""
    obs = _flags(lower_body_seen=True, lower_body_clothed=False, lower_body_bare=True, fullbody=True)
    assert R.resolve_bottom_ex(attrs(bottom_garment="none"), obs) == ("none", False)


def test_resolve_bottom_dress_is_dress_not_jeans():
    """드레스는 jeans 기본도, bare legs도 아니다 — 다리를 드레스로 덮는다 (2026-10-28)."""
    obs = _flags(lower_body_seen=False, lower_body_clothed=False, lower_body_bare=False, fullbody=False)
    assert R.resolve_bottom_ex(attrs(bottom_garment="none", top_garment="dress"), obs) == ("dress", False)


def test_render_dress_covers_legs_without_skin_gap():
    obs = _flags(lower_body_seen=False, lower_body_clothed=False, lower_body_bare=False, fullbody=False)
    canvas = R.render(obs, attrs(bottom_garment="none", top_garment="dress"), (), "classic")
    f = get_layout("classic").face("r_leg", "front", 0)
    skin = shade(rgba(obs.skin.hex), R.FACE_SHADE["front"])[:3]
    for v in range(9):
        assert canvas.image.getpixel((f.x + 1, f.y + v))[:3] != skin, v


def test_render_dress_beats_conflicting_jeans_bottom():
    obs = _flags(lower_body_seen=False, lower_body_clothed=False, lower_body_bare=False, fullbody=False)
    assert R.resolve_bottom_ex(attrs(top_garment="dress", bottom_garment="jeans"), obs) == ("dress", False)


def test_render_skirt_short_hem_leaves_bare_legs_below():
    """짧은 치마는 밑단까지만 덮고 아래는 맨다리 — 드레스처럼 늘리지 않는다."""
    obs = dataclasses.replace(observed(), skirt_hem_rows=3)
    canvas = R.render(obs, attrs(bottom_garment="skirt"), (), "classic")
    f = get_layout("classic").face("r_leg", "front", 0)
    skirt = shade(rgba(obs.bottom.hex), R.FACE_SHADE["front"])[:3]
    skin = shade(rgba(obs.skin.hex), R.FACE_SHADE["front"])[:3]
    for v in range(2):
        assert canvas.image.getpixel((f.x + 1, f.y + v))[:3] == skirt, v
    assert canvas.image.getpixel((f.x + 1, f.y + 2))[:3] == shade(rgba(obs.bottom.hex), 0.82)[:3]  # hem
    for v in range(3, 9):
        assert canvas.image.getpixel((f.x + 1, f.y + v))[:3] == skin, v


def test_render_skirt_long_hem_covers_to_shoes():
    obs = dataclasses.replace(observed(), skirt_hem_rows=9)
    canvas = R.render(obs, attrs(bottom_garment="skirt"), (), "classic")
    f = get_layout("classic").face("r_leg", "front", 0)
    skin = shade(rgba(obs.skin.hex), R.FACE_SHADE["front"])[:3]
    for v in range(9):
        assert canvas.image.getpixel((f.x + 1, f.y + v))[:3] != skin, v


def test_render_skirt_hem_falls_back_when_no_mask():
    obs = dataclasses.replace(observed(), skirt_hem_rows=None)
    canvas = R.render(obs, attrs(bottom_garment="skirt"), (), "classic")
    f = get_layout("classic").face("r_leg", "front", 0)
    skin = shade(rgba(obs.skin.hex), R.FACE_SHADE["front"])[:3]
    assert canvas.image.getpixel((f.x + 1, f.y + R.DEFAULT_SKIRT_ROWS - 1))[:3] != skin
    assert canvas.image.getpixel((f.x + 1, f.y + R.DEFAULT_SKIRT_ROWS))[:3] == skin


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


def test_render_skirt_uses_skirt_mask_colour_not_skin_bottom():
    """치마 렌더는 Skirt(5) 마스크 색을 쓴다 — 바지 클래스가 맨다리를 덮어도 오염 없음."""
    obs = dataclasses.replace(
        observed(), skirt_hem_rows=4,
        bottom=sample("#a3715e"), skirt_sample=sample("#3b3b67"),
    )
    canvas = R.render(obs, attrs(bottom_garment="skirt"), (), "classic")
    f = get_layout("classic").face("r_leg", "front", 0)
    assert canvas.image.getpixel((f.x + 1, f.y + 0))[:3] == shade(rgba("#3b3b67"), 1.0)[:3]


def test_render_skirt_falls_back_to_dress_mask_colour():
    obs = dataclasses.replace(
        observed(), skirt_hem_rows=6,
        bottom=sample("#a3715e"), dress_sample=sample("#eeeeee"),
    )
    canvas = R.render(obs, attrs(bottom_garment="skirt"), (), "classic")
    f = get_layout("classic").face("r_leg", "front", 0)
    assert canvas.image.getpixel((f.x + 1, f.y + 0))[:3] == shade(rgba("#eeeeee"), 1.0)[:3]


def test_render_dress_uses_dress_mask_colour():
    obs = dataclasses.replace(
        observed(), bottom=sample("#a3715e"), dress_sample=sample("#eeeeee"),
    )
    canvas = R.render(obs, attrs(top_garment="dress", bottom_garment="none"), (), "classic")
    f = get_layout("classic").face("r_leg", "front", 0)
    assert canvas.image.getpixel((f.x + 1, f.y + 0))[:3] == shade(rgba("#eeeeee"), 1.0)[:3]


# --- Phase 3: 크롭 천 텍스처 (2026-10-28) -----------------------------------

def _fabric(complexity=20.0):
    from PIL import Image

    def tile(w, h):
        img = Image.new("RGB", (w, h))
        px = img.load()
        for v in range(h):
            for u in range(w):
                px[u, v] = (200, 40, 60) if (u + v) % 2 else (40, 90, 160)
        return img

    return TX.FabricTexture(tile(8, 12), tile(4, 12), tile(4, 12), complexity, (0, 0, 8, 8))


def test_graphic_uses_cropped_texture_front_only():
    obs = dataclasses.replace(observed(), top_texture=_fabric())
    canvas = R.render(obs, attrs(pattern="graphic"), (), "classic")
    front = get_layout("classic").face("body", "front", 0)
    back = get_layout("classic").face("body", "back", 0)
    fcols = {canvas.image.getpixel((front.x + u, front.y + 6))[:3] for u in range(8)}
    assert len(fcols) > 1
    assert (242, 242, 242) not in fcols
    base = shade(rgba(obs.top.hex), R.FACE_SHADE["back"])[:3]
    assert canvas.image.getpixel((back.x + 2, back.y + 6))[:3] == base


def test_plain_pattern_ignores_usable_texture():
    """흰 셔츠 주름처럼 HF 가 높아도 VLM pattern=plain 이면 크롭하지 않는다."""
    obs = dataclasses.replace(observed(), top_texture=_fabric(complexity=20.0))
    canvas = R.render(obs, attrs(pattern="plain"), (), "classic")
    front = get_layout("classic").face("body", "front", 0)
    cols = {canvas.image.getpixel((front.x + u, front.y + 6))[:3] for u in range(8)}
    assert len(cols) == 1


def test_skirt_uses_bottom_texture_above_hem_only():
    obs = dataclasses.replace(observed(), bottom_texture=_fabric(), skirt_hem_rows=4)
    canvas = R.render(obs, attrs(bottom_garment="skirt"), (), "classic")
    f = get_layout("classic").face("r_leg", "front", 0)
    rows = [[canvas.image.getpixel((f.x + u, f.y + v))[:3] for u in range(f.w)] for v in range(9)]
    assert len({tuple(r) for r in rows[:2]}) == 2  # 체커 두 색
    skin = shade(rgba(obs.skin.hex), R.FACE_SHADE["front"])[:3]
    for v in range(4, 9):
        assert all(px == skin for px in rows[v]), v


def test_textured_skin_passes_validation():
    obs = dataclasses.replace(observed(), top_texture=_fabric(), bottom_texture=_fabric())
    canvas = R.render(obs, attrs(pattern="plaid", bottom_garment="jeans"), (), "classic")
    assert validate_image(canvas.image, "classic") == []


def _style_attrs(style, length="long"):
    return attrs(hair_length=length, hair_style=style)


def test_l2_style_signatures_are_distinct():
    def l2_body(style, length="long"):
        c = R.render(observed(hair="#112233"), _style_attrs(style, length), ())
        return _opaque_cells(c, "body", 1)

    bob = l2_body("bob")
    long_s = l2_body("long_straight")
    wavy = l2_body("long_wavy")
    curly = l2_body("curly")
    pony = l2_body("ponytail")
    bun = l2_body("bun")
    assert not bob  # no drape
    # Straight/wavy/curly share one reference drape (refs are unlabelled).
    assert len(long_s) > 0 and wavy == long_s == curly
    assert any(name == "back" and u in (3, 4) for name, u, v in pony)
    assert not any(name == "back" and u in (0, 1) for name, u, v in pony)

    # bob/short 프린지 차이: bob 은 2행까지, short 은 2행 위를 덮지 않는다.
    bobc = R.render(observed(), _style_attrs("bob", "short"), ())
    shortc = R.render(observed(), _style_attrs("short", "short"), ())
    # Reference short hair has L2 at the temples too (row3 u1: 99% of refs);
    # the style contrast is the centre fringe: bob covers row 4, short is open.
    assert bobc.get("head", "front", 3, 4, 1)[3] != 0
    assert shortc.get("head", "front", 3, 4, 1)[3] == 0

    # bun: 뒤통수 상단 밝은 덩어리.
    bunc = R.render(observed(hair="#112233"), _style_attrs("bun"), ())
    plainc = R.render(observed(hair="#112233"), _style_attrs("long_straight"), ())
    assert bunc.get("head", "back", 3, 1, 1)[:3] != plainc.get("head", "back", 3, 1, 1)[:3]


def test_back_drape_caps_mask_evidence_and_no_drape_styles():
    """Loose long styles use the reference drape length (back 12, chest 11),
    not SCHP evidence; no-drape styles stay bare."""
    st = dataclasses.replace(HS.rule_stencil("long"), body_rows=3)
    base = dataclasses.replace(observed(), hair_stencil=st)
    long = R.render(base, attrs(hair_length="long", hair_style="long_straight"), ())
    for v in range(12):
        assert _hairish(long.get("body", "back", 3, v), base.hair.hex, "back"), v
    for v in range(11):
        assert _hairish(long.get("body", "front", 0, v), base.hair.hex, "front"), v
    assert not _hairish(long.get("body", "front", 3, 2), base.hair.hex, "front")  # shirt centre
    bob = R.render(base, attrs(hair_length="long", hair_style="bob"), ())
    assert bob.get("body", "back", 0, 0)[:3] != shade(rgba(base.hair.hex), R.FACE_SHADE["back"])[:3]


def test_hair_l2_has_no_regular_parity_stripes():
    """Reference tone maps may vary, but not as the old even/odd 2-tone columns."""
    canvas = R.render(observed(hair="#112233"), attrs(hair_length="long", hair_style="long_straight"), ())
    for face_name in ("top", "back"):
        f = canvas.layout.face("head", face_name, 1)
        cols = [
            canvas.get("head", face_name, u, 0, 1)
            for u in range(f.w)
            if canvas.get("head", face_name, u, 0, 1)[3]
        ]
        even = {c for c in cols[0::2]}; odd = {c for c in cols[1::2]}
        assert not (len(even) == 1 and len(odd) == 1 and even != odd), (face_name, cols)


def test_eyes_are_exactly_one_row_above_chin():
    """Every eye bottom is row 6; row 7 is the single chin gap."""
    from skinmaker.canvas import shade, rgba
    skin = shade(rgba("#e0ac69"), R.FACE_SHADE["front"])[:3]
    for hood in ("none", "up", "down"):
        canvas = R.render(observed(), attrs(top_garment="hoodie", hood=hood), ())
        for u in range(1, 7):
            assert canvas.get("head", "front", u, 7)[:3] == skin, (hood, u)
        assert any(canvas.get("head", "front", u, 6)[:3] != skin for u in (1, 2, 5, 6)), hood


def test_template_l2_never_covers_eye_rows():
    """Reference templates keep both eye rows clear (row5 L2 in <=10% of refs)."""
    for i in range(30):
        color = f"#{0x101010 + i * 0x050505:06x}"
        canvas = R.render(observed(hair=color), attrs(hair_length="long", hair_style="long_wavy"), ())
        for u in range(1, 7):
            for v in (5, 6):
                assert canvas.get("head", "front", u, v, 1)[3] == 0, (i, u, v)


def test_hood_up_mask_brim_at_row_zero():
    """Final mask: L1 front row 0 is the brim; L2 front is empty and the L1
    rows below are the face opening (base hair/skin)."""
    canvas = R.render(observed(), attrs(top_garment="hoodie", hood="up"), ())
    for u in range(8):
        assert canvas.get("head", "front", u, 0, 0)[3] == 255  # L1 brim


def test_final_asset_applies_head_bottom_masks():
    """The committed head.bottom L1/L2 masks must reach the rendered skin."""
    from skinmaker import hood_masks

    masks = hood_masks.load_hood_masks()
    assert masks and "head.bottom" in masks["up"]["L1"]
    for hood in ("up", "down"):
        canvas = R.render(observed(), attrs(top_garment="hoodie", hood=hood), ())
        plain = R.render(observed(), attrs(top_garment="hoodie", hood="none"), ())
        for layer, layer_index in (("L1", 0), ("L2", 1)):
            grid = masks[hood][layer]["head.bottom"]
            for v, row in enumerate(grid):
                for u, bit in enumerate(row):
                    if bit:
                        assert canvas.get("head", "bottom", u, v, layer_index) != plain.get(
                            "head", "bottom", u, v, layer_index
                        ), (hood, layer, u, v)


def test_hood_down_long_hair_skips_body_back_hair():
    """Hood-down + long hair must not draw hair over the body back face."""
    short = R.render(observed(), attrs(top_garment="hoodie", hood="down",
                                       hair_length="short", hair_style="short"), ())
    for length, style in (("long", "long_straight"), ("medium", "long_wavy")):
        long = R.render(observed(), attrs(top_garment="hoodie", hood="down",
                                          hair_length=length, hair_style=style), ())
        for layer in (0, 1):
            for v in range(12):
                for u in range(8):
                    assert long.get("body", "back", u, v, layer) == short.get("body", "back", u, v, layer), (length, layer, u, v)


def test_dark_outer_sample_does_not_override_a_single_light_jacket():
    """Notes: teal/gray single jackets became black because the outer sample
    (shadow) overrode a confident top."""
    import dataclasses
    from skinmaker.colors import ColorSample

    base = observed(top="#498ba4")
    base = dataclasses.replace(
        base,
        outer=ColorSample("#111011", 0.9, True, (17, 16, 17), 400),
        inner=ColorSample("#400e0a", 0.8, True, (64, 14, 10), 200),
    )
    canvas = R.render(base, attrs(top_garment="jacket", inner_top="tee",
                                  closure_type="zipper", collar_type="none"), ())
    f = canvas.layout.face("body", "front", 0)
    px = canvas.image.getpixel((f.x + 1, f.y + 6))[:3]
    assert px[2] > px[0] and px[2] > 40, px  # teal-ish, not near-black


def test_legit_dark_outer_with_light_inner_is_used():
    """A layered light inner shirt + dark outer jacket must still use outer."""
    import dataclasses
    from skinmaker.colors import ColorSample

    base = observed(top="#498ba4")
    base = dataclasses.replace(
        base,
        outer=ColorSample("#111011", 0.9, True, (17, 16, 17), 400),
        inner=ColorSample("#f2f2f2", 0.9, True, (242, 242, 242), 400),
    )
    canvas = R.render(base, attrs(top_garment="jacket", inner_top="tee",
                                  closure_type="open", collar_type="none"), ())
    f = canvas.layout.face("body", "front", 0)
    px = canvas.image.getpixel((f.x + 2, f.y + 10))[:3]
    assert px[0] < 40 and px[1] < 40 and px[2] < 40, px  # used the dark outer


def test_hoodie_outer_overrides_a_background_contaminated_top():
    """Hoodie top sampled as light blue (background) while outer is beige."""
    import dataclasses
    from skinmaker.colors import ColorSample

    base = observed(top="#cae5ff")
    base = dataclasses.replace(base, outer=ColorSample("#8e7a63", 0.9, True, (142, 122, 99), 400))
    canvas = R.render(base, attrs(top_garment="hoodie", inner_top="none",
                                  closure_type="none", collar_type="none"), ())
    f = canvas.layout.face("body", "front", 0)
    px = canvas.image.getpixel((f.x + 2, f.y + 10))[:3]
    assert px[0] > px[2] + 20, px  # beige, not light blue


def test_low_confidence_light_hair_keeps_gold():
    """Gold hair sampled with low confidence must not fall back to dark brown."""
    import dataclasses
    from skinmaker.colors import ColorSample

    base = dataclasses.replace(
        observed(), hair=ColorSample("#ddc19c", 0.4, False, (221, 193, 156), 80)
    )
    colors = R.resolve_colors(base)
    assert colors["hair"][:3] == (221, 193, 156)
    dark = dataclasses.replace(
        observed(), hair=ColorSample("#3e1a0c", 0.4, False, (62, 26, 12), 80)
    )
    assert R.resolve_colors(dark)["hair"] == rgba(R.DEFAULT_HAIR)


def test_headwear_cap_draws_a_light_brim_under_the_hood():
    cap = R.render(observed(), attrs(headwear="cap", hood="up"), ())
    beanie = R.render(observed(), attrs(headwear="beanie", hood="up"), ())
    plain = R.render(observed(), attrs(headwear="none", hood="up"), ())
    f = cap.layout.face("head", "front", 0)
    cap_px = cap.image.getpixel((f.x + 3, f.y + 1))[:3]
    beanie_px = beanie.image.getpixel((f.x + 3, f.y + 1))[:3]
    plain_px = plain.image.getpixel((f.x + 3, f.y + 1))[:3]
    assert cap_px != plain_px and sum(cap_px) > sum(plain_px)
    assert beanie_px != plain_px and sum(beanie_px) < sum(plain_px)


def test_shallow_hood_shows_ear_pixels():
    shallow = R.render(observed(), attrs(hood="up", hood_fit="shallow"), ())
    normal = R.render(observed(), attrs(hood="up", hood_fit="normal"), ())
    f = shallow.layout.face("head", "right", 0)
    ear = shallow.image.getpixel((f.x + 6, f.y + 4))[:3]
    hood = normal.image.getpixel((f.x + 6, f.y + 4))[:3]
    assert ear != hood
    assert ear[0] > ear[2]  # skin shade (warm)


def test_headwear_mask_override_replaces_the_procedural_brim():
    grid = [[0] * 8 for _ in range(8)]
    grid[1][2] = 1
    canvas = R.render(observed(), attrs(headwear="cap", hood="none"), (),
                      mask_override={"headwear.cap": {"L1": {"head.front": grid}}})
    f = canvas.layout.face("head", "front", 0)
    hat = canvas.image.getpixel((f.x + 2, f.y + 1))[:3]
    plain = canvas.image.getpixel((f.x + 1, f.y + 1))[:3]
    assert hat != plain


def test_hood_fit_mask_override_places_ears():
    grid = [[0] * 8 for _ in range(8)]
    grid[6][7] = 1
    canvas = R.render(observed(), attrs(hood="up", hood_fit="shallow"), (),
                      mask_override={"hood_fit.shallow": {"L1": {"head.right": grid}}})
    f = canvas.layout.face("head", "right", 0)
    ear = canvas.image.getpixel((f.x + 7, f.y + 6))[:3]
    assert ear[0] > ear[2]  # skin-shaded ear, not hood fabric


def test_hair_mask_override_clips_head_hair():
    grid = [[0] * 8 for _ in range(8)]
    grid[1][0] = 1
    canvas = R.render(observed(), attrs(hair_style="bob", hood="none"), (),
                      mask_override={"hair_style.bob": {"L1": {"head.front": grid}}})
    f = canvas.layout.face("head", "front", 0)
    hair_px = canvas.image.getpixel((f.x + 0, f.y + 1))[:3]
    skin_px = canvas.image.getpixel((f.x + 1, f.y + 1))[:3]
    assert hair_px != skin_px


def test_beard_mask_override_adds_beard_cells():
    grid = [[0] * 8 for _ in range(8)]
    grid[6][3] = 1
    canvas = R.render(observed(), attrs(beard="full", hood="none"), (),
                      mask_override={"beard.full": {"L1": {"head.front": grid}}})
    f = canvas.layout.face("head", "front", 0)
    beard_px = canvas.image.getpixel((f.x + 3, f.y + 6))[:3]
    skin_px = canvas.image.getpixel((f.x + 2, f.y + 6))[:3]
    assert beard_px != skin_px


def test_sleeve_mask_override_clips_arm_rows():
    grid = [[0] * 4 for _ in range(12)]
    grid[0][0] = 1
    canvas = R.render(observed(), attrs(sleeve_len="short", hood="none"), (),
                      mask_override={"sleeve_len.short": {"L1": {"r_arm.front": grid}}})
    f = canvas.layout.face("r_arm", "front", 0)
    shirt = canvas.image.getpixel((f.x + 0, f.y + 0))[:3]
    skin = canvas.image.getpixel((f.x + 1, f.y + 0))[:3]
    assert shirt != skin


def test_bottom_mask_override_clips_leg_rows():
    grid = [[0] * 4 for _ in range(12)]
    grid[0][0] = 1
    canvas = R.render(observed(), attrs(bottom_garment="pants", hood="none"), (),
                      mask_override={"bottom_garment.pants": {"L1": {"r_leg.front": grid}}})
    f = canvas.layout.face("r_leg", "front", 0)
    pants = canvas.image.getpixel((f.x + 0, f.y + 0))[:3]
    skin = canvas.image.getpixel((f.x + 1, f.y + 0))[:3]
    assert pants != skin


def test_structure_mask_override_clips_zipper_cells():
    grid = [[0] * 8 for _ in range(12)]
    grid[1][4] = 1
    canvas = R.render(observed(), attrs(closure_type="zipper", hood="none", collar_type="none"), (),
                      mask_override={"closure_type.zipper": {"L1": {"body.front": grid}}})
    f = canvas.layout.face("body", "front", 0)
    zipper = canvas.image.getpixel((f.x + 4, f.y + 1))[:3]
    base = canvas.image.getpixel((f.x + 4, f.y + 2))[:3]
    top = shade(rgba(observed().top.hex), R.FACE_SHADE["front"])[:3]
    assert zipper != base
    assert base == top


def test_inner_mask_override_clips_neck_cells():
    grid = [[0] * 8 for _ in range(12)]
    grid[0][3] = 1
    canvas = R.render(observed(), attrs(inner_top="shirt", hood="none", collar_type="none"), (),
                      mask_override={"inner_top.shirt": {"L1": {"body.front": grid}}})
    f = canvas.layout.face("body", "front", 0)
    inner = canvas.image.getpixel((f.x + 3, f.y + 0))[:3]
    top = canvas.image.getpixel((f.x + 3, f.y + 1))[:3]
    assert inner != top


def test_top_garment_mask_overrides_body_and_arm():
    body_grid = [[0] * 8 for _ in range(12)]
    body_grid[1][1] = 1
    arm_grid = [[0] * 4 for _ in range(12)]
    arm_grid[0][0] = 1
    canvas = R.render(observed(), attrs(top_garment="tee", hood="none"), (),
                      mask_override={"top_garment.tee": {"L1": {"body.front": body_grid, "r_arm.front": arm_grid}}})
    f = canvas.layout.face("body", "front", 0)
    top = canvas.image.getpixel((f.x + 1, f.y + 1))[:3]
    skin = canvas.image.getpixel((f.x + 1, f.y + 2))[:3]
    assert top != skin
    a = canvas.layout.face("r_arm", "front", 0)
    arm_top = canvas.image.getpixel((a.x + 0, a.y + 0))[:3]
    arm_skin = canvas.image.getpixel((a.x + 1, a.y + 0))[:3]
    assert arm_top != arm_skin


def test_body_hair_mask_clips_l1_and_l2():
    l1 = [[0] * 8 for _ in range(12)]
    l1[0][1] = 1
    l2 = [[0] * 8 for _ in range(12)]
    l2[0][1] = 1
    canvas = R.render(observed(), attrs(hair_style="long_wavy", hair_length="long", hood="none"), (),
                      mask_override={"hair_style.long_wavy": {"L1": {"body.front": l1},
                                                               "L2": {"body.front": l2}}})
    f = canvas.layout.face("body", "front", 0)
    hair = canvas.image.getpixel((f.x + 1, f.y + 0))[:3]
    top = shade(rgba(observed().top.hex), R.FACE_SHADE["front"])[:3]
    assert hair != top
    assert canvas.image.getpixel((f.x + 1, f.y + 0))[3] == 255
