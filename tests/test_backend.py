"""backend API 계약 (네트워크 없음. transport는 mock으로 주입)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

import backend.app as A
from skinmaker.vlm.mock import MockTransport

GOOD = {
    "top_garment": "tee",
    "bottom_garment": "shorts",
    "pattern": "plain",
    "sleeve_len": "short",
    "hair_length": "medium",
    "hair_bbox": [200, 50, 800, 600],
}

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PHOTO = FIXTURES / "messi5.jpg"

# hair_bbox 배선용 픽스처. messi5+GOOD([200,50,800,600]) 조합은 brief 초안이었으나
# 실측 불가: messi5의 머리카락이 짙고 작아 어떤 박스로도 점유율 0.18을 못 넘긴다
# (최대 0.09). 대신 7f18 사진의 실측 확신 헤어 박스(239,46,30,45)를 쓴다.
# 정규화 bbox [557,65,676,128]은 back_to_original 왕복이 정확히 일치한다.
PHOTO_HAIR = FIXTURES / "7f18cb16d51f6228b635d23c18772c05.jpg"
GOOD_HAIR = {
    "top_garment": "tee",
    "bottom_garment": "shorts",
    "pattern": "plain",
    "sleeve_len": "short",
    "hair_length": "medium",
    "hair_bbox": [557, 65, 676, 128],
}


def client(first=None, second=None):
    first = first or GOOD
    A.make_transport = lambda: MockTransport(first=first, second=second)
    return TestClient(A.app)


# client() 가 A.make_transport 를 덮어쓰므로, env 기반 경로를 검사하려면 원본을 보관한다.
_REAL_MAKE_TRANSPORT = A.make_transport


def test_health_ok():
    A.make_transport = lambda: MockTransport(first=GOOD)
    r = TestClient(A.app).get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_env_mock_transport_generates_with_default_scenario(monkeypatch):
    """SKINMAKER_TRANSPORT=mock 만으로도 로컬 생성이 끝까지 간다 (기본 시나리오).

    시나리오를 주입하지 않은 mock 은 complete() 가 None 을 돌려줘 502 가 됐다.
    .env 에 mock 만 넣는 오프라인 개발 경로(AGENTS.md)가 실제로 동작해야 한다.
    """
    monkeypatch.setattr(A, "make_transport", _REAL_MAKE_TRANSPORT)
    monkeypatch.setenv("SKINMAKER_TRANSPORT", "mock")
    with PHOTO.open("rb") as f:
        r = TestClient(A.app).post("/api/v1/generate-skin", files={"file": ("m.jpg", f, "image/jpeg")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert body["data"]["skins"]


def test_generate_returns_three_urls():
    second = dict(GOOD, sleeve_len="long", hair_length="long")
    with PHOTO.open("rb") as f:
        r = client(GOOD, second).post("/api/v1/generate-skin", files={"file": ("m.jpg", f, "image/jpeg")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert len(body["data"]["skins"]) == 3
    assert all(u.startswith("/static/skins/") for u in body["data"]["skins"])
    # 파일 실재 확인
    from backend.app import STATIC_DIR

    for u in body["data"]["skins"]:
        assert (STATIC_DIR / Path(u).name).exists()


def test_generate_returns_flat_variants():
    """Edit Skin 토글 재료 (설계 §5): skins_flat이 skins와 같은 순서·길이,
    디스크에 실재하고, ON 파일과 신발 행 밖 픽셀이 동일하다."""
    second = dict(GOOD, sleeve_len="long", hair_length="long")
    with PHOTO.open("rb") as f:
        r = client(GOOD, second).post("/api/v1/generate-skin", files={"file": ("m.jpg", f, "image/jpeg")})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    flats = data["skins_flat"]
    assert len(flats) == len(data["skins"])
    from PIL import Image as PILImage

    allowed = _admin_leg_shoe_pixels()
    for on, flat in zip(data["skins"], flats):
        on_name, flat_name = Path(on).name, Path(flat).name
        assert flat_name == on_name.replace(".png", "_flat.png"), (on_name, flat_name)
        assert (A.STATIC_DIR / on_name).exists() and (A.STATIC_DIR / flat_name).exists()
        # 신발 행 밖 동일 (계약 테스트 동일 근거)
        px_on = PILImage.open(A.STATIC_DIR / on_name).convert("RGBA").load()
        px_flat = PILImage.open(A.STATIC_DIR / flat_name).convert("RGBA").load()
        diff = {(x, y) for y in range(64) for x in range(64) if px_on[x, y] != px_flat[x, y]}
        assert diff, "신발 행 차이 없음"
        assert diff <= allowed, diff - allowed


def _admin_leg_shoe_pixels():
    from skinmaker.format import get_layout

    layout = get_layout("classic")
    allowed = set()
    for part in ("r_leg", "l_leg"):
        for face in layout.part(part, 0).faces.values():
            if face.h < 12:
                continue
            for v in range(9, face.h):
                for u in range(face.w):
                    allowed.add((face.x + u, face.y + v))
    return allowed


def test_generate_noise_level_contract():
    """설계 §9: noise_level 폼 필드 — 부재=1.0, 가비지=400, 범위 밖=클램프, 0=무노이즈."""
    from PIL import Image as PILImage

    second = dict(GOOD, sleeve_len="long", hair_length="long")
    post = lambda lvl: client(GOOD, second).post(
        "/api/v1/generate-skin",
        files={"file": ("m.jpg", PHOTO.open("rb").read(), "image/jpeg")},
        data={} if lvl is None else {"noise_level": lvl},
    )
    r_garbage = post("abc")
    assert r_garbage.status_code == 400
    assert r_garbage.json()["detail"]["code"] == "bad_noise_level"

    r0, r1, r7 = post("0"), post("1"), post("7")
    assert r0.status_code == r1.status_code == r7.status_code == 200
    png0 = A.STATIC_DIR / Path(r0.json()["data"]["skins"][0]).name
    png1 = A.STATIC_DIR / Path(r1.json()["data"]["skins"][0]).name
    png7 = A.STATIC_DIR / Path(r7.json()["data"]["skins"][0]).name
    b0 = PILImage.open(png0).convert("RGBA").tobytes()
    b1 = PILImage.open(png1).convert("RGBA").tobytes()
    b7 = PILImage.open(png7).convert("RGBA").tobytes()
    assert b0 != b1          # 0은 무노이즈 — 1과 다르다
    assert b7 == b1          # 7은 [0,1]로 클램프 → 1과 동일


UPPER_PHOTO = FIXTURES / "ex6(half).png"


def _upper_body_seg(monkeypatch):
    """하의/맨다리 픽셀이 하나도 없는 마스크 — 상반신 사진의 파서 관측을 대신한다.

    실제 66MB SCHP 모델 없이도 jeans 기본 규칙(하체 미관측)을 검증한다.
    """
    import numpy as np

    from skinmaker import parsing

    monkeypatch.setattr(
        parsing, "bottom_mask",
        lambda im: np.zeros((im.height, im.width), dtype=np.uint8),
    )


def test_generate_upper_body_defaults_to_jeans(monkeypatch):
    """상반신 사진 + S2 bottom=none → 스킨은 jeans 행, summary도 jeans (설계 §10)."""
    from PIL import Image as PILImage

    from skinmaker.format import get_layout
    from skinmaker.render import DEFAULT_JEANS, FACE_SHADE, NOISE_TOL
    from skinmaker.canvas import rgba, shade

    _upper_body_seg(monkeypatch)
    with UPPER_PHOTO.open("rb") as f:
        r = client(dict(GOOD, bottom_garment="none"), None).post(
            "/api/v1/generate-skin", files={"file": ("m.png", f, "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert "bottom_garment=jeans" in body["summary"], body["summary"]
    img = PILImage.open(A.STATIC_DIR / Path(body["skins"][0]).name).convert("RGBA")
    L = get_layout("classic")
    f = L.face("r_leg", "front", 0)
    jeans = shade(rgba(DEFAULT_JEANS), FACE_SHADE["front"])[:3]
    for v in range(9):
        got = img.getpixel((f.x + 1, f.y + v))[:3]
        # 파이프라인 렌더는 노이즈가 얹힌다 (설계 §3): 톨러런스 프로브.
        assert all(abs(p - q) <= NOISE_TOL for p, q in zip(got, jeans)), (v, got, jeans)


def test_generate_returns_category_payload():
    """설계 §11: 분류 카테고리를 구조화 JSON으로 — 사용자가 본다."""
    second = dict(GOOD, sleeve_len="long", hair_length="long")
    with PHOTO.open("rb") as f:
        r = client(GOOD, second).post("/api/v1/generate-skin", files={"file": ("m.jpg", f, "image/jpeg")})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    a = data["attributes"]
    for field in ("top_garment", "bottom_garment", "pattern", "sleeve_len", "hair_length"):
        assert field in a["values"], a["values"]
    assert a["uncertain"] == data["uncertain"]
    cands = data["candidates"]
    assert [c["index"] for c in cands] == [1, 2, 3]
    assert cands[0]["varied"] == "as-answered"
    assert cands[1]["varied"] != "as-answered"
    assert data["noise_level"] == 1.0


def test_generate_category_payload_records_derived(monkeypatch):
    """하체 미관측 jeans 기본이 발동하면 derived에 표기된다 (설계 §10·§11)."""
    _upper_body_seg(monkeypatch)
    with UPPER_PHOTO.open("rb") as f:
        r = client(dict(GOOD, bottom_garment="none"), None).post(
            "/api/v1/generate-skin", files={"file": ("m.png", f, "image/png")})
    assert r.status_code == 200, r.text
    a = r.json()["data"]["attributes"]
    assert a["values"]["bottom_garment"] == "jeans"
    assert any("bottom_garment" in d for d in a["derived"]), a["derived"]


def test_generate_echoes_hair_options():
    """Tier 0 (2026-10-15): 머리 실루엣 근원/대칭 폼 필드.

    부재 → 기본(mask, symmetrized) 적용 + 응답 에코 (noise_level 관례).
    rule은 오늘 렌더와 픽셀 동일 베이스라인 (스텐실 미생성).
    """
    def post(**form):
        with PHOTO.open("rb") as f:
            return client().post("/api/v1/generate-skin",
                                 files={"file": ("m.jpg", f, "image/jpeg")}, data=form)

    r_default = post()
    assert r_default.status_code == 200, r_default.text
    body = r_default.json()["data"]
    assert body["hair_source"] == "mask"
    assert body["hair_symmetry"] == "symmetrized"
    assert body["hair_overlay"] == "on"

    r_off = post(hair_overlay="off")
    assert r_off.status_code == 200
    assert r_off.json()["data"]["hair_overlay"] == "off"
    r_rule = post(hair_source="rule", hair_symmetry="raw")
    assert r_rule.status_code == 200
    body = r_rule.json()["data"]
    assert body["hair_source"] == "rule"
    assert body["hair_symmetry"] == "raw"


def test_generate_rejects_bad_hair_option():
    with PHOTO.open("rb") as f:
        r = client().post("/api/v1/generate-skin",
                          files={"file": ("m.jpg", f, "image/jpeg")},
                          data={"hair_source": "bogus"})
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "bad_hair_option"


def test_generate_returns_steps_sheets():
    """설계 §12: 처리 과정 시트 (간단/QA) — steps/ 하위폴더에 저장, 응답 data.steps.

    실앱 404 사건 (2026-10-13): 저장 위치(STATIC_DIR/steps=skins/steps)와 URL
    (/static/steps/)가 어긋나 브라우저에서 404. 테스트는 URL을 실제로 페치해야
    배선 불일치를 잡는다 — 파일 존재 + URL 접두사 검사만으로는 못 잡았다."""
    second = dict(GOOD, sleeve_len="long", hair_length="long")
    c = client(GOOD, second)
    with PHOTO.open("rb") as f:
        r = c.post("/api/v1/generate-skin", files={"file": ("m.jpg", f, "image/jpeg")})
    assert r.status_code == 200, r.text
    steps = r.json()["data"]["steps"]
    assert set(steps) == {"clean", "full"}
    for url in steps.values():
        assert url.startswith("/static/steps/")
        p = A.ROOT / "static" / "steps" / Path(url).name
        assert p.exists() and p.stat().st_size > 1000, url
        got = c.get(url)  # URL이 실제로 서빙되는지 — 저장 위치와 응답 URL의 배선 검사
        assert got.status_code == 200, (url, got.status_code)
        assert got.content[:8] == b"\x89PNG\r\n\x1a\n" and len(got.content) > 1000, url


def test_generate_steps_flag_skips_sheets():
    """설정 체크박스 (기본 해제): steps=0 → 시트 미생성, 응답 steps=null.
    부재 → 기존 동작(생성). 진위 규칙은 parsing_on 관례와 동일."""
    second = dict(GOOD, sleeve_len="long", hair_length="long")
    post = lambda lvl: client(GOOD, second).post(
        "/api/v1/generate-skin",
        files={"file": ("m.jpg", PHOTO.open("rb").read(), "image/jpeg")},
        data={} if lvl is None else {"steps": lvl},
    )
    r_off = post("0")
    assert r_off.status_code == 200, r_off.text
    data = r_off.json()["data"]
    assert data["steps"] is None
    token_off = Path(data["skins"][0]).name.split("_")[0]
    assert not (A.ROOT / "static" / "steps" / f"{token_off}_steps.png").exists()

    for truthy in ("1", "true", "on", "yes"):
        r_on = post(truthy)
        assert r_on.status_code == 200
        assert r_on.json()["data"]["steps"] is not None
    r_absent = post(None)
    assert r_absent.json()["data"]["steps"] is not None  # 부재 = 기존 동작


def test_non_image_rejected():
    r = client().post("/api/v1/generate-skin", files={"file": ("x.txt", b"hi", "text/plain")})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "not_image"


def test_no_face_reports_422_with_message(tmp_path):
    from PIL import Image as PILImage

    blank = tmp_path / "blank.jpg"
    PILImage.new("RGB", (200, 200), (30, 60, 90)).save(blank)
    with blank.open("rb") as f:
        r = client().post("/api/v1/generate-skin", files={"file": ("b.jpg", f, "image/jpeg")})
    assert r.status_code == 422
    body = r.json()["detail"]
    assert body["code"] == "no_face"
    assert "얼굴" in body["message"]


def test_classify_failure_maps_to_502():
    A.make_transport = lambda: MockTransport(fail=True)
    with PHOTO.open("rb") as f:
        r = TestClient(A.app).post("/api/v1/generate-skin", files={"file": ("m.jpg", f, "image/jpeg")})
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "classify_failed"


def test_rate_limit_maps_to_503():
    A.make_transport = lambda: MockTransport(fail=True, error="HTTP 429: quota")
    with PHOTO.open("rb") as f:
        r = TestClient(A.app).post("/api/v1/generate-skin", files={"file": ("m.jpg", f, "image/jpeg")})
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "overloaded"


def test_generate_uses_hair_bbox_for_crown():
    # brief 초안의 `crown != (58,42,28,255)`는 틀렸다. 정수리는 FACE_SHADE[top]
    # 1.12가 적용되므로 배선 전 정수리는 shade(DEFAULT_HAIR)다. 그 값과 다르면 배선됨.
    # 기대 crown은 하드코딩 hex가 아니라 같은 입력(같은 사진+같은 classify bbox)으로
    # extract를 재실행해 구한다. WB·클러스터 문턱 재조정에도 깨지지 않는다.
    from PIL import Image as PILImage

    from skinmaker.canvas import rgba, shade
    from skinmaker.classify import classify
    from skinmaker.colors import extract
    from skinmaker.eval import expected_pixel
    from skinmaker.quality import inspect
    from skinmaker.render import DEFAULT_HAIR, FACE_SHADE
    from skinmaker.render import NOISE_TOL as _NOISE_TOL

    with PHOTO_HAIR.open("rb") as f:
        r = client(GOOD_HAIR, None).post("/api/v1/generate-skin", files={"file": ("h.jpg", f, "image/jpeg")})
    assert r.status_code == 200, r.text
    url = r.json()["data"]["skins"][0]
    img = PILImage.open(A.STATIC_DIR / Path(url).name).convert("RGBA")
    crown = img.getpixel((8, 0))  # head top 면 (0,0) = 스킨 (8,0)
    default_crown = shade(rgba(DEFAULT_HAIR), FACE_SHADE["top"])
    assert crown != default_crown

    photo = inspect(str(PHOTO_HAIR))
    result = classify(photo, MockTransport(first=GOOD_HAIR))
    assert result.ok and result.hair_bbox_px is not None
    observed = extract(photo, hair_bbox=result.hair_bbox_px)
    assert observed.hair.confident  # 픽스처 변별력 가드: retune으로 미달이 되면 여기서 loudly 실패
    expected = expected_pixel(observed, "hair", "top")
    # 노이즈 파이프라인 (설계 §3): 등식은 채널별 톨러런스로.
    assert all(abs(p - q) <= _NOISE_TOL for p, q in zip(crown[:3], expected[:3])), (crown, expected)


def test_generate_returns_input_photo_url():
    with PHOTO.open("rb") as f:
        r = client().post("/api/v1/generate-skin", files={"file": ("m.jpg", f, "image/jpeg")})
    assert r.status_code == 200, r.text
    body = r.json()
    input_url = body["data"]["input"]
    assert input_url.startswith("/static/skins/input_")
    from backend.app import STATIC_DIR

    saved = STATIC_DIR / Path(input_url).name
    assert saved.exists()
    assert saved.read_bytes() == PHOTO.read_bytes()  # 사진과 동일 바이트


def test_generate_rejects_oversize_upload(monkeypatch):
    monkeypatch.setenv("SKINMAKER_MAX_UPLOAD_MB", "1")
    payload = b"\xff\xd8" + b"x" * (1024 * 1024 + 1)
    r = client().post("/api/v1/generate-skin", files={"file": ("big.jpg", payload, "image/jpeg")})
    assert r.status_code == 413, r.text
    assert r.json()["detail"]["code"] == "too_large"


def test_generate_rate_limited(monkeypatch):
    from backend.limits import RateLimiter

    monkeypatch.setattr(A, "_rate_limiter", RateLimiter(limit=1))
    with PHOTO.open("rb") as f:
        first = client().post("/api/v1/generate-skin", files={"file": ("m.jpg", f, "image/jpeg")})
    assert first.status_code == 200, first.text
    with PHOTO.open("rb") as f:
        second = client().post("/api/v1/generate-skin", files={"file": ("m.jpg", f, "image/jpeg")})
    assert second.status_code == 429, second.text
    assert second.json()["detail"]["code"] == "rate_limited"
