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


@pytest.mark.parametrize("model", ["classic", "slim"])
def test_render_is_valid(model):
    canvas = R.render(observed(), attrs(), (), model)
    assert validate_image(canvas.image, model) == []


@pytest.mark.parametrize("model", ["classic", "slim"])
def test_head_overlay_transparent(model):
    canvas = R.render(observed(), attrs(), (), model)
    px = canvas.image.load()
    for face in canvas.layout.part("head", 1).faces.values():
        for y in range(face.y, face.y + face.h):
            for x in range(face.x, face.x + face.w):
                assert px[x, y][3] == 0


def test_hair_only_in_head_base():
    canvas = R.render(observed(hair="#112233"), attrs(hair_length="long"), (), "classic")
    hair = rgba("#112233")
    front = canvas.layout.face("head", "front", 0)
    assert canvas.image.getpixel((front.x + 4, front.y + 0))[:3] == shade(hair, 1.0)[:3]
    overlay = canvas.layout.face("head", "front", 1)
    assert canvas.image.getpixel((overlay.x + 4, overlay.y + 0))[3] == 0


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



def test_render_uses_only_binary_alpha():
    alpha = R.render(observed(), attrs(), (), "classic").image.getchannel("A")
    assert {v for _, v in alpha.getcolors(maxcolors=256)} <= {0, 255}


@pytest.mark.parametrize("top", ["tee", "hoodie", "jacket", "shirt", "sweater", "vest", "uniform", "apron", "overalls", "dress", "none"])
@pytest.mark.parametrize("bottom", ["jeans", "shorts", "skirt", "pants", "none"])
def test_all_garment_combos_valid(top, bottom):
    sleeve = "none" if top == "none" else "short"
    canvas = R.render(observed(), attrs(top_garment=top, bottom_garment=bottom, sleeve_len=sleeve), (), "classic")
    assert validate_image(canvas.image, "classic") == []
