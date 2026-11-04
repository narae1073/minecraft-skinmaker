"""General mask-editor API: defaults, final/mask preview, save."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("mask_editor_app", ROOT / "tools" / "mask_editor" / "app.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


import pytest


@pytest.fixture(autouse=True)
def _isolated_out(tmp_path, monkeypatch):
    # Never read or write the user's real draft (out/mask_editor) from tests.
    monkeypatch.setattr(mod, "OUT", tmp_path)
    # Each test starts without an uploaded photo.
    monkeypatch.setitem(mod._PHOTO, "observed", None)
    monkeypatch.setitem(mod._PHOTO, "name", None)
    monkeypatch.setitem(mod._PHOTO, "info", None)
    monkeypatch.setitem(mod._PHOTO, "attrs", None)
    # No network in tests: the photo classification returns the fixture attributes.
    from skinmaker import production_qa as Q
    fixture = _fake_classification(Q._attrs("long", "long_straight", "none").values)
    monkeypatch.setattr(mod, "_classify_photo", lambda photo: (fixture, "test"))


def test_defaults_expose_key_value_tree_and_general_masks():
    c = TestClient(mod.app)
    r = c.get("/api/defaults")
    assert r.status_code == 200
    j = r.json()
    assert set(j["maskable"]) == {"hood", "headwear", "hood_fit", "hair_style", "hair_length", "beard", "sleeve_len", "bottom_garment", "closure_type", "collar_type", "pocket_type", "neckwear", "inner_top", "top_garment"}
    assert "hood.up" in j["masks"] and "headwear.cap" in j["masks"]
    hair_cells = sum(sum(row) for grid in j["masks"]["hair_style.bob"]["L1"].values() for row in grid)
    assert hair_cells > 0
    body_hair_l1 = sum(sum(row) for face, grid in j["masks"]["hair_style.long_wavy"]["L1"].items()
                       if face.startswith("body.") for row in grid)
    body_hair_l2 = sum(sum(row) for face, grid in j["masks"]["hair_style.long_wavy"]["L2"].items()
                       if face.startswith("body.") for row in grid)
    head_hair_l2 = sum(sum(row) for face, grid in j["masks"]["hair_style.long_wavy"]["L2"].items()
                       if face.startswith("head.") for row in grid)
    assert body_hair_l1 > 0 and body_hair_l2 > 0
    assert head_hair_l2 > 0
    # Saved drafts from the old seed can carry long body drape on short/medium;
    # the defaults migration must replace body faces with the length-matched seed.
    def body_l1(name):
        return sum(sum(row) for face, grid in j["masks"][name]["L1"].items()
                   if face.startswith("body.") for row in grid)
    assert body_l1("hair_length.short") == 0
    assert body_l1("hair_length.medium") == 0
    assert body_l1("hair_length.long") > 0
    assert body_l1("hair_length.very_long") > 0
    assert sum(sum(row) for grid in j["masks"]["beard.full"]["L1"].values() for row in grid) == 0
    inner_cells = sum(sum(row) for grid in j["masks"]["inner_top.shirt"]["L1"].values() for row in grid)
    assert inner_cells > 0
    top_cells = sum(sum(row) for grid in j["masks"]["top_garment.tee"]["L1"].values() for row in grid)
    assert top_cells > 0


def test_preview_final_and_mask_modes():
    c = TestClient(mod.app)
    masks = c.get("/api/defaults").json()["masks"]
    for mode in ("final", "mask"):
        r = c.post("/api/preview", json={"key": "hood", "value": "up", "masks": masks, "mode": mode})
        assert r.status_code == 200, r.text
        assert r.json()["skin"].startswith("/out/")


def test_hair_length_preview_uses_matching_style():
    # The old preview always used hair_style=long_straight, so short length
    # looked like long hair. Match the style to the length instead.
    assert mod._attrs_for("hair_length", "short").get("hair_style") == "short"
    assert mod._attrs_for("hair_length", "medium").get("hair_style") == "bob"
    assert mod._attrs_for("hair_length", "long").get("hair_style") == "long_straight"
    short = mod._seed_hair("hair_length", "short")
    very = mod._seed_hair("hair_length", "very_long")

    def count(seed, prefix):
        return sum(sum(row) for face, grid in seed["L1"].items() if face.startswith(prefix) for row in grid)

    assert count(short, "body.") == 0
    assert count(very, "body.") > 0
    assert count(short, "head.") < count(very, "head.")


def test_seed_endpoint_returns_current_seed():
    c = TestClient(mod.app)
    r = c.get("/api/seed", params={"key": "hair_style", "value": "long_wavy"})
    assert r.status_code == 200, r.text
    grid = r.json()["mask"]["L1"]
    head = sum(sum(row) for face, g in grid.items() if face.startswith("head.") for row in g)
    body = sum(sum(row) for face, g in grid.items() if face.startswith("body.") for row in g)
    assert head > 0 and body > 0


def test_hair_style_preview_uses_very_long_base_for_full_style():
    assert mod._attrs_for("hair_style", "long_wavy").get("hair_length") == "very_long"
    assert mod._attrs_for("hair_length", "short").get("hair_style") == "short"


def test_defaults_exposes_16_key_combo_schema():
    c = TestClient(mod.app)
    j = c.get("/api/defaults").json()
    assert len(j["enums"]) == 16
    assert "pattern" in j["enums"] and "symmetry" in j["enums"]
    assert len(j["defaults"]) == 16
    assert j["models"] == ["classic", "slim"]
    assert set(j["combo"]) == set(j["enums"])
    assert "pattern" not in j["maskable"] and "symmetry" not in j["maskable"]


def test_preview_full_16_key_combo_and_slim():
    c = TestClient(mod.app)
    j = c.get("/api/defaults").json()
    combo = dict(j["combo"])
    combo.update({"top_garment": "shirt", "bottom_garment": "shorts", "pattern": "vertical_stripe",
                  "sleeve_len": "long", "hair_style": "long_wavy", "hair_length": "long",
                  "hood": "down", "closure_type": "buttons", "collar_type": "shirt"})
    r = c.post("/api/preview", json={"combo": combo, "model": "slim", "masks": j["masks"],
                                     "mode": "final", "key": "hair_style", "value": "long_wavy"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model"] == "slim"
    assert body["skin"].startswith("/out/")
    assert body["effective"]["hair_style"] == "long_wavy"
    assert body["effective"]["pattern"] == "vertical_stripe"


def test_preview_combo_cross_rule_is_reported():
    c = TestClient(mod.app)
    j = c.get("/api/defaults").json()
    combo = dict(j["combo"])
    combo.update({"top_garment": "none", "sleeve_len": "long", "pattern": "floral"})
    r = c.post("/api/preview", json={"combo": combo, "masks": j["masks"], "mode": "final",
                                     "key": "hood", "value": "up"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["effective"]["top_garment"] == "none"
    assert body["effective"]["sleeve_len"] == "none"
    assert body["effective"]["pattern"] == "plain"
    assert any("sleeve_len" in w for w in body["warnings"])


def test_preview_rejects_bad_combo_and_model():
    c = TestClient(mod.app)
    j = c.get("/api/defaults").json()
    combo = dict(j["combo"])
    combo["top_garment"] = "bogus"
    r = c.post("/api/preview", json={"combo": combo, "masks": j["masks"], "mode": "final"})
    assert r.status_code == 400
    r = c.post("/api/preview", json={"combo": j["combo"], "model": "bogus", "masks": j["masks"]})
    assert r.status_code == 400


def test_defaults_migrates_top_body_and_hair_back():
    c = TestClient(mod.app)
    j = c.get("/api/defaults").json()
    hoodie = j["masks"]["top_garment.hoodie"]["L1"]
    assert sum(sum(row) for face, grid in hoodie.items() if face == "body.back" for row in grid) == 96
    assert sum(sum(row) for face, grid in hoodie.items() if face.startswith("body.") for row in grid) >= 352
    for name in ("hair_style.long_wavy", "hair_length.long", "hair_style.short"):
        for layer in ("L1", "L2"):
            assert sum(sum(row) for face, grid in j["masks"][name][layer].items()
                       if face == "body.back" for row in grid) == 0


def _saved_doc(tmp_path, monkeypatch, doc):
    monkeypatch.setattr(mod, "OUT", tmp_path)
    (tmp_path / "attribute_masks.json").write_text(__import__("json").dumps(doc), encoding="utf-8")


def _cells(grid_by_face, prefix):
    return sum(sum(row) for face, grid in grid_by_face.items() if face.startswith(prefix) for row in grid)


def test_saved_draft_user_body_edits_survive_reload(tmp_path, monkeypatch):
    # Regression: a saved, schema-2 draft with the user's cleared top body.back
    # must not be refilled on every /api/defaults read.
    hoodie = mod._seed_top("hoodie")
    layers = {layer: dict(hoodie.get(layer, {})) for layer in ("L1", "L2")}
    layers["L1"]["body.back"] = [[0] * 8 for _ in range(12)]
    saved = {"version": 1, "schema": mod.SCHEMA, "masks": {"top_garment.hoodie": mod._normalize_key(layers)}}
    _saved_doc(tmp_path, monkeypatch, saved)
    j = mod._defaults()["top_garment.hoodie"]["L1"]
    assert _cells(j, "body.back") == 0


def test_saved_hair_length_user_body_edits_survive_reload(tmp_path, monkeypatch):
    seed = mod._seed_hair("hair_length", "long")
    layers = {layer: dict(seed.get(layer, {})) for layer in ("L1", "L2")}
    layers["L1"]["body.front"] = [[0] * 4 for _ in range(12)]
    saved = {"version": 1, "schema": mod.SCHEMA, "masks": {"hair_length.long": mod._normalize_key(layers)}}
    _saved_doc(tmp_path, monkeypatch, saved)
    j = mod._defaults()["hair_length.long"]["L1"]
    assert _cells(j, "body.front") == 0


def test_legacy_draft_without_schema_is_still_migrated(tmp_path, monkeypatch):
    # Drafts written before the schema marker still get the one-off refill.
    hoodie = mod._seed_top("hoodie")
    layers = {layer: dict(hoodie.get(layer, {})) for layer in ("L1", "L2")}
    layers["L1"]["body.back"] = [[0] * 8 for _ in range(12)]
    _saved_doc(tmp_path, monkeypatch, {"version": 1, "masks": {"top_garment.hoodie": mod._normalize_key(layers)}})
    j = mod._defaults()["top_garment.hoodie"]["L1"]
    assert _cells(j, "body.back") == 96


def test_hood_policy_still_zeroes_body_back_hair_in_saved_draft(tmp_path, monkeypatch):
    seed = mod._seed_hair("hair_style", "long_wavy")
    layers = {layer: dict(seed.get(layer, {})) for layer in ("L1", "L2")}
    layers["L1"]["body.back"] = [[1] * 8 for _ in range(12)]
    saved = {"version": 1, "schema": mod.SCHEMA, "masks": {"hair_style.long_wavy": mod._normalize_key(layers)}}
    _saved_doc(tmp_path, monkeypatch, saved)
    j = mod._defaults()["hair_style.long_wavy"]
    for layer in ("L1", "L2"):
        assert _cells(j[layer], "body.back") == 0


def test_save_writes_schema_marker(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(mod, "OUT", tmp_path)
    c = TestClient(mod.app)
    r = c.post("/api/save", json={"masks": {}})
    assert r.status_code == 200, r.text
    assert json.loads((tmp_path / "attribute_masks.json").read_text(encoding="utf-8"))["schema"] == mod.SCHEMA


def test_viewer_moves_l2_arms_with_l1_for_slim():
    # Regression: setModel moved the L1 arms for slim but left the L2 arm
    # overlays at the classic x, so they were not concentric.
    src = (ROOT / "tools" / "mask_editor" / "viewer.js").read_text(encoding="utf-8")
    body = src[src.index("function setModel("):src.index("function pick(")]
    assert "meshes.arm2.position.x" in body
    assert "meshes.larm2.position.x" in body


def test_defaults_publish_atlas_rects_for_both_layers():
    # The 2D editor draws boxes from these rects: one per face per layer, all
    # inside the 64x64 atlas, and L1/L2 must not overlap each other.
    j = TestClient(mod.app).get("/api/defaults").json()
    atlas = j["atlas"]
    assert atlas["size"] == 64
    for layer in ("L1", "L2"):
        assert set(atlas["rects"][layer]) == set(j["faces"])
        for face, (x, y, w, h) in atlas["rects"][layer].items():
            assert 0 <= x and 0 <= y and x + w <= 64 and y + h <= 64, (layer, face)
            assert [w, h] == j["dims"][face], (layer, face)
    taken = {}
    for layer in ("L1", "L2"):
        for face, (x, y, w, h) in atlas["rects"][layer].items():
            for py in range(y, y + h):
                for px in range(x, x + w):
                    assert (px, py) not in taken, f"{layer}.{face} overlaps {taken.get((px, py))}"
                    taken[(px, py)] = f"{layer}.{face}"


def test_seed_all_returns_procedural_seed_for_every_value():
    # Reset target: every maskable value, from the algorithm only (no draft,
    # no approved asset). Hood policy still hides body-back hair.
    c = TestClient(mod.app)
    r = c.get("/api/seed-all")
    assert r.status_code == 200, r.text
    masks = r.json()["masks"]
    assert set(masks) == {f"{k}.{v}" for k, vs in mod.MASKABLE.items() for v in vs}
    assert sum(sum(row) for grid in masks["hair_style.bob"]["L1"].values() for row in grid) > 0
    for layer in ("L1", "L2"):
        assert sum(sum(row) for face, grid in masks["hair_style.long_wavy"][layer].items()
                   if face.startswith("body.back") for row in grid) == 0


def test_preview_returns_final_base_always_and_mask_only_in_mask_mode():
    c = TestClient(mod.app)
    masks = c.get("/api/defaults").json()["masks"]
    final = c.post("/api/preview", json={"key": "hood", "value": "up", "masks": masks, "mode": "final"}).json()
    assert final["skin"].startswith("/out/") and final.get("mask") is None
    mask = c.post("/api/preview", json={"key": "hood", "value": "up", "masks": masks, "mode": "mask"}).json()
    assert mask["mask"].startswith("/out/") and mask["mask"] != mask["skin"]
    assert mask["skin"].startswith("/out/")


def _head_l1(masks, combo):
    from skinmaker import production_qa as Q
    from skinmaker import render as R
    attrs = mod._combo_attrs(dict(mod.DEFAULT_COMBO, **combo))
    canvas = R.render(Q._observed(), attrs, (), mask_override=masks, model="classic")
    out = {}
    for face in ("front", "back", "right", "left", "top"):
        f = mod.LAYOUT.face("head", face, 0)
        out[face] = [tuple(canvas.image.getpixel((x, y)))
                     for y in range(f.y, f.y + f.h) for x in range(f.x, f.x + f.w)]
    return out


def test_seeded_head_hair_matches_procedural_render():
    # Regression (2026-11-04): hair masks were seeded from the rule stencil
    # while the renderer uses the reference silhouette, so intersecting the
    # style and length seeds cut the side hair. A seeded render must match the
    # procedural one on the head.
    seed = mod._seed_masks()
    for combo in ({"hair_style": "short", "hair_length": "short", "hood": "none"},
                  {"hair_style": "bob", "hair_length": "medium", "hood": "none"},
                  {"hair_style": "long_straight", "hair_length": "long", "hood": "none"}):
        proc = _head_l1({}, combo)
        seeded = _head_l1(seed, combo)
        diff = sum(1 for face in proc for a, b in zip(proc[face], seeded[face]) if a != b)
        assert diff == 0, (combo, diff)


def test_reset_and_per_value_seed_keep_top_body_clothed():
    # Regression (2026-11-04): /api/seed-all and /api/seed skipped the top-body
    # refill that the saved-draft defaults apply, so the back of the torso
    # rendered as bare skin after Reset.
    c = TestClient(mod.app)
    for masks in (c.get("/api/seed-all").json()["masks"],
                  {"top_garment.hoodie": c.get("/api/seed", params={"key": "top_garment", "value": "hoodie"}).json()["mask"]}):
        grid = masks["top_garment.hoodie"]
        for layer in ("L1",):
            back = grid[layer]["body.back"]
            assert all(all(row) for row in back), "body.back must be fully clothed"


def test_combo_warns_on_contradictory_hair_style_and_length():
    # Advisory only (editor): contradictory hair pairs cut the hair masks.
    bad = mod._combo_attrs(dict(mod.DEFAULT_COMBO, hair_style="short", hair_length="long"))
    assert any("hair" in w for w in mod._combo_warnings({"hair_style": "short", "hair_length": "long"}, bad))
    bad2 = mod._combo_attrs(dict(mod.DEFAULT_COMBO, hair_style="long_wavy", hair_length="short"))
    assert any("hair" in w for w in mod._combo_warnings({"hair_style": "long_wavy", "hair_length": "short"}, bad2))
    ok = mod._combo_attrs(dict(mod.DEFAULT_COMBO, hair_style="short", hair_length="short"))
    assert not any("hair" in w for w in mod._combo_warnings({"hair_style": "short", "hair_length": "short"}, ok))


def test_viewer_exposes_dispose_that_releases_listeners_and_loop():
    # Regression: the viewer added window/ResizeObserver listeners and an rAF
    # loop that were never removed, so re-created viewers piled up.
    src = (ROOT / "tools" / "mask_editor" / "viewer.js").read_text(encoding="utf-8")
    assert "function dispose()" in src
    body = src[src.index("function dispose()"):src.index("return {", src.index("function dispose()"))]
    assert "cancelAnimationFrame" in body
    assert "removeEventListener('resize'" in body
    assert "disconnect()" in body
    assert "renderer.dispose()" in body
    assert "dispose, " in src or "dispose }" in src or "dispose," in src


def test_preview_production_source_uses_approved_asset_not_draft():
    # source=production renders with the approved asset (what generation uses),
    # ignoring the draft masks in the request.
    c = TestClient(mod.app)
    masks = c.get("/api/seed-all").json()["masks"]
    draft = c.post("/api/preview", json={"key": "hood", "value": "up", "masks": masks, "mode": "final",
                                         "source": "draft"}).json()
    draft_bytes = (mod.OUT / "preview.png").read_bytes()
    prod = c.post("/api/preview", json={"key": "hood", "value": "up", "masks": masks, "mode": "final",
                                        "source": "production"}).json()
    prod_bytes = (mod.OUT / "preview.png").read_bytes()
    assert draft["source"] == "draft" and prod["source"] == "production"
    # Seed-all carries hair/top masks the approved asset does not have.
    assert draft_bytes != prod_bytes
    bad = c.post("/api/preview", json={"key": "hood", "value": "up", "masks": masks, "source": "x"})
    assert bad.status_code == 400


def test_legacy_draft_hair_is_migrated_once_with_backup(tmp_path, monkeypatch):
    # The pre-fix draft (schema < 3) carries rule-stencil hair masks. The first
    # load re-seeds the hair keys once, keeps a backup, and marks the draft v3.
    import json
    monkeypatch.setattr(mod, "OUT", tmp_path)
    narrow = mod._normalize_key({"L1": {"head.right": [[1, 0, 0, 0, 0, 0, 0, 0]] * 8}, "L2": {}})
    other = mod._seed_for("hood", "up")
    doc = {"version": 1, "schema": 2, "masks": {"hair_length.short": narrow,
                                                "hood.up": mod._normalize_key(other)}}
    path = tmp_path / "attribute_masks.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    masks = mod._defaults()
    backups = list(tmp_path.glob("attribute_masks.pre-v3-*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8"))["schema"] == 2
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["schema"] == mod.SCHEMA
    assert saved["masks"]["hair_length.short"] == mod._seed_masks()["hair_length.short"]
    assert saved["masks"]["hood.up"] == doc["masks"]["hood.up"]
    # Second load: already v3, no new backup, no rewrite.
    before = path.read_text(encoding="utf-8")
    mod._defaults()
    assert path.read_text(encoding="utf-8") == before
    assert len(list(tmp_path.glob("attribute_masks.pre-v3-*.json"))) == 1
    assert masks["hair_length.short"]["L1"]["head.right"] == mod._seed_masks()["hair_length.short"]["L1"]["head.right"]


def test_slim_override_applies_only_to_slim_renders():
    # Slim arm faces are narrower (front/back/top/bottom are 3 px, not 4). An
    # entry may carry a "slim" sub-dict with grids for those faces. Only slim
    # renders use them; classic renders and existing assets are unchanged.
    from skinmaker import attribute_masks as AM
    grid3 = [[1, 1, 1] for _ in range(12)]
    masks = {"sleeve_len.long": {"L1": {}, "L2": {}, "slim": {"L1": {"r_arm.front": grid3}, "L2": {}}}}
    slim = AM.resolve_model(masks, "slim")
    classic = AM.resolve_model(masks, "classic")
    assert slim["sleeve_len.long"]["L1"]["r_arm.front"] == grid3
    assert "r_arm.front" not in classic["sleeve_len.long"]["L1"]
    assert "slim" not in classic["sleeve_len.long"]
    assert AM.resolve_model({"x.y": {"L1": {}, "L2": {}}}, "slim") == {"x.y": {"L1": {}, "L2": {}}}


def test_slim_override_changes_slim_render_not_classic():
    from skinmaker import production_qa as Q
    from skinmaker import render as R
    obs = Q._observed()
    attrs = mod._combo_attrs(dict(mod.DEFAULT_COMBO, sleeve_len="long", top_garment="tee", hood="none"))
    cleared = {"sleeve_len.long": {"L1": {}, "L2": {}, "slim": {"L1": {
        "r_arm.front": [[0, 0, 0] for _ in range(12)],
        "l_arm.front": [[0, 0, 0] for _ in range(12)]}, "L2": {}}}}
    none = {}
    slim_a = R.render(obs, attrs, (), mask_override=cleared, model="slim")
    slim_b = R.render(obs, attrs, (), mask_override=none, model="slim")
    assert slim_a.image.tobytes() != slim_b.image.tobytes()
    cls_a = R.render(obs, attrs, (), mask_override=cleared, model="classic")
    cls_b = R.render(obs, attrs, (), mask_override=none, model="classic")
    assert cls_a.image.tobytes() == cls_b.image.tobytes()


def test_defaults_publish_slim_atlas_and_sub_faces():
    j = TestClient(mod.app).get("/api/defaults").json()
    assert set(j["slim"]["sub_faces"]) == {f"{p}.{f}" for p in ("r_arm", "l_arm") for f in ("front", "back", "top", "bottom")}
    rects = j["slim"]["atlas"]["rects"]
    assert rects["L1"]["r_arm.front"][2] == 3 and rects["L1"]["r_arm.right"][2] == 4
    assert j["atlas"]["rects"]["L1"]["r_arm.front"][2] == 4


def test_slim_override_survives_normalize_and_save_load(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "OUT", tmp_path)
    grid3 = [[1, 0, 1] for _ in range(12)]
    key = mod._normalize_key({"L1": {}, "L2": {}, "slim": {"L1": {"r_arm.front": grid3}}})
    assert key["slim"]["L1"]["r_arm.front"] == grid3
    assert "slim" not in mod._normalize_key({"L1": {}, "L2": {}})


PHOTO_PATH = ROOT / "tests" / "fixtures" / "messi5.jpg"


def test_photo_upload_drives_observed_and_can_be_cleared():
    c = TestClient(mod.app)
    fixture = mod._observed().skin.hex
    with open(PHOTO_PATH, "rb") as fh:
        r = c.post("/api/photo", files={"file": ("messi5.jpg", fh.read(), "image/jpeg")})
    assert r.status_code == 200, r.text
    info = r.json()
    assert info["name"] == "messi5.jpg" and info["skin"].startswith("#")
    assert c.get("/api/photo").json()["name"] == "messi5.jpg"
    assert mod._observed().skin.hex == info["skin"] != fixture
    assert c.delete("/api/photo").status_code == 200
    assert c.get("/api/photo").json() is None
    assert mod._observed().skin.hex == fixture


def test_photo_changes_the_seed_for_hair():
    c = TestClient(mod.app)
    before = c.get("/api/seed", params={"key": "hair_style", "value": "short"}).json()["mask"]
    with open(PHOTO_PATH, "rb") as fh:
        assert c.post("/api/photo", files={"file": ("messi5.jpg", fh.read(), "image/jpeg")}).status_code == 200
    after = c.get("/api/seed", params={"key": "hair_style", "value": "short"}).json()["mask"]
    c.delete("/api/photo")
    assert before != after


def test_photo_without_a_face_is_rejected():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (128, 128, 128)).save(buf, format="PNG")
    r = TestClient(mod.app).post("/api/photo", files={"file": ("blank.png", buf.getvalue(), "image/png")})
    assert r.status_code == 422, r.text


def _fake_classification(attrs_values, ok=True, error_kind=None, error=None):
    from types import SimpleNamespace
    from skinmaker import attributes as A
    attrs = A.validate(dict(attrs_values, hair_bbox=[200, 50, 800, 600]))
    return SimpleNamespace(ok=ok, attributes=attrs, error=error, error_kind=error_kind,
                           hair_bbox_px=None, uncertain=())


def test_photo_classification_drives_the_seed_base(monkeypatch):
    # Garment and hair attributes for the seeds come from the photo's VLM
    # classification, not from the fixed fixture.
    from skinmaker import production_qa as Q
    jacket = dict(Q._attrs("short", "short", "none").values, top_garment="jacket", bottom_garment="shorts")
    monkeypatch.setattr(mod, "_classify_photo", lambda photo: (_fake_classification(jacket), "fake"))
    c = TestClient(mod.app)
    with open(PHOTO_PATH, "rb") as fh:
        r = c.post("/api/photo", files={"file": ("messi5.jpg", fh.read(), "image/jpeg")})
    assert r.status_code == 200, r.text
    assert r.json()["attributes_source"] == "fake"
    assert r.json()["attributes"]["top_garment"] == "jacket"
    base = mod._seed_base()
    assert base["top_garment"] == "jacket" and base["bottom_garment"] == "shorts"
    assert base["hood"] == "none"
    assert base["hair_length"] == "short"
    assert tuple(base["hair_bbox"]) == (200, 50, 800, 600)
    assert c.delete("/api/photo").status_code == 200
    assert mod._seed_base()["top_garment"] == "hoodie"  # fixture again


def test_failed_photo_classification_is_reported_and_not_stored(monkeypatch):
    from skinmaker import production_qa as Q
    monkeypatch.setattr(mod, "_classify_photo",
                        lambda photo: (_fake_classification(Q._attrs("long", "long_straight", "none").values,
                                                            ok=False, error_kind="transport",
                                                            error="no key"), "gemini"))
    c = TestClient(mod.app)
    with open(PHOTO_PATH, "rb") as fh:
        r = c.post("/api/photo", files={"file": ("messi5.jpg", fh.read(), "image/jpeg")})
    assert r.status_code == 503, r.text
    assert c.get("/api/photo").json() is None


def test_photo_is_not_persisted_under_the_served_out_directory(tmp_path, monkeypatch):
    # /out is a static mount: an uploaded photo kept there would be downloadable
    # by anyone who can reach the editor. Only derived data may remain.
    with open(PHOTO_PATH, "rb") as fh:
        r = TestClient(mod.app).post("/api/photo", files={"file": ("messi5.jpg", fh.read(), "image/jpeg")})
    assert r.status_code == 200, r.text
    assert not [p for p in tmp_path.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]


def test_editor_token_gates_api_and_rendered_output_when_configured(monkeypatch):
    # The shared editor is reachable from the whole tailnet. With a token
    # configured, the API and the rendered /out files need it; the page and
    # static assets stay open (they hold no data).
    monkeypatch.setenv("SKINMAKER_EDITOR_TOKEN", "s3cret-token")
    c = TestClient(mod.app)
    assert c.get("/").status_code == 200
    assert c.get("/api/defaults").status_code == 401
    assert c.get("/api/photo").status_code == 401
    assert c.get("/out/preview.png").status_code in (401,)
    assert c.post("/api/auth", json={"token": "wrong"}).status_code == 401
    ok = c.post("/api/auth", json={"token": "s3cret-token"})
    assert ok.status_code == 200
    assert "editor_token" in ok.headers.get("set-cookie", "")
    assert c.get("/api/defaults").status_code == 200  # cookie kept by TestClient
    fresh = TestClient(mod.app)
    assert fresh.get("/api/defaults", headers={"X-Editor-Token": "s3cret-token"}).status_code == 200
    assert fresh.get("/api/defaults", headers={"X-Editor-Token": "nope"}).status_code == 401


def test_no_token_configured_means_no_gate(monkeypatch):
    monkeypatch.delenv("SKINMAKER_EDITOR_TOKEN", raising=False)
    assert TestClient(mod.app).get("/api/defaults").status_code == 200
