"""General attribute-mask schema, migration and gate-facing helpers."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker import attribute_masks as AM
from skinmaker import hood_masks as HM


def test_asset_is_valid_and_has_migrated_hood():
    data = AM.load_asset()
    assert AM.validate_asset(data) == []
    masks = AM.load_masks()
    for kind in ("up", "down"):
        assert f"hood.{kind}" in masks
        grid = AM.get_mask(masks, "hood", kind, "L1", "head", "front")
        assert len(grid) == 8 and all(len(row) == 8 for row in grid)


def test_legacy_hood_asset_converts_to_general_keys():
    masks = AM.load_masks(Path("assets/hood_masks.json"))
    assert set(masks) == {"hood.up", "hood.down"}
    assert AM.legacy_hood_masks(masks).keys() == {"up", "down"}


def test_hood_loader_reads_the_general_asset():
    loaded = HM.load_hood_masks()
    assert loaded is not None
    assert set(loaded) <= {"up", "down"}
    assert "L1" in loaded["up"] and "head.front" in loaded["up"]["L1"]


def test_validate_rejects_unknown_key_layer_and_grid():
    assert AM.validate_asset({"masks": {"bogus": {}}}) == ["invalid key: 'bogus'"]
    assert AM.validate_asset({"masks": {"hood.up": {"L9": {}}}}) == ["hood.up: invalid layer 'L9'"]
    assert AM.validate_asset({"masks": {"hood.up": {"L1": {"head.front": [[2]]}}}})
    assert AM.validate_asset({"masks": {"hood.up": {"L1": {"head.front": []}}}})
