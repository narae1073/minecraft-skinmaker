"""Owner-only skin jobs through the real generate route (mock transport)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.app as A
from backend import jobs as JOBS
from skinmaker.vlm.mock import MockTransport

PHOTO = Path(__file__).resolve().parent / "fixtures" / "messi5.jpg"
GOOD = {
    "top_garment": "tee", "bottom_garment": "jeans", "pattern": "plain",
    "sleeve_len": "short", "hair_length": "medium", "hair_style": "bob",
    "hood": "none", "hair_bbox": [557, 65, 676, 128],
}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(JOBS, "PRIVATE_DIR", tmp_path / "private")
    monkeypatch.setattr(JOBS, "JOBS_DIR", tmp_path / "private" / "jobs")
    monkeypatch.setattr(JOBS, "INPUTS_DIR", tmp_path / "private" / "inputs")
    static = tmp_path / "static"
    static.mkdir()
    monkeypatch.setattr(A, "STATIC_DIR", static)
    monkeypatch.setattr(A, "make_transport", lambda: MockTransport(first=GOOD))
    monkeypatch.setattr(A, "_render_limiter", A.RateLimiter(limit=1000))
    return static


def _generate(client):
    with open(PHOTO, "rb") as fh:
        return client.post("/api/v1/generate-skin", files={"file": ("m.jpg", fh, "image/jpeg")})


def test_generate_sets_owner_cookie_and_keeps_input_private(_isolated):
    client = TestClient(A.app)
    r = _generate(client)
    assert r.status_code == 200, r.text
    assert "skinmaker_owner" in r.headers.get("set-cookie", "")
    data = r.json()["data"]
    assert data["input"].startswith("/api/v1/jobs/") and data["job"]["editable"] is True
    token = data["job"]["id"]
    assert (JOBS.INPUTS_DIR / f"{token}.jpg").is_file()
    assert not [p for p in _isolated.iterdir() if p.name.startswith("input_")]
    assert JOBS.load_record(token) is not None


def test_only_the_generating_browser_can_read_or_edit_the_job(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    assert owner.get(f"/api/v1/jobs/{token}").status_code == 200
    stranger = TestClient(A.app)
    assert stranger.get(f"/api/v1/jobs/{token}").status_code == 403
    assert stranger.get(f"/api/v1/jobs/{token}/input").status_code == 403
    assert stranger.put(f"/api/v1/jobs/{token}/overlay", json={"masks": {}}).status_code == 403
    assert stranger.post(f"/api/v1/jobs/{token}/render", json={"index": 1}).status_code == 403
    assert TestClient(A.app).get("/api/v1/jobs/0123456789ab").status_code == 404
    assert TestClient(A.app).get("/api/v1/jobs/../../etc").status_code in (403, 404)


def test_owner_input_is_served_privately(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    r = owner.get(f"/api/v1/jobs/{token}/input")
    assert r.status_code == 200 and r.content[:3] == b"\xff\xd8\xff"
    assert r.headers.get("cache-control", "").startswith("private")


def test_overlay_put_validates_and_requires_json(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    assert owner.put(f"/api/v1/jobs/{token}/overlay", content=b"{}",
                     headers={"Content-Type": "text/plain"}).status_code == 415
    bad = {"top_garment.tee": {"L1": {"body.front": [[2]]}, "L2": {}}}
    assert owner.put(f"/api/v1/jobs/{token}/overlay", json={"masks": bad}).status_code == 400
    good = {"top_garment.tee": {"L1": {"body.front": [[0] * 8 for _ in range(12)]}, "L2": {}}}
    r = owner.put(f"/api/v1/jobs/{token}/overlay", json={"masks": good})
    assert r.status_code == 200 and r.json()["data"]["revision"] == 1
    assert owner.get(f"/api/v1/jobs/{token}/overlay").json()["masks"] == good


def test_empty_overlay_render_matches_the_original_output(_isolated):
    owner = TestClient(A.app)
    data = _generate(owner).json()["data"]
    token = data["job"]["id"]
    original = (_isolated / f"{token}_c1.png").read_bytes()
    r = owner.post(f"/api/v1/jobs/{token}/render", json={"index": 1})
    assert r.status_code == 200, r.text
    rendered = (_isolated / f"{token}_e0_c1.png").read_bytes()
    assert rendered == original


def test_render_with_overlay_changes_the_output_and_bad_index_is_404(_isolated):
    owner = TestClient(A.app)
    data = _generate(owner).json()["data"]
    token = data["job"]["id"]
    before = (_isolated / f"{token}_c1.png").read_bytes()
    owner.put(f"/api/v1/jobs/{token}/overlay", json={"masks": {
        "top_garment.tee": {"L1": {"body.front": [[0] * 8 for _ in range(12)]}, "L2": {}}}})
    r = owner.post(f"/api/v1/jobs/{token}/render", json={"index": 1})
    assert r.status_code == 200, r.text
    assert (_isolated / f"{token}_e1_c1.png").read_bytes() != before
    assert owner.post(f"/api/v1/jobs/{token}/render", json={"index": 9}).status_code == 404
