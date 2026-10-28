"""S2: 스키마·검증·전송 계층·오케스트레이션 (네트워크 없음)."""
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PIL import Image

from skinmaker import attributes as A
from skinmaker import classify as C
from skinmaker import quality as Q
from skinmaker.vlm import TransportError, get_transport
from skinmaker.vlm.gemini import _gemini_schema
from skinmaker.vlm.gemini import GeminiTransport
from skinmaker.vlm.mock import DEFAULT_SCENARIO, MockTransport
from skinmaker.vlm.ollama import OllamaTransport
from skinmaker.vlm.openrouter import DEFAULT_MODELS
from skinmaker.vlm.openrouter import OpenRouterTransport

GOOD = {
    "top_garment": "hoodie",
    "bottom_garment": "jeans",
    "pattern": "plain",
    "sleeve_len": "long",
    "hair_length": "long",
    "beard": "full",
    "inner_top": "shirt",
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


# --- 스키마 ---------------------------------------------------------------

def test_every_enum_field_has_default_and_hint():
    assert set(A.ENUMS) == set(A.FIELD_ORDER)
    assert set(A.DEFAULTS) == set(A.FIELD_ORDER)
    for name in A.FIELD_ORDER:
        assert A.DEFAULTS[name] in A.ENUMS[name]
        assert name in A._HINTS


def test_schema_lists_exactly_the_fields():
    schema = A.build_schema()
    assert set(schema["properties"]) == set(A.NATURAL_ORDER)
    assert schema["required"] == list(A.NATURAL_ORDER)
    for name in A.FIELD_ORDER:
        assert schema["properties"][name]["enum"] == list(A.ENUMS[name])


def test_prompt_contains_all_options_in_given_order():
    prompt = A.build_prompt(A.NATURAL_ORDER)
    for name in A.FIELD_ORDER:
        for option in A.ENUMS[name]:
            assert option in prompt
    assert prompt.index("top_garment") < prompt.index("bottom_garment")


def test_reversed_order_changes_prompt_and_schema_key_order():
    a = A.build_prompt(A.NATURAL_ORDER)
    b = A.build_prompt(A.REVERSED_ORDER)
    assert a != b
    assert list(A.build_schema(A.REVERSED_ORDER)["properties"]) == list(A.REVERSED_ORDER)


# --- JSON 파싱 -----------------------------------------------------------

def test_parse_plain_object():
    assert A.parse_json_object('{"a":1}') == {"a": 1}


def test_parse_fenced_object():
    assert A.parse_json_object('```json\n{"a":1}\n```') == {"a": 1}


def test_parse_object_embedded_in_prose():
    assert A.parse_json_object('설명입니다.\n{"a":1}\n以上') == {"a": 1}


@pytest.mark.parametrize("bad", [None, "", "   ", "설명만", "[1,2,3]", "{oops}"])
def test_parse_rejects_garbage(bad):
    assert A.parse_json_object(bad) is None


# --- 검증 / 강제 ---------------------------------------------------------

def test_validate_accepts_good_payload():
    attrs = A.validate(GOOD)
    assert attrs.get("top_garment") == "hoodie"
    assert attrs.hair_bbox == (200, 50, 800, 600)
    assert attrs.coerced == () and attrs.missing == ()


def test_validate_layering_fields():
    """겹쳐 입은 상의: inner_top/neckwear enum·기본값·강제 (사용자 결정 2026-10-21)."""
    assert A.ENUMS["inner_top"] == ("none", "shirt", "tee", "knit")
    assert A.ENUMS["neckwear"] == ("none", "tie")
    assert A.DEFAULTS["inner_top"] == "none" and A.DEFAULTS["neckwear"] == "none"
    assert A.validate({**GOOD, "neckwear": "tie"}).get("neckwear") == "tie"
    attrs = A.validate({**GOOD, "inner_top": "blouse"})
    assert "inner_top" in attrs.coerced and attrs.get("inner_top") == "none"


def test_validate_beard_defaults_and_coerces():
    """수염 필드: full/stubble/none, 미지정·오값은 none (사용자 결정 2026-10-20)."""
    assert A.ENUMS["beard"] == ("none", "stubble", "full")
    assert A.DEFAULTS["beard"] == "none"
    assert A.validate({**GOOD, "beard": "stubble"}).get("beard") == "stubble"
    assert A.validate(GOOD).get("beard") == "full"
    attrs = A.validate({**GOOD, "beard": "bushy"})
    assert "beard" in attrs.coerced and attrs.get("beard") == "none"


def test_validate_coerces_unknown_enum_value():
    attrs = A.validate({**GOOD, "pattern": "space_invaders"})
    assert "pattern" in attrs.coerced
    assert attrs.get("pattern") == A.DEFAULTS["pattern"]


def test_validate_records_missing_fields():
    attrs = A.validate({"top_garment": "tee"})
    assert set(attrs.missing) == set(A.FIELD_ORDER) - {"top_garment"} | {A.BBOX_FIELD}
    assert attrs.get("top_garment") == "tee"


def test_validate_none_payload():
    attrs = A.validate(None)
    assert set(attrs.missing) == set(A.FIELD_ORDER) | {A.BBOX_FIELD}


@pytest.mark.parametrize(
    "bad",
    [[1, 2], [0, 0, 1, 1], "abcd", [None, 0, 900, 900], [900, 0, 900, 900], None, "x"],
)
def test_validate_rejects_bad_bbox(bad):
    assert A.validate({**GOOD, "hair_bbox": bad}).hair_bbox is None


def test_validate_sorts_reversed_bbox():
    attrs = A.validate({**GOOD, "hair_bbox": [800, 600, 200, 50]})
    assert attrs.hair_bbox == (200, 50, 800, 600)


def test_validate_clips_bbox_to_scale():
    attrs = A.validate({**GOOD, "hair_bbox": [-500, -500, 5000, 5000]})
    assert attrs.hair_bbox == (0, 0, A.BBOX_SCALE, A.BBOX_SCALE)


def test_vary_fields_includes_top_and_excludes_face_fields():
    assert "glasses" not in A.Attributes({**{n: "x" for n in A.FIELD_ORDER}}, None).vary_fields()
    # 상의 유무 불일치는 옷 입은 대안 후보로 살린다 (2026-10-21 캐미솔 사진).
    assert set(A.Attributes({}, None).vary_fields()) == {"top_garment", "hair_length", "sleeve_len"}


def test_prompt_states_sleeveless_tops_are_tops():
    """끈나시·민소매도 상의 — none은 맨몸일 때만 (2026-10-21 캐미솔 오분류 대응)."""
    prompt = A.build_prompt()
    assert "민소매" in prompt and "끈나시" in prompt
    assert "none" in prompt


# --- 불확실성 -------------------------------------------------------------

def test_agreement_detects_disagreement():
    a = A.validate(GOOD)
    b = A.validate({**GOOD, "pattern": "check"})
    assert A.agreement(a, b) == ("pattern",)


def test_agreement_detects_coercion_either_side():
    a = A.validate(GOOD)
    b = A.validate({**GOOD, "sleeve_len": "nope"})
    assert "sleeve_len" in A.agreement(a, b)


def test_agreement_is_empty_for_identical():
    assert A.agreement(A.validate(GOOD), A.validate(GOOD)) == ()


def test_is_uncertain_from_single_call():
    assert A.is_uncertain(A.validate(GOOD)) == ()
    assert set(A.is_uncertain(A.validate({**GOOD, "pattern": "nope"}))) == {"pattern"}


# --- 전송 계층 계약 -------------------------------------------------------

def test_registry_rejects_unknown_transport():
    with pytest.raises(ValueError):
        get_transport("gpt5")


def test_mock_transport_records_calls_and_repeats_first():
    t = MockTransport(first=GOOD)
    assert t.complete(Image.new("RGB", (10, 10)), "p", {}) == GOOD
    assert t.complete(Image.new("RGB", (10, 10)), "p", {}) == GOOD
    assert len(t.calls) == 2


def test_mock_transport_failure_mode():
    t = MockTransport(fail=True, error="boom")
    assert t.available() == (False, "boom")
    assert t.complete(Image.new("RGB", (4, 4)), "p", {}) is None


def test_registry_mock_without_scenario_uses_default():
    """env/CLI 경로(get_transport)로 만든 mock 은 기본 시나리오를 갖는다.

    시나리오 주입은 테스트가 직접 MockTransport(first=...) 로 한다. 주입 없이
    레지스트리로 만들 때만 기본값을 채워 오프라인 개발이 동작하게 한다.
    """
    t = get_transport("mock")
    payload = t.complete(Image.new("RGB", (10, 10)), "p", {})
    assert payload is not None
    assert payload["top_garment"] == "tee"


def test_default_scenario_has_no_uncertain_fields():
    """기본 시나리오는 8필드를 모두 채운다 — 오프라인 mock 실행이 거짓 불확실성을 만들지 않는다."""
    assert A.is_uncertain(A.validate(DEFAULT_SCENARIO)) == ()
    result = C.classify(photo(), get_transport("mock"), double_check=True)
    assert result.ok
    assert result.uncertain == ()


def test_gemini_requires_api_key(monkeypatch):
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    t = GeminiTransport()
    ok, detail = t.available()
    assert ok is False and "키 없음" in detail
    assert t.configured()[0] is False


def test_gemini_configured_accepts_key_without_network():
    t = GeminiTransport(api_key="k")
    ok, detail = t.configured()
    assert ok is True and "키 있음" in detail


def test_gemini_schema_conversion():
    out = _gemini_schema(A.build_schema())
    assert out["type"] == "OBJECT"
    assert out["properties"]["top_garment"]["enum"] == list(A.ENUMS["top_garment"])
    assert out["properties"]["hair_bbox"]["items"] == {"type": "INTEGER"}
    assert out["properties"]["closure_type"]["enum"] == list(A.ENUMS["closure_type"])
    assert out["properties"]["collar_type"]["enum"] == list(A.ENUMS["collar_type"])
    assert "floral" in out["properties"]["pattern"]["enum"]


def test_prompt_lists_structure_fields():
    prompt = A.build_prompt()
    for name in ("closure_type", "collar_type", "pocket_type", "symmetry"):
        assert name in prompt


def test_gemini_extracts_text_part():
    t = GeminiTransport(api_key="k")
    payload = {"candidates": [{"content": {"parts": [{"text": '{"a":1}'}]}}]}
    assert t._extract(payload) == {"a": 1}


def test_gemini_extract_handles_no_candidates():
    t = GeminiTransport(api_key="k")
    assert t._extract({}) is None


def test_ollama_availablity_reports_unreachable():
    class Boom:
        def get(self, *a, **k):
            raise OSError("no route")

    ok, detail = OllamaTransport(host="http://127.0.0.1:1", session=Boom()).available()
    assert ok is False and "연결 실패" in detail


def test_ollama_configured_does_not_probe():
    class Boom:
        def get(self, *a, **k):
            raise AssertionError("configured() must not probe")

    ok, detail = OllamaTransport(host="http://127.0.0.1:1", session=Boom()).configured()
    assert ok is True and "연결 미확인" in detail


def test_mock_configured_reports_failure_mode():
    ok, detail = MockTransport(fail=True, error="boom").configured()
    assert ok is False and "boom" in detail


# --- 모델 크롭 ------------------------------------------------------------

def test_model_region_includes_shoulders():
    face = Q.FaceBox(200, 120, 160, 200)
    r = C.model_region(face, (600, 800))
    assert r.y < face.y
    assert r.bottom > face.bottom + 200
    assert r.x < face.x and r.right > face.right


def test_model_region_reaches_hips_for_full_body():
    """전신샷에서 크롭이 골반까지 내려가야 하의가 보인다 (청바지→none 회귀)."""
    face = Q.FaceBox(270, 93, 61, 86)
    r = C.model_region(face, (600, 900))
    assert r.bottom >= face.bottom + int(face.h * 3.5)


def test_model_region_reaches_image_bottom_for_fullbody():
    """전신(messi5)에서 크롭 하단이 이미지 하단에 닿아야 다리가 보인다."""
    face = Q.FaceBox(228, 95, 30, 37)
    region = C.model_region(face, (548, 342))
    clipped = Q.clip_to(region, (548, 342))
    assert clipped is not None
    assert clipped.bottom == 342
    assert clipped.w > face.w * 2  # 양팔이 들어올 폭


def test_portrait_crop_unchanged_and_fullbody_gets_more_pixels():
    """초상화는 기존 크롭·768px 그대로, 전신은 이미지 하단까지 + 고해상도.

    (brief 초안의 (548,342) 치수로는 크롭이 이미지 자체를 넘을 수 없어
    max>768 을 만족할 수 없으므로, 실제 전신 사진 치수로 적응.
    의도는 동일: 프레이밍별 차등 해상도.)
    """
    portrait_img = photo((1000, 1000), Q.FaceBox(300, 200, 200, 250))
    full_img = photo((1000, 1600), Q.FaceBox(450, 150, 80, 100))
    assert C.framing(portrait_img) == "portrait"
    assert C.framing(full_img) == "fullbody"
    # B1(2026-10-11) side=1.7/up=1.25: 앉은 구도의 옆옷·손이 잘리지 않게 확장.
    # 초상화도 동일 상수라 (1000x1000, face 200x250) 크롭은 이렇게 나온다:
    # x = 300 - 1.7*200 = -40 → 0, right = 300+200+340 = 840,
    # y = 200 - 1.25*250 = -112 → 0, bottom = 200+250*6.25 > 1000 → 1000.
    clipped = Q.clip_to(C.model_region(portrait_img.face, (1000, 1000)), (1000, 1000))
    assert clipped == Q.FaceBox(0, 0, 840, 1000)
    portrait = C.prepare(portrait_img)
    full = C.prepare(full_img)
    assert portrait is not None and full is not None
    assert max(portrait.image.size) <= 768
    assert max(full.image.size) > 768  # 전신 고해상도
    assert Q.clip_to(C.model_region(full_img.face, (1000, 1600)), (1000, 1600)).bottom == 1600


def test_framing_boundary_and_no_face():
    """경계 face_h/img_h=0.12 는 portrait, 미만은 fullbody, 얼굴 없음은 portrait."""
    assert C.framing(photo((1000, 1000), Q.FaceBox(0, 0, 120, 120))) == "portrait"
    assert C.framing(photo((1000, 1000), Q.FaceBox(0, 0, 119, 119))) == "fullbody"
    noface = Q.PhotoInput("t.jpg", Image.new("RGB", (100, 100)), None, None, ())
    assert C.framing(noface) == "portrait"


def test_prepare_returns_none_without_face():
    p = Q.PhotoInput("t.jpg", Image.new("RGB", (100, 100)), None, None, ())
    assert C.prepare(p) is None


def test_prepare_downscales_to_max_px():
    p = photo(size=(2400, 3200), face=Q.FaceBox(800, 400, 600, 800))
    crop = C.prepare(p, max_px=768)
    assert crop is not None
    assert max(crop.image.size) <= 768


def test_bbox_maps_back_to_original_pixels():
    p = photo(size=(600, 800), face=Q.FaceBox(200, 120, 160, 200))
    crop = C.prepare(p)
    back = crop.back_to_original((0, 0, 1000, 1000), p.image.size)
    assert back.x == crop.source.x and back.y == crop.source.y
    assert back.w <= crop.source.w and back.h <= crop.source.h


def test_bbox_none_maps_to_none():
    assert C.prepare(photo()).back_to_original(None, (600, 800)) is None


# --- classify 오케스트레이션 ----------------------------------------------

def test_classify_single_call_success():
    p = photo()
    r = C.classify(p, MockTransport(first=GOOD), double_check=False)
    assert r.ok and not r.double_checked
    assert r.attributes.get("top_garment") == "hoodie"
    assert r.uncertain == ()
    assert r.elapsed >= 0


def test_classify_double_check_uses_two_calls_with_different_prompts():
    t = MockTransport(first=GOOD, second=GOOD)
    r = C.classify(photo(), t, double_check=True)
    assert r.double_checked and len(t.calls) == 2
    assert t.calls[0]["prompt"] != t.calls[1]["prompt"]
    assert r.uncertain == ()


def test_classify_double_check_flags_disagreement():
    t = MockTransport(first=GOOD, second={**GOOD, "sleeve_len": "short"})
    r = C.classify(photo(), t, double_check=True)
    assert r.uncertain == ("sleeve_len",)
    assert r.attributes.get("sleeve_len") == "long"


def test_classify_double_check_can_rescue_coerced_value():
    t = MockTransport(first={**GOOD, "pattern": "???"}, second=GOOD)
    r = C.classify(photo(), t, double_check=True)
    assert r.attributes.get("pattern") == "plain"
    assert "pattern" in r.uncertain


def test_classify_merge_keeps_first_when_both_valid():
    t = MockTransport(first=GOOD, second=GOOD)
    r = C.classify(photo(), t, double_check=True)
    assert r.raw_first == GOOD


class RaisingTransport:
    """설정 누락처럼 TransportError 를 던지는 전송 계층 (네트워크 없음)."""

    name = "raising"

    def __init__(self, fail_on: int = 1, message: str = "Gemini API 키가 없다"):
        self.fail_on = fail_on
        self.message = message
        self.calls = 0

    def available(self) -> tuple[bool, str]:
        return True, "raising"

    def complete(self, image, prompt, schema):
        self.calls += 1
        if self.calls == self.fail_on:
            raise TransportError(self.message)
        return dict(GOOD)


def test_classify_reports_transport_failure():
    t = MockTransport(fail=True, error="HTTP 429")
    r = C.classify(photo(), t, double_check=False)
    assert r.ok is False
    assert "HTTP 429" in r.error
    assert r.error_kind is None


def test_classify_reports_transport_exception_instead_of_raising():
    r = C.classify(photo(), RaisingTransport(fail_on=1), double_check=False)
    assert r.ok is False
    assert r.error_kind == "transport"
    assert "API 키" in r.error


def test_classify_second_query_exception_degrades_to_single_query():
    t = RaisingTransport(fail_on=2)
    r = C.classify(photo(), t, double_check=True)
    assert t.calls == 2
    assert r.ok is True
    assert r.double_checked is False
    assert r.raw_second is None
    assert r.attributes.get("top_garment") == "hoodie"


def test_classify_reports_parse_failure():
    r = C.classify(photo(), MockTransport(first=None), double_check=False)
    assert r.ok is False and "파싱" in r.error


def test_classify_without_face_fails_cleanly():
    p = Q.PhotoInput("t.jpg", Image.new("RGB", (100, 100)), None, None, ())
    r = C.classify(p, MockTransport(first=GOOD))
    assert r.ok is False


def test_classify_is_transport_agnostic_in_output():
    a = C.classify(photo(), MockTransport(first=GOOD), double_check=False)
    b = C.classify(photo(), MockTransport(first=GOOD), double_check=False)
    assert a.attributes.values == b.attributes.values
    assert a.uncertain == b.uncertain


def test_classify_records_raw_payloads():
    r = C.classify(photo(), MockTransport(first=GOOD, second=GOOD), double_check=True)
    assert r.raw_first == GOOD and r.raw_second == GOOD


def test_classify_attaches_hair_bbox_in_pixels():
    r = C.classify(photo(), MockTransport(first=GOOD), double_check=False)
    assert r.hair_bbox_px is not None
    assert r.hair_bbox_px.w > 0


# --- 교차 규칙 (enum 은 독립이 아니다) ------------------------------------

def test_cross_rule_forces_sleeve_none_when_no_top():
    a = A.validate({**GOOD, "top_garment": "none", "sleeve_len": "long"})
    assert a.get("sleeve_len") == "none"
    assert any(s.startswith("sleeve_len") for s in a.derived)


def test_cross_rule_forces_plain_when_no_top():
    a = A.validate({**GOOD, "top_garment": "none", "pattern": "plaid"})
    assert a.get("pattern") == "plain"


def test_cross_rule_leaves_valid_payload_untouched():
    a = A.validate(GOOD)
    assert a.derived == ()
    assert a.get("sleeve_len") == "long"


def test_cross_rule_reports_both_applications():
    a = A.validate({**GOOD, "top_garment": "none", "pattern": "check", "sleeve_len": "short"})
    # sleeve/pattern + closure/collar (top=none) — pocket already none
    assert len(a.derived) == 4
    assert any(d.startswith("closure_type") for d in a.derived)


def test_apply_cross_rules_is_pure():
    values = {n: GOOD[n] for n in A.FIELD_ORDER}
    before = dict(values)
    A.apply_cross_rules(values)
    assert values == before


def test_derive_does_not_touch_when_top_present():
    d = A.apply_cross_rules({"top_garment": "hoodie", "sleeve_len": "long", "pattern": "plain"})
    assert d.applied == ()


# --- OpenRouter 무료 모델 폴백 ------------------------------------------------

def test_openrouter_registry():
    t = get_transport("openrouter")
    assert t.name == "openrouter"
    assert t.model == "apodex/apodex-1.1-mini:free"


def test_openrouter_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    t = OpenRouterTransport()
    ok, detail = t.available()
    assert ok is False and "API 키 없음" in detail
    assert t.configured()[0] is False


def test_openrouter_default_fallback_chain():
    t = OpenRouterTransport(api_key="x")
    assert t._models[0] == "apodex/apodex-1.1-mini:free"
    assert len(t._models) > 5
    assert "openrouter/free" in t._models


def test_openrouter_custom_model_list():
    t = OpenRouterTransport(api_key="x", model="a/b:free,c/d:free")
    assert t._models == ("a/b:free", "c/d:free")


def test_openrouter_env_default_models(monkeypatch):
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODELS", "z/z:free,a/b:free")
    try:
        t = OpenRouterTransport(api_key="x")
        assert t._models[0] == "z/z:free"
        assert t._models[1] == "a/b:free"
    finally:
        monkeypatch.delenv("OPENROUTER_DEFAULT_MODELS", raising=False)


def test_openrouter_extra_model_becomes_primary():
    t = OpenRouterTransport(api_key="x", model="new/fresh:free")
    assert t._models[0] == "new/fresh:free"
    assert t._models[1] == "apodex/apodex-1.1-mini:free"


class FakeResp:
    def __init__(self, status: int = 200, text: str = "", json_: Any = None):
        self.status_code = status
        self._text = text
        self._json = json_
        self.text = text

    def json(self):
        if self._json is not None:
            return self._json
        return json.loads(self._text)


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def post(self, url, headers, json, timeout):
        self.calls.append((url, headers, json))
        return self.responses.pop(0)

    def get(self, url, headers, timeout):
        return FakeResp(200, "", {"data": []})


def test_openrouter_extract_success_first_call():
    t = OpenRouterTransport(api_key="x")
    t.session = FakeSession(
        [FakeResp(json_={"choices": [{"message": {"content": json.dumps(GOOD)}}]})]
    )
    img = Image.new("RGB", (100, 100), "red")
    result = t.complete(img, "prompt", A.build_schema())
    assert result == GOOD
    assert t.last_model == "apodex/apodex-1.1-mini:free"


def test_openrouter_fallback_to_second_model():
    first = {"choices": [{"message": {"content": "no json at all"}}]}
    second = {"choices": [{"message": {"content": json.dumps(GOOD)}}]}
    t = OpenRouterTransport(api_key="x")
    t.session = FakeSession([FakeResp(json_=first), FakeResp(json_=second)])
    img = Image.new("RGB", (100, 100), "red")
    result = t.complete(img, "prompt", A.build_schema())
    assert result == GOOD
    assert t.last_model == "google/gemma-4-31b-it:free"
    assert t.last_error is None


def test_openrouter_all_models_fail_returns_none():
    fail = {"error": {"message": "boom"}}
    t = OpenRouterTransport(api_key="x")
    t.session = FakeSession([FakeResp(json_=fail), FakeResp(json_=fail)])
    img = Image.new("RGB", (100, 100), "red")
    result = t.complete(img, "prompt", A.build_schema())
    assert result is None
    assert "boom" in t.last_error


def test_openrouter_fallback_on_http_error():
    bad = FakeResp(429, '{"error":{"message":"rate limit"}}')
    good = FakeResp(json_={"choices": [{"message": {"content": json.dumps(GOOD)}}]})
    t = OpenRouterTransport(api_key="x")
    t.session = FakeSession([bad, good])
    img = Image.new("RGB", (100, 100), "red")
    result = t.complete(img, "prompt", A.build_schema())
    assert result == GOOD


def test_openrouter_none_image_returns_none():
    t = OpenRouterTransport(api_key="x")
    result = t.complete(None, "ping", {})
    assert result is None


def test_openrouter_request_structure():
    t = OpenRouterTransport(api_key="x")
    t.session = FakeSession([FakeResp(json_={"choices": [{"message": {"content": json.dumps(GOOD)}}]})])
    img = Image.new("RGB", (100, 100), "red")
    t.complete(img, "hi", A.build_schema())
    req = t.session.calls[0][2]
    assert req["model"] == "apodex/apodex-1.1-mini:free"
    assert req["messages"][0]["role"] == "user"
    assert req["messages"][0]["content"][0]["type"] == "text"
    assert req["messages"][0]["content"][1]["type"] == "image_url"
    assert req["temperature"] == 0
    assert req["response_format"]["type"] == "json_object"
    assert "Authorization" in t.session.calls[0][1]
    assert "X-Title" in t.session.calls[0][1]



# --- B1: mid-프레임 크롭 폭·상단 확장 (앉은/올려다닌 팔) ------------------------
# 실측 (2026-10-11, images12 600x400, face(216,148,59,76)): 옆팔꿈치 x≈375
# (= face.x+2.7fw), 손가락 끝 y≈57 (= face.y-1.2fh). 기존 side=0.9/up=0.9 는
# 둘 다 잘랐다 ("양옆이 잘렸다" 고정10 원인 기록).

def test_mid_frame_crop_covers_akimbo_arms_and_hands():
    face = Q.FaceBox(216, 148, 59, 76)
    region = C.model_region(face, (600, 400))
    assert region.x <= face.x - 1.5 * face.w      # 반대쪽 어깨·소매
    assert region.right >= face.x + 2.5 * face.w  # 옆팔꿈치가 들어온다
    assert region.y <= face.y - 1.1 * face.h      # 올린 손끝
