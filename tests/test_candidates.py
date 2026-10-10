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
