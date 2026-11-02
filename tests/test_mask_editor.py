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
    assert set(j["maskable"]) == {"hood", "headwear", "hood_fit", "hair_style", "hair_length", "beard"}
    assert "hood.up" in j["masks"] and "headwear.cap" in j["masks"]


def test_preview_final_and_mask_modes():
    c = TestClient(mod.app)
    masks = c.get("/api/defaults").json()["masks"]
    for mode in ("final", "mask"):
        r = c.post("/api/preview", json={"key": "hood", "value": "up", "masks": masks, "mode": mode})
        assert r.status_code == 200, r.text
        assert r.json()["skin"].startswith("/out/")
