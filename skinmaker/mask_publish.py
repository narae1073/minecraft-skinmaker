"""Selectively promote mask-editor draft entries into the production asset.

The standalone editor writes a full draft (every maskable value is seeded).
Promoting the whole draft would add dozens of keys to the production asset at
once, so this module merges only the keys the reviewer selected, backups the
previous asset, and writes the matching approval record.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import shutil
from pathlib import Path

from . import attribute_masks as AM

ROOT = Path(__file__).resolve().parent.parent


def load_masks_file(path: str | Path) -> dict:
    """Read a mask asset/draft and return its ``masks`` mapping."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    masks = data.get("masks", data) if isinstance(data, dict) else None
    if not isinstance(masks, dict):
        raise ValueError("masks must be an object")
    return masks


def diff_masks(draft: dict, production: dict) -> dict[str, list[str]]:
    """Key-level diff between a draft and the current production asset."""
    draft_keys = set(draft)
    prod_keys = set(production)
    common = draft_keys & prod_keys
    return {
        "added": sorted(draft_keys - prod_keys),
        "changed": sorted(k for k in common if draft[k] != production[k]),
        "same": sorted(k for k in common if draft[k] == production[k]),
        "production_only": sorted(prod_keys - draft_keys),
    }


def merge_masks(asset_path: str | Path, approval_path: str | Path,
                draft_path: str | Path, keys: list[str], *,
                backup_dir: str | Path, approved_by: str = "editor") -> dict:
    """Merge ``keys`` from the draft into the production asset.

    Returns a summary with the previous/next key counts, the backup path and the
    approval SHA. Raises ``ValueError`` for an invalid selection or asset.
    """
    if not isinstance(keys, list) or not keys:
        raise ValueError("select at least one mask key")
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate mask key")
    asset_path = Path(asset_path)
    approval_path = Path(approval_path)
    draft = load_masks_file(draft_path)
    missing = [key for key in keys if key not in draft]
    if missing:
        raise ValueError("not in the draft: " + ", ".join(sorted(missing)[:5]))
    previous = {}
    if asset_path.is_file():
        previous = load_masks_file(asset_path)

    merged = dict(previous)
    for key in keys:
        merged[key] = draft[key]
    payload = {
        "version": 1,
        "source": "mask_editor",
        "policy": AM.POLICY,
        "note": "Approved attribute-value shape masks (selected editor keys).",
        "masks": merged,
    }
    errors = AM.validate_asset(payload)
    if errors:
        raise ValueError("invalid mask asset: " + "; ".join(errors[:8]))

    backup_path = None
    if asset_path.is_file():
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = backup_dir / f"attribute_masks.{stamp}.json"
        shutil.copy2(asset_path, backup_path)

    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    sha = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    artifact = str(asset_path.relative_to(ROOT)) if asset_path.is_relative_to(ROOT) else str(asset_path)
    record = {
        "approved": True,
        "approved_by": approved_by,
        "approved_at": datetime.date.today().isoformat(),
        "policy": AM.POLICY,
        "sha256": sha,
        "artifact": artifact,
    }
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    approval_path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    diff = diff_masks(draft, previous)
    return {
        "sha256": sha,
        "keys": sorted(keys),
        "added": [k for k in diff["added"] if k in keys],
        "changed": [k for k in diff["changed"] if k in keys],
        "previous_entries": len(previous),
        "entries": len(merged),
        "backup": str(backup_path) if backup_path else None,
        "artifact": artifact,
        "approval": str(approval_path),
    }
