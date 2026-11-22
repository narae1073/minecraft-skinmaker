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
    static = tmp_path / "static"
    static.mkdir()
    monkeypatch.setattr(A, "STATIC_DIR", static)
    monkeypatch.setattr(A, "make_transport", lambda: MockTransport(first=GOOD))
    monkeypatch.setattr(A, "_render_limiter", A.RateLimiter(limit=1000))
    return static


def _generate(client):
    with open(PHOTO, "rb") as fh:
        return client.post("/api/v1/generate-skin", files={"file": ("m.jpg", fh, "image/jpeg")})


def test_generate_sets_owner_cookie_and_stores_no_input(_isolated):
    client = TestClient(A.app)
    r = _generate(client)
    assert r.status_code == 200, r.text
    assert "skinmaker_owner" in r.headers.get("set-cookie", "")
    data = r.json()["data"]
    assert "input" not in data and data["job"]["editable"] is True
    token = data["job"]["id"]
    assert not (_isolated.parent / "private" / "inputs").exists()
    assert not [p for p in _isolated.iterdir() if p.name.startswith("input_")]
    assert JOBS.load_record(token) is not None


def test_only_the_generating_browser_can_read_or_edit_the_job(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    assert owner.get(f"/api/v1/jobs/{token}").status_code == 200
    stranger = TestClient(A.app)
    assert stranger.get(f"/api/v1/jobs/{token}").status_code == 403
    assert stranger.get(f"/api/v1/jobs/{token}/input").status_code == 404
    assert stranger.put(f"/api/v1/jobs/{token}/overlay", json={"masks": {}}).status_code == 403
    assert stranger.post(f"/api/v1/jobs/{token}/render", json={"index": 1}).status_code == 403
    assert TestClient(A.app).get("/api/v1/jobs/0123456789ab").status_code == 404
    assert TestClient(A.app).get("/api/v1/jobs/../../etc").status_code in (403, 404)


def test_overlay_put_validates_and_requires_json(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    assert owner.put(f"/api/v1/jobs/{token}/overlay", content=b"{}",
                     headers={"Content-Type": "text/plain"}).status_code == 415
    bad = {"top_garment.tee": {"L1": {"body.front": [[2]]}, "L2": {}}}
    assert owner.put(f"/api/v1/jobs/{token}/overlay", json={"masks": bad}).status_code == 400
    good = {"top_garment.tee": {"L1": {"body.front": [[0] * 8 for _ in range(12)]}, "L2": {}}}
    r = owner.put(f"/api/v1/jobs/{token}/overlay", json={"masks": good})
    assert r.status_code == 200 and r.json()["revision"] == 1
    assert r.json()["changed"] == ["top_garment.tee"]
    stored = owner.get(f"/api/v1/jobs/{token}/overlay").json()["masks"]
    assert stored["top_garment.tee"]["L1"]["body.front"] == good["top_garment.tee"]["L1"]["body.front"]


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


def _editor(owner, token, **params):
    return owner.get(f"/api/v1/jobs/{token}/editor", params=params)


def test_editor_payload_has_the_atlas_masks_and_baseline(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    r = _editor(owner, token)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["atlas"]["size"] == 64 and len(d["atlas"]["rects"]["L1"]) == 36
    assert d["slim"]["sub_faces"]
    assert len(d["masks"]) == 56 and "hair_style.bob" in d["masks"]
    assert d["enums"]["top_garment"] and d["combo"]["top_garment"]
    base = _editor(owner, token, baseline=1).json()["masks"]
    assert base == d["masks"]  # nothing edited yet


def test_unedited_preview_matches_the_job_render(_isolated):
    import base64
    import io
    from PIL import Image
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    masks = _editor(owner, token).json()["masks"]
    r = owner.post(f"/api/v1/jobs/{token}/preview", json={"masks": masks, "index": 1})
    assert r.status_code == 200, r.text
    png = base64.b64decode(r.json()["skin"].split(",", 1)[1])
    preview = Image.open(io.BytesIO(png)).convert("RGBA")
    original = Image.open(io.BytesIO((_isolated / f"{token}_c1.png").read_bytes())).convert("RGBA")
    assert preview.tobytes() == original.tobytes()


def test_edited_preview_differs_and_save_stores_only_the_change(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    masks = _editor(owner, token).json()["masks"]
    edited = {k: v for k, v in masks.items()}
    entry = {layer: {face: [row[:] for row in grid] for face, grid in faces.items()}
             for layer, faces in masks["top_garment.tee"].items()}
    entry["L1"]["body.front"] = [[0] * 8 for _ in range(12)]
    edited["top_garment.tee"] = entry
    r = owner.post(f"/api/v1/jobs/{token}/preview", json={"masks": edited, "index": 1})
    assert r.status_code == 200, r.text
    orig = owner.post(f"/api/v1/jobs/{token}/preview", json={"masks": masks, "index": 1}).json()["skin"]
    assert r.json()["skin"] != orig
    saved = owner.put(f"/api/v1/jobs/{token}/overlay", json={"masks": edited, "index": 1})
    assert saved.status_code == 200, saved.text
    assert saved.json()["changed"] == ["top_garment.tee"]


def test_seed_endpoint_returns_the_baseline_entry(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    r = owner.get(f"/api/v1/jobs/{token}/seed", params={"key": "hair_style", "value": "bob"})
    assert r.status_code == 200, r.text
    assert r.json()["mask"]["L1"]
    assert owner.get(f"/api/v1/jobs/{token}/seed", params={"key": "nope", "value": "x"}).status_code == 400


def test_editor_endpoints_are_owner_only_and_validate_the_index(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    stranger = TestClient(A.app)
    assert _editor(stranger, token).status_code == 403
    assert stranger.get(f"/api/v1/jobs/{token}/seed", params={"key": "hood", "value": "up"}).status_code == 403
    assert stranger.post(f"/api/v1/jobs/{token}/preview", json={"masks": {}}).status_code == 403
    assert _editor(owner, token, index=9).status_code == 404
    assert owner.post(f"/api/v1/jobs/{token}/preview", json={"masks": {"x": 1}, "index": 1}).status_code == 400


def test_editor_page_is_owner_only_and_only_serves_editor_assets(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    page = owner.get(f"/edit/{token}")
    assert page.status_code == 200
    assert f'window.MASK_EDITOR_JOB = "{token}"' in page.text
    assert "/edit/lib/app.js" in page.text and "/static/" not in page.text
    # Job mode saves to this skin's overlay, not the developer draft file.
    assert "out/mask_editor/attribute_masks.json" not in page.text
    assert "저장은 이 스킨에만 적용됩니다" in page.text
    assert TestClient(A.app).get(f"/edit/{token}").status_code == 403
    assert owner.get("/edit/lib/app.js").status_code == 200
    assert owner.get("/edit/lib/vendor/three.module.js").status_code == 200
    # Traversal is normalised by the client; what matters is that no source file is served.
    for probe in ("/edit/lib/../app.py", "/edit/lib/vendor/../../backend/app.py", "/edit/lib/app.py"):
        r = owner.get(probe)
        assert r.status_code != 200 and b"FastAPI" not in r.content and b"def " not in r.content, probe


def test_headwear_toggle_is_per_skin_and_puts_the_cap_draft_in_the_overlay(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    other = _generate(owner).json()["data"]["job"]["id"]
    assert owner.post(f"/api/v1/jobs/{token}/attributes", json={"headwear": "fedora"}).status_code == 400
    r = owner.post(f"/api/v1/jobs/{token}/attributes", json={"headwear": "cap"})
    assert r.status_code == 200, r.text
    overlay = owner.get(f"/api/v1/jobs/{token}/overlay").json()["masks"]
    assert "headwear.cap" in overlay and set(overlay["headwear.cap"]["L1"]) >= {"head.top", "head.front"}
    editor = owner.get(f"/api/v1/jobs/{token}/editor").json()
    assert editor["combo"]["headwear"] == "cap"
    # The other skin is untouched.
    assert owner.get(f"/api/v1/jobs/{other}/editor").json()["combo"]["headwear"] == "none"
    assert "headwear.cap" not in owner.get(f"/api/v1/jobs/{other}/overlay").json()["masks"]
    stranger = TestClient(A.app)
    assert stranger.post(f"/api/v1/jobs/{token}/attributes", json={"headwear": "none"}).status_code == 403


def test_cap_render_shows_the_hat_and_none_matches_the_original(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    original = (_isolated / f"{token}_c1.png").read_bytes()
    owner.post(f"/api/v1/jobs/{token}/attributes", json={"headwear": "none"})
    assert owner.post(f"/api/v1/jobs/{token}/render", json={"index": 1}).status_code == 200
    # headwear none on a candidate that had none: the skin is the same as before
    assert (_isolated / f"{token}_e1_c1.png").read_bytes() == original
    owner.post(f"/api/v1/jobs/{token}/attributes", json={"headwear": "cap"})
    assert owner.post(f"/api/v1/jobs/{token}/render", json={"index": 1}).status_code == 200
    assert (_isolated / f"{token}_e2_c1.png").read_bytes() != original


def test_beanie_is_per_skin_and_uses_its_draft(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    assert owner.post(f"/api/v1/jobs/{token}/attributes", json={"headwear": "beanie"}).status_code == 200
    overlay = owner.get(f"/api/v1/jobs/{token}/overlay").json()["masks"]
    assert "headwear.beanie" in overlay and "headwear.cap" not in overlay
    assert owner.get(f"/api/v1/jobs/{token}/editor").json()["combo"]["headwear"] == "beanie"


def test_hat_colour_is_per_skin_and_validated(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    assert owner.post(f"/api/v1/jobs/{token}/attributes",
                      json={"headwear": "cap", "hat_color": "red"}).status_code == 400
    assert owner.post(f"/api/v1/jobs/{token}/attributes",
                      json={"headwear": "cap", "hat_color": "#ff0000"}).status_code == 200
    assert owner.post(f"/api/v1/jobs/{token}/render", json={"index": 1}).status_code == 200
    from PIL import Image
    img = Image.open(_isolated / f"{token}_e1_c1.png").convert("RGBA")
    px = img.load()
    reds = sum(1 for x in range(img.width) for y in range(img.height)
               if px[x, y][0] > 200 and px[x, y][1] < 60 and px[x, y][2] < 60)
    assert reds > 40
    assert owner.post(f"/api/v1/jobs/{token}/attributes", json={"headwear": "none"}).status_code == 200


def test_job_editor_flag_off_disables_jobs_and_routes(_isolated, monkeypatch):
    monkeypatch.setenv("SKINMAKER_JOB_EDITOR", "0")
    owner = TestClient(A.app)
    r = _generate(owner)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data.get("job") is None
    token = Path(data["skins"][0]).name.split("_")[0]
    assert not (Path(_isolated).parent / "private" / "jobs").exists()
    assert "skinmaker_owner" not in r.headers.get("set-cookie", "")
    assert owner.get(f"/edit/{token}").status_code == 404
    assert owner.get(f"/api/v1/jobs/{token}").status_code == 404
    assert owner.get(f"/api/v1/jobs/{token}/editor").status_code == 404
    assert owner.get("/edit/lib/app.js").status_code == 404


def test_health_reports_job_editor_flag(monkeypatch):
    monkeypatch.setenv("SKINMAKER_JOB_EDITOR", "0")
    body = TestClient(A.app).get("/api/v1/health").json()
    assert body["job_editor"] == "off"


def test_clothing_attributes_are_per_skin_and_validated(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    other = _generate(owner).json()["data"]["job"]["id"]
    base = owner.get(f"/api/v1/jobs/{token}/editor").json()["combo"]
    other_base = owner.get(f"/api/v1/jobs/{other}/editor").json()["combo"]

    r = owner.post(f"/api/v1/jobs/{token}/attributes", json={
        "attributes": {"top_garment": "hoodie", "bottom_garment": "jeans", "sleeve_len": "long"},
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overrides"] == {"top_garment": "hoodie", "bottom_garment": "jeans", "sleeve_len": "long"}
    assert body["attributes"]["top_garment"] == "hoodie"
    combo = owner.get(f"/api/v1/jobs/{token}/editor").json()["combo"]
    assert (combo["top_garment"], combo["bottom_garment"], combo["sleeve_len"]) == ("hoodie", "jeans", "long")
    # A different skin keeps its own photo values.
    assert owner.get(f"/api/v1/jobs/{other}/editor").json()["combo"]["top_garment"] == other_base["top_garment"]

    # Unknown value, out-of-scope field, and too many changes are rejected.
    assert owner.post(f"/api/v1/jobs/{token}/attributes",
                      json={"attributes": {"top_garment": "spacesuit"}}).status_code == 400
    assert owner.post(f"/api/v1/jobs/{token}/attributes",
                      json={"attributes": {"pattern": "check"}}).status_code == 400
    assert owner.post(f"/api/v1/jobs/{token}/attributes",
                      json={"attributes": {f"k{i}": "x" for i in range(20)}}).status_code == 400
    assert owner.post(f"/api/v1/jobs/{token}/attributes", json={}).status_code == 400

    # Reset drops the overrides and returns the photo's values.
    r = owner.post(f"/api/v1/jobs/{token}/attributes", json={"reset": True})
    assert r.status_code == 200, r.text
    assert r.json()["overrides"] == {}
    combo = owner.get(f"/api/v1/jobs/{token}/editor").json()["combo"]
    for key in ("top_garment", "bottom_garment", "sleeve_len"):
        assert combo[key] == base[key]


def test_clothing_change_rerenders_the_skin_without_touching_the_original(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    original = (_isolated / f"{token}_c1.png").read_bytes()
    assert owner.post(f"/api/v1/jobs/{token}/attributes",
                      json={"attributes": {"top_garment": "dress"}}).status_code == 200
    assert owner.post(f"/api/v1/jobs/{token}/render", json={"index": 1}).status_code == 200
    assert (_isolated / f"{token}_e1_c1.png").read_bytes() != original
    assert (_isolated / f"{token}_c1.png").read_bytes() == original
    # The editor preview shows the new clothes too.
    masks = owner.get(f"/api/v1/jobs/{token}/editor").json()["masks"]
    preview = owner.post(f"/api/v1/jobs/{token}/preview", json={"masks": masks, "index": 1})
    assert preview.status_code == 200 and preview.json()["skin"].startswith("data:image/png;base64,")


def _flip_first_cell(masks):
    """Toggle one baseline texel so the overlay differs."""
    import copy
    masks = copy.deepcopy(masks)
    for name, entry in masks.items():
        for layer in ("L1", "L2"):
            for grid in (entry.get(layer) or {}).values():
                if grid and grid[0]:
                    grid[0][0] = 1 - grid[0][0]
                    return masks, name
    raise AssertionError("no mask cell to flip")


def _two_candidate_job(client):
    import copy
    token = _generate(client).json()["data"]["job"]["id"]
    record = JOBS.load_record(token)
    second = copy.deepcopy(record["candidates"][0])
    second["index"] = 2
    second["seed"] = int(second["seed"]) + 1
    record["candidates"].append(second)
    JOBS.save_record(record)
    return token


def test_overlays_are_per_candidate_and_restore_works(_isolated):
    owner = TestClient(A.app)
    token = _two_candidate_job(owner)
    base = owner.get(f"/api/v1/jobs/{token}/editor?index=1").json()
    assert base["index"] == 1 and base["candidates"] == [1, 2]
    assert base["history"] == []
    masks, name = _flip_first_cell(base["masks"])

    first = owner.put(f"/api/v1/jobs/{token}/overlay", json={"masks": masks, "index": 1})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["index"] == 1 and name in body["override_names"]
    assert body["history"][0]["revision"] == body["revision"]

    # The other candidate keeps its own baseline.
    other = owner.get(f"/api/v1/jobs/{token}/editor?index=2").json()
    assert name not in other["override_names"]
    assert owner.get(f"/api/v1/jobs/{token}/overlay?index=2").json()["masks"] == {}
    assert owner.get(f"/api/v1/jobs/{token}/overlay?index=9").status_code == 404

    # Saving the baseline again clears the override but keeps both revisions.
    second = owner.put(f"/api/v1/jobs/{token}/overlay", json={"masks": base["masks"], "index": 1})
    assert second.status_code == 200
    assert second.json()["override_names"] == []
    assert [h["revision"] for h in second.json()["history"]] == [second.json()["revision"], body["revision"]]

    # Restoring rev 1 brings the texel back as a new revision.
    restored = owner.post(f"/api/v1/jobs/{token}/restore", json={"index": 1, "revision": body["revision"]})
    assert restored.status_code == 200, restored.text
    assert restored.json()["revision"] != body["revision"]
    editor = owner.get(f"/api/v1/jobs/{token}/editor?index=1").json()
    assert name in editor["override_names"]
    assert editor["history"][0]["revision"] == restored.json()["revision"]

    assert owner.post(f"/api/v1/jobs/{token}/restore", json={"index": 1, "revision": 999}).status_code == 404
    assert owner.post(f"/api/v1/jobs/{token}/restore", json={"index": 9, "revision": 1}).status_code == 404
    assert owner.post(f"/api/v1/jobs/{token}/restore", json={"index": 1, "revision": "x"}).status_code == 400


def test_editor_page_opens_each_candidate_by_index(_isolated):
    owner = TestClient(A.app)
    token = _two_candidate_job(owner)
    page = owner.get(f"/edit/{token}?index=2")
    assert page.status_code == 200
    html = page.text
    assert "MASK_EDITOR_INDEX = 2" in html and 'data-index="2"' in html
    assert "MASK_EDITOR_JOB" in html
    assert owner.get(f"/edit/{token}?index=9").status_code == 404


def test_hair_style_and_length_rerender_without_new_overrides(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    base = owner.get(f"/api/v1/jobs/{token}/editor?index=1").json()
    original = (_isolated / f"{token}_c1.png").read_bytes()
    style = "bun" if base["combo"]["hair_style"] != "bun" else "long_straight"
    length = "very_long" if base["combo"]["hair_length"] != "very_long" else "short"
    r = owner.post(f"/api/v1/jobs/{token}/attributes",
                   json={"attributes": {"hair_style": style, "hair_length": length}})
    assert r.status_code == 200, r.text
    assert r.json()["attributes"]["hair_style"] == style
    assert r.json()["attributes"]["hair_length"] == length
    editor = owner.get(f"/api/v1/jobs/{token}/editor?index=1").json()
    assert editor["combo"]["hair_style"] == style
    assert editor["combo"]["hair_length"] == length
    # Changing hair must not turn every seeded hair mask into a stored override.
    assert editor["override_names"] == base["override_names"]
    assert owner.post(f"/api/v1/jobs/{token}/render", json={"index": 1}).status_code == 200
    assert (_isolated / f"{token}_e1_c1.png").read_bytes() != original
    assert owner.post(f"/api/v1/jobs/{token}/attributes",
                      json={"attributes": {"hair_length": "floor"}}).status_code == 400
    reset = owner.post(f"/api/v1/jobs/{token}/attributes", json={"reset": True})
    assert reset.status_code == 200
    assert reset.json()["attributes"]["hair_style"] == base["combo"]["hair_style"]


def test_editor_payload_exposes_photo_values_and_attribute_overrides(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    base = owner.get(f"/api/v1/jobs/{token}/editor?index=1").json()
    assert "photo_combo" in base and "attribute_overrides" in base
    assert base["attribute_overrides"] == {}
    assert base["photo_combo"]["neckwear"] == base["combo"]["neckwear"]
    r = owner.post(f"/api/v1/jobs/{token}/attributes",
                   json={"attributes": {"neckwear": "tie", "beard": "full"}})
    assert r.status_code == 200, r.text
    assert r.json()["overrides"] == {"neckwear": "tie", "beard": "full"}
    edited = owner.get(f"/api/v1/jobs/{token}/editor?index=1").json()
    assert edited["combo"]["neckwear"] == "tie"
    assert edited["combo"]["beard"] == "full"
    # The photo comparison never changes when the user edits.
    assert edited["photo_combo"]["neckwear"] == base["photo_combo"]["neckwear"]
    assert edited["photo_combo"]["beard"] == base["photo_combo"]["beard"]
    assert edited["attribute_overrides"] == {"neckwear": "tie", "beard": "full"}
    assert owner.post(f"/api/v1/jobs/{token}/attributes",
                      json={"attributes": {"pattern": "check"}}).status_code == 400
    owner.post(f"/api/v1/jobs/{token}/attributes", json={"reset": True})
    reset = owner.get(f"/api/v1/jobs/{token}/editor?index=1").json()
    assert reset["attribute_overrides"] == {}
    assert reset["combo"]["neckwear"] == base["photo_combo"]["neckwear"]


def test_attributes_post_returns_preview_skin_and_hat_mask_in_one_round_trip(_isolated):
    owner = TestClient(A.app)
    token = _generate(owner).json()["data"]["job"]["id"]
    first = owner.post(f"/api/v1/jobs/{token}/attributes",
                       json={"attributes": {"top_garment": "tee"}, "index": 1})
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["skin"].startswith("data:image/png;base64,")
    assert first_body["hat_mask"] is None
    assert first_body["override_names"] == []

    second = owner.post(f"/api/v1/jobs/{token}/attributes",
                        json={"attributes": {"top_garment": "dress", "headwear": "cap"},
                              "hat_color": "#ff0000", "index": 1})
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["skin"].startswith("data:image/png;base64,")
    assert second_body["skin"] != first_body["skin"]
    assert "headwear.cap" in (second_body["hat_mask"] or {})
    assert "headwear.cap" in second_body["override_names"]
    assert owner.post(f"/api/v1/jobs/{token}/attributes",
                      json={"attributes": {"top_garment": "tee"}, "index": 9}).status_code == 404
