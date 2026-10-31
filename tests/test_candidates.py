"""S4: 불확실 필드 변형 후보 + 검증 (네트워크 없음)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from skinmaker import attributes as A
from skinmaker import candidates as S4
from skinmaker import classify as C
from skinmaker import quality as Q
from skinmaker.colors import extract
from skinmaker.validate import validate_image
from skinmaker.vlm.mock import MockTransport

BASE = {
    "top_garment": "tee",
    "bottom_garment": "jeans",
    "pattern": "plain",
    "sleeve_len": "long",
    "hair_length": "short",
    "hair_style": "short",
    "hood": "none",
    "beard": "none",
    "inner_top": "none",
    "neckwear": "none",
    "closure_type": "buttons",
    "collar_type": "crew",
    "pocket_type": "none",
    "symmetry": "symmetric",
    "hair_bbox": [200, 50, 800, 600],
}


def photo(size=(600, 800), face=Q.FaceBox(200, 120, 160, 200)):
    img = Image.new("RGB", size, (120, 100, 90))
    q = Q.Quality(0.95, face.area, 120.0, 400.0, 100.0, True)
    return Q.PhotoInput("t.jpg", img, face, q, ())


def setup(first, second):
    p = photo()
    result = C.classify(p, MockTransport(first=first, second=second))
    assert result.ok
    return extract(p), result


def test_disagreement_on_both_vary_fields_gives_three():
    first = dict(BASE)
    second = dict(BASE, sleeve_len="short", hair_length="very_long")
    observed, result = setup(first, second)
    assert set(result.uncertain) >= {"sleeve_len", "hair_length"}
    out = S4.build(observed, result)
    assert len(out) == 3
    assert out[0].varied == "as-answered"
    assert out[0].attributes.get("sleeve_len") == "long"
    assert out[1].attributes.get("hair_length") == "very_long"
    assert out[2].attributes.get("sleeve_len") == "short"
    assert all(c.ok for c in out)
    assert len({c.image.tobytes() for c in out}) == 3


def test_agreement_gives_single_candidate():
    observed, result = setup(dict(BASE), dict(BASE))
    assert result.uncertain == ()
    out = S4.build(observed, result)
    assert len(out) == 1
    assert out[0].varied == "as-answered"
    assert out[0].ok


def test_top_garment_disagreement_gives_clothed_variant():
    """VLM 두 질의가 상의 유무에서 갈리면 옷 입은 대안 후보를 만든다 (2026-10-21)."""
    first = dict(BASE, top_garment="none", sleeve_len="none")
    second = dict(BASE, top_garment="tee", sleeve_len="none")
    observed, result = setup(first, second)
    assert "top_garment" in result.uncertain
    out = S4.build(observed, result)
    assert len(out) == 2
    assert out[0].attributes.get("top_garment") == "none"
    assert out[1].varied.startswith("top_garment=")
    assert out[1].attributes.get("top_garment") == "tee"
    assert all(c.ok for c in out)


def test_uncertain_non_vary_field_gives_no_variant():
    first = dict(BASE)
    second = dict(BASE, pattern="vertical_stripe")
    observed, result = setup(first, second)
    assert "pattern" in result.uncertain
    out = S4.build(observed, result)
    assert len(out) == 1  # pattern 은 vary 대상이 아니라 근거 없는 변형 금지


def test_cross_rule_suppresses_phantom_variant():
    first = dict(BASE, top_garment="none", sleeve_len="none")
    second = dict(BASE, top_garment="none", sleeve_len="long")
    observed, result = setup(first, second)
    out = S4.build(observed, result)
    # 둘째 답 long 은 cross 규칙에 걸려 none 으로 접히므로 c1과 동일 → 중복 제거
    assert len(out) == 1


def test_second_query_coerced_gives_no_variant():
    first = dict(BASE)
    second = dict(BASE, sleeve_len="반팔")
    observed, result = setup(first, second)
    assert "sleeve_len" in result.uncertain
    out = S4.build(observed, result)
    assert len(out) == 1


def test_all_vary_combinations_validate():
    observed, _ = setup(dict(BASE), dict(BASE))
    for hair in A.ENUMS["hair_length"]:
        for sleeve in A.ENUMS["sleeve_len"]:
            values = dict(BASE, hair_length=hair, sleeve_len=sleeve)
            attrs = A.validate(values)
            from skinmaker.render import render

            canvas = render(observed, attrs, (), "classic")
            assert validate_image(canvas.image, "classic") == [], (hair, sleeve)


# --- 후보별 노이즈 시드 + ON/OFF 쌍 (설계 §4·§8.1) --------------------------

def _leg_shoe_pixels(model="classic"):
    from skinmaker.format import get_layout

    layout = get_layout(model)
    allowed = set()
    for part in ("r_leg", "l_leg"):
        for face in layout.part(part, 0).faces.values():
            if face.h < 12:
                continue
            for v in range(9, face.h):  # shoe_start=9 (jeans/pants)
                for u in range(face.w):
                    allowed.add((face.x + u, face.y + v))
    return allowed


def test_candidates_have_seeds():
    first, second = dict(BASE), dict(BASE, sleeve_len="short", hair_length="very_long")
    observed, result = setup(first, second)
    out = S4.build(observed, result)
    assert len(out) == 3
    assert len({c.noise_seed for c in out}) == 3


def test_build_noise_level_zero_noiseless():
    observed, result = setup(dict(BASE), dict(BASE))
    lvl0 = S4.build(observed, result, noise_level=0.0)
    from skinmaker.render import render
    seedless = render(observed, lvl0[0].attributes, (), "classic")
    seedless_flat = render(observed, lvl0[0].attributes, (), "classic", shoe_two_tone=False)
    assert lvl0[0].image.tobytes() == seedless.image.tobytes()
    assert lvl0[0].image_flat.tobytes() == seedless_flat.image.tobytes()


def test_same_candidate_reproducible():
    first, second = dict(BASE), dict(BASE, sleeve_len="short", hair_length="very_long")
    out1 = S4.build(*setup(first, second))
    out2 = S4.build(*setup(first, second))
    assert [c.image.tobytes() for c in out1] == [c.image.tobytes() for c in out2]
    assert [c.noise_seed for c in out1] == [c.noise_seed for c in out2]


def test_candidate_flat_pair_contract():
    """ON/OFF 쌍: 노이즈는 같고, 차이는 신발 행뿐이며, 둘 다 validate 통과."""
    first, second = dict(BASE), dict(BASE, sleeve_len="short", hair_length="very_long")
    observed, result = setup(first, second)
    out = S4.build(observed, result)
    allowed = _leg_shoe_pixels()
    for c in out:
        assert c.ok, c.problems
        assert c.image_flat is not None
        assert validate_image(c.image_flat, "classic") == []
        px1, px2 = c.image.load(), c.image_flat.load()
        diff = {(x, y) for y in range(64) for x in range(64) if px1[x, y] != px2[x, y]}
        assert diff, "ON/OFF 사이 신발 행 차이 없음"
        assert diff <= allowed, diff - allowed
