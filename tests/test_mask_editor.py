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
