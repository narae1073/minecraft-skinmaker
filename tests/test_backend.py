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
