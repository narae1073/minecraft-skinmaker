"""parsing.py 스파이크→배선 (L2). 플래그(env)로만 켜진다. 의존성 없으면 조용히 폴백."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest
from PIL import Image

from skinmaker import parsing as P
from skinmaker.attributes import EMPTY
from skinmaker import attributes as A
from skinmaker import colors as C
from skinmaker import quality as Q
from skinmaker import render as R


# --- 플래그 ------------------------------------------------------------

def test_flag_default_on(monkeypatch):
    """기본 on (2026-10-12 결정): 미설정 시 파싱 사용. 0/빈/off/no 로만 끈다."""
    monkeypatch.delenv(P.PARSING_ENV, raising=False)
    assert P.parsing_on() is True


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "on", "Yes"])
def test_flag_on_variants(monkeypatch, value):
    monkeypatch.setenv(P.PARSING_ENV, value)
    assert P.parsing_on() is True


@pytest.mark.parametrize("value", ["0", "", "false", "FALSE", "off", "no"])
def test_flag_off_variants(monkeypatch, value):
    monkeypatch.setenv(P.PARSING_ENV, value)
    assert P.parsing_on() is False


def test_parser_path_env_override(monkeypatch, tmp_path):
    target = tmp_path / "m.onnx"
    monkeypatch.setenv(P.PARSER_ENV, str(target))
    assert P.parser_path() == target


def test_preproc_matches_documented_sizes_and_normalized():
    img = Image.new("RGB", (300, 200), (128, 64, 32))
    out = P._preproc(img)
    assert out.shape == (1, 3, 512, 512)
    assert out.dtype == np.float32
    x = out[0, 2]  # B 채널 (RGB 마지막)
    # (32/255 - 0.485) / 0.229
    assert abs(x.mean() - ((32/255 - 0.485) / 0.229)) < 1e-4


# --- 가용성 (의존성/모델 부재는 조용히 불가) ----------------------------

def test_available_false_when_model_missing(tmp_path, monkeypatch):
    monkeypatch.setenv(P.PARSER_ENV, str(tmp_path / "missing.onnx"))
    P.reset()
    ok, detail = P.available()
    assert ok is False and "모델" in detail


def test_available_false_when_runtime_missing(tmp_path, monkeypatch):
    dummy = tmp_path / "fake.onnx"
    dummy.write_bytes(b"x")
    monkeypatch.setenv(P.PARSER_ENV, str(dummy))
    monkeypatch.setattr(P, "_runtime", lambda: None)
    P.reset()
    ok, detail = P.available()
    assert ok is False and "onnxruntime" in detail


def test_bottom_mask_none_when_runtime_missing(monkeypatch, tmp_path):
    dummy = tmp_path / "fake.onnx"
    dummy.write_bytes(b"x")
    monkeypatch.setenv(P.PARSER_ENV, str(dummy))
    monkeypatch.setattr(P, "_runtime", lambda: None)
    P.reset()
    assert P.bottom_mask(Image.new("RGB", (40, 40))) is None


# --- 마스크 (스텁 세션으로 클래스맵 검증) --------------------------------

class FakeSession:
    def __init__(self, seg):
        self.seg = seg
        self.inputs = [type("I", (), {"name": "pixel_values"})()]

    def run(self, names, feed):
        return [self.seg]


def _logits(pants_from_y=256):
    seg512 = np.zeros((512, 512), np.uint8)
    seg512[pants_from_y:, :] = P.PANTS
    out = np.zeros((1, 18, 512, 512), np.float32)
    out[0, P.PANTS, pants_from_y:, :] = 9.0
    return out


def test_bottom_mask_resizes_class_map_to_photo(tmp_path, monkeypatch):
    monkeypatch.setenv(P.PARSING_ENV, "1")
    image = Image.new("RGB", (200, 400), (200, 200, 200))
    monkeypatch.setattr(P, "_session", lambda: FakeSession(_logits(256)))
    P.reset()
    got = P.bottom_mask(image)
    assert got is not None and got.shape == (400, 200) and got.dtype == np.uint8
    assert set(np.unique(got)) == {0, P.PANTS}
    assert (got[300, :] == P.PANTS).all()


# --- extract 배선 (플래그 on/off, 폴백) ---------------------------------

def _synthetic():
    img = Image.new("RGB", (200, 400), (216, 200, 210))
    px = img.load()
    for y in range(80, 175):        # 흰 셔츠
        for x in range(70, 130):
            px[x, y] = (240, 240, 240)
    for y in range(175, 205):        # 노랑 벨트 (밴드가 노랑을 본다)
        for x in range(85, 115):
            px[x, y] = (200, 180, 40)
    for y in range(205, 400):        # 청바지
        for x in range(70, 130):
            px[x, y] = (30, 40, 90)
    face = Q.FaceBox(100, 80, 40, 50)
    return Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())


def _seg_for(photo, classes):
    img = photo.image
    seg = np.zeros((img.height, img.width), np.uint8)
    for y in range(205, 400):
        for x in range(70, 130):
            seg[y, x] = classes["bottom"]
    return seg


def test_extract_uses_mask_bottom_when_enabled(monkeypatch):
    monkeypatch.setenv(P.PARSING_ENV, "1")
    photo = _synthetic()
    monkeypatch.setattr(P, "bottom_mask", lambda image: _seg_for(photo, {"bottom": P.PANTS}))
    obs = C.extract(photo)
    assert obs.bottom.hex == "#1e285a"  # 청바지색 (30,40,90)
    assert obs.bottom_plausible is True


def test_extract_flag_off_never_calls_mask(monkeypatch):
    monkeypatch.setenv(P.PARSING_ENV, "0")  # 명시 off (기본은 이제 on)
    photo = _synthetic()

    def boom(image):
        raise AssertionError("flag off인데 mask가 호출되었다")
    monkeypatch.setattr(P, "bottom_mask", boom)
    obs = C.extract(photo)
    expected = C.extract(photo)  # 동일 env, 밴드/캐스케이드 결과 참조
    assert obs.bottom.hex == expected.bottom.hex
    assert obs.bottom.missing is False


def test_extract_falls_back_to_bands_when_mask_unavailable(monkeypatch):
    monkeypatch.setenv(P.PARSING_ENV, "1")
    photo = _synthetic()
    calls = {}

    def fake_mask(image):
        calls["n"] = calls.get("n", 0) + 1
        return None
    monkeypatch.setattr(P, "bottom_mask", fake_mask)
    obs1 = C.extract(photo)
    monkeypatch.setattr(P, "bottom_mask", fake_mask)
    obs2 = C.extract(photo)
    assert obs1.bottom.hex == obs2.bottom.hex and obs1.bottom.missing is False
    assert calls["n"] >= 1


def _synthetic_wb_sensitive():
    # 피부 앵커가 따뜻해야 WB 게인이 의미 있게 걸린다.
    img = Image.new("RGB", (200, 400), (240, 240, 240))
    px = img.load()
    for y in range(80, 130):        # 얼굴: 따뜻한 피부 (R 치우침)
        for x in range(80, 120):
            px[x, y] = (250, 170, 120)
    for y in range(205, 400):        # 바지: 옅은 노랑 (WB 뒤 회녹색으로 밀리는 값)
        for x in range(70, 130):
            px[x, y] = (232, 220, 160)
    face = Q.FaceBox(80, 80, 40, 50)
    return Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())


def test_mask_bottom_uses_raw_colour_under_wb_gain(monkeypatch):
    # 마스크 국소화는 WB 이전 원본 픽셀을 잰다 — SKIN_REF 앵커 WB 가 옅은 노랑을
    # 회녹색으로 눌러버리는 것(#c7cdc1 사례)을 막는다 (fitting 59 A-B: 0.746->0.797).
    monkeypatch.setenv(P.PARSING_ENV, "1")
    photo = _synthetic_wb_sensitive()
    monkeypatch.setattr(P, "bottom_mask", lambda image: _seg_for(photo, {"bottom": P.PANTS}))
    obs = C.extract(photo)
    assert max(abs(o - e) for o, e in zip(obs.bottom.rgb, (232, 220, 160))) <= 6


# --- L2c: 마스크로 머리·신발 국소화 --------------------------------------
# eval hair fallback 10/10 (기본 #3a2a1c만 성김)을 마스크로 직접 잰다.
# 신발도 SHOE 상수 검정 대신 Left/Right-shoe 클래스 색으로.

def test_extract_hair_uses_mask_when_enabled(monkeypatch):
    monkeypatch.setenv(P.PARSING_ENV, "1")
    photo = _synthetic_wb_sensitive()
    # 머리 영역을 청록색으로 바꾸고 마스크로 Hair 클래스 지정
    px = photo.image.load()
    for y in range(60, 80):
        for x in range(80, 120):
            px[x, y] = (0, 170, 170)
    seg = np.zeros((photo.image.height, photo.image.width), np.uint8)
    seg[60:80, 80:120] = 2          # Hair 클래스
    seg[205:400, 70:130] = P.PANTS
    monkeypatch.setattr(P, "bottom_mask", lambda im: seg)
    obs = C.extract(photo)
    assert obs.hair.hex == "#00aaaa", obs.hair.hex

def test_extract_hair_mask_beats_small_face_blanking(monkeypatch):
    # small flag이면 지금은 헤어를 블랭크(끌지 않음)한다 — 마스크라면 실측 영역이 있어 측정한다.
    monkeypatch.setenv(P.PARSING_ENV, "1")
    photo = _synthetic_wb_sensitive()
    px = photo.image.load()
    for y in range(60, 80):
        for x in range(80, 120):
            px[x, y] = (0, 170, 170)
    photo = photo._replace(degrade=("small",)) if hasattr(photo, "_replace") else photo
    photo = Q.PhotoInput(photo.path, photo.image, photo.face, photo.quality, ("small",))
    seg = np.zeros((photo.image.height, photo.image.width), np.uint8)
    seg[60:80, 80:120] = 2
    seg[205:400, 70:130] = P.PANTS
    monkeypatch.setattr(P, "bottom_mask", lambda im: seg)
    obs = C.extract(photo)
    assert obs.hair.hex == "#00aaaa"


def test_extract_hair_mask_beats_hair_bbox(monkeypatch):
    # VLM hair_bbox를 무시한다 — 실측 마스크가 우선이고 mask가 색을 못 찾으면 bbox 폴백이다.
    monkeypatch.setenv(P.PARSING_ENV, "1")
    photo = _synthetic_wb_sensitive()
    px = photo.image.load()
    for y in range(60, 80):
        for x in range(80, 120):
            px[x, y] = (0, 170, 170)
    seg = np.zeros((photo.image.height, photo.image.width), np.uint8)
    seg[60:80, 80:120] = 2
    seg[205:400, 70:130] = P.PANTS
    monkeypatch.setattr(P, "bottom_mask", lambda im: seg)
    from skinmaker import colors as CM
    observed = C.extract(photo, hair_bbox=Q.FaceBox(0, 0, 20, 20))
    assert observed.hair.hex == "#00aaaa"


def test_extract_shoe_sample_from_mask(monkeypatch):
    monkeypatch.setenv(P.PARSING_ENV, "1")
    photo = _synthetic_wb_sensitive()
    image = photo.image
    px = image.load()
    for y in range(380, 400):        # 신발 (빨강)
        for x in range(70, 130):
            px[x, y] = (220, 40, 30)
    seg = np.zeros((image.height, image.width), np.uint8)
    seg[60:80, 80:120] = 2
    seg[205:400, 70:130] = P.PANTS
    seg[380:400, 70:130] = 9         # Left-shoe
    monkeypatch.setattr(P, "bottom_mask", lambda im: seg)
    obs = C.extract(photo)
    assert obs.shoe.hex == "#dc281e", obs.shoe


def test_render_shoes_use_mask_colour(monkeypatch):
    monkeypatch.setenv(P.PARSING_ENV, "1")
    photo = _synthetic_wb_sensitive()
    image = photo.image
    px = image.load()
    for y in range(380, 400):
        for x in range(70, 130):
            px[x, y] = (220, 40, 30)
    seg = np.zeros((image.height, image.width), np.uint8)
    seg[380:400, 70:130] = 9
    monkeypatch.setattr(P, "bottom_mask", lambda im: seg)
    obs = C.extract(photo)
    canvas = R.render(obs, A.EMPTY, (), "classic")
    # 앞면 다리 (side 9-11 중 앞줄) 색이 신발색인지
    front = canvas.layout.face("r_leg", "front", 0)
    row = 10
    cols = [canvas.get("r_leg", "front", u, row) for u in range(front.w)]
    assert all(c[:3] == (220, 40, 30) for c in cols), cols  # front shade 1.0 -> 신발색 그대로
