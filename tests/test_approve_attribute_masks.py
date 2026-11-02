"""Approval CLI: validate editor draft, promote asset, write SHA approval."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.approve_attribute_masks import approve


def _draft(tmp_path: Path) -> Path:
    grid = [[1] * 8 for _ in range(8)]
    p = tmp_path / "draft.json"
    p.write_text(json.dumps({"masks": {
        "hood.up": {"L1": {"head.front": grid}, "L2": {}},
    }}), encoding="utf-8")
    return p


def test_approve_writes_asset_and_sha(tmp_path):
    draft = _draft(tmp_path)
    asset = tmp_path / "attribute_masks.json"
    approval = tmp_path / "attribute_masks_approval.json"
    out = approve(draft, asset, approval, approved_by="tester")
    sha = hashlib.sha256(asset.read_bytes()).hexdigest()
    assert out["sha256"] == sha
    record = json.loads(approval.read_text())
    assert record["approved"] is True
    assert record["approved_by"] == "tester"
    assert record["sha256"] == sha
    assert "hood.up" in json.loads(asset.read_text())["masks"]


def test_approve_rejects_invalid_draft(tmp_path):
    draft = tmp_path / "bad.json"
    draft.write_text('{"masks": {"bogus": {}}}', encoding="utf-8")
    try:
        approve(draft, tmp_path / "a.json", tmp_path / "ap.json")
    except ValueError as exc:
        assert "invalid key" in str(exc)
    else:
        raise AssertionError("invalid draft was promoted")
