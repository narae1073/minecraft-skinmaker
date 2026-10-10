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

PHOTO = Path(__file__).resolve().parent.parent / "out" / "s0_photos" / "messi5.jpg"

# hair_bbox 배선용 픽스처. messi5+GOOD([200,50,800,600]) 조합은 brief 초안이었으나
# 실측 불가: messi5의 머리카락이 짙고 작아 어떤 박스로도 점유율 0.18을 못 넘긴다
# (최대 0.09). 대신 7f18 사진의 실측 확신 헤어 박스(239,46,30,45)를 쓴다.
# 정규화 bbox [557,65,676,128]은 back_to_original 왕복이 정확히 일치한다.
PHOTO_HAIR = Path(__file__).resolve().parent.parent / "out" / "s0_photos" / "7f18cb16d51f6228b635d23c18772c05.jpg"
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


def test_health_ok():
    A.make_transport = lambda: MockTransport(first=GOOD)
    r = TestClient(A.app).get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


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
    assert crown == expected_pixel(observed, "hair", "top")
