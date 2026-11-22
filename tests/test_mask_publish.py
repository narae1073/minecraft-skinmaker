"""Selective promotion of editor draft masks into the production asset."""
from __future__ import annotations

import hashlib
import json

import pytest

from skinmaker import mask_publish as MP


def _entry(bit=1):
    return {"L1": {"head.front": [[bit]]}, "L2": {}}


def _write(path, masks):
    path.write_text(json.dumps({"version": 1, "masks": masks}, ensure_ascii=False), encoding="utf-8")


def _setup(tmp_path):
    draft = tmp_path / "draft.json"
    asset = tmp_path / "assets" / "attribute_masks.json"
    approval = tmp_path / "assets" / "attribute_masks_approval.json"
    asset.parent.mkdir(parents=True)
    _write(draft, {
        "hood.up": _entry(1),
        "hood.down": _entry(0),
        "headwear.cap": _entry(1),
    })
    _write(asset, {
        "hood.up": _entry(1),
        "hood.down": _entry(1),
        "top_garment.tee": _entry(0),
    })
    return draft, asset, approval


def test_diff_masks_splits_added_changed_same_and_production_only(tmp_path):
    draft, asset, _approval = _setup(tmp_path)
    diff = MP.diff_masks(MP.load_masks_file(draft), MP.load_masks_file(asset))
    assert diff["added"] == ["headwear.cap"]
    assert diff["changed"] == ["hood.down"]
    assert diff["same"] == ["hood.up"]
    assert diff["production_only"] == ["top_garment.tee"]


def test_merge_only_selected_keys_and_backups_previous_asset(tmp_path):
    draft, asset, approval = _setup(tmp_path)
    before = asset.read_bytes()
    summary = MP.merge_masks(asset, approval, draft, ["headwear.cap"], backup_dir=tmp_path / "backup")
    assert summary["added"] == ["headwear.cap"]
    assert summary["changed"] == []
    assert summary["previous_entries"] == 3
    assert summary["entries"] == 4
    assert summary["backup"]
    assert (tmp_path / "backup").joinpath(summary["backup"].split("/")[-1]).read_bytes() == before
    merged = MP.load_masks_file(asset)
    assert set(merged) == {"hood.up", "hood.down", "top_garment.tee", "headwear.cap"}
    # Selecting one key does not drag the rest of the draft in: the production
    # hood.down stays as it was, not the draft's changed value.
    assert merged["hood.down"] == _entry(1)
    assert merged["top_garment.tee"]["L1"]["head.front"] == [[0]]


def test_approval_sha_matches_the_written_asset(tmp_path):
    draft, asset, approval = _setup(tmp_path)
    summary = MP.merge_masks(asset, approval, draft, ["hood.down"], backup_dir=tmp_path / "backup")
    record = json.loads(approval.read_text(encoding="utf-8"))
    assert record["approved"] is True
    assert record["approved_by"] == "editor"
    assert record["sha256"] == hashlib.sha256(asset.read_bytes()).hexdigest()
    assert summary["sha256"] == record["sha256"]
    assert summary["changed"] == ["hood.down"]
    assert MP.load_masks_file(asset)["hood.down"] == _entry(0)


def test_selection_errors_do_not_touch_the_asset(tmp_path):
    draft, asset, approval = _setup(tmp_path)
    before = asset.read_bytes()
    with pytest.raises(ValueError):
        MP.merge_masks(asset, approval, draft, [], backup_dir=tmp_path / "backup")
    with pytest.raises(ValueError):
        MP.merge_masks(asset, approval, draft, ["not.a.key"], backup_dir=tmp_path / "backup")
    with pytest.raises(ValueError):
        MP.merge_masks(asset, approval, draft, ["hood.up", "hood.up"], backup_dir=tmp_path / "backup")
    assert asset.read_bytes() == before
    assert not approval.exists()
