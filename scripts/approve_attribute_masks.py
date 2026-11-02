#!/usr/bin/env python3
"""Promote a mask-editor draft to the production asset with SHA approval.

The editor writes out/mask_editor/attribute_masks.json. This CLI validates it,
copies it to assets/attribute_masks.json, and writes the approval SHA/policy.
It requires an explicit --yes (human gate); it never approves automatically.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from skinmaker import attribute_masks as AM  # noqa: E402


def approve(draft: Path, asset: Path, approval: Path, approved_by: str = "user") -> dict:
    data = json.loads(Path(draft).read_text(encoding="utf-8"))
    masks = data.get("masks", data)
    payload = {
        "version": 1,
        "source": "mask_editor",
        "policy": AM.POLICY,
        "note": "Approved attribute-value shape masks (editor draft promoted).",
        "masks": masks,
    }
    errors = AM.validate_asset(payload)
    if errors:
        raise ValueError("invalid mask asset: " + "; ".join(errors[:8]))
    asset = Path(asset)
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    sha = hashlib.sha256(asset.read_bytes()).hexdigest()
    record = {
        "approved": True,
        "approved_by": approved_by,
        "approved_at": _dt.date.today().isoformat(),
        "policy": AM.POLICY,
        "sha256": sha,
        "artifact": str(asset.relative_to(ROOT)) if asset.is_relative_to(ROOT) else str(asset),
    }
    approval = Path(approval)
    approval.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"sha256": sha, "artifact": str(asset), "approval": str(approval), "entries": len(masks)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", default=str(ROOT / "out" / "mask_editor" / "attribute_masks.json"))
    parser.add_argument("--asset", default=str(AM.ASSET_PATH))
    parser.add_argument("--approval", default=str(AM.APPROVAL_PATH))
    parser.add_argument("--approved-by", default="user")
    parser.add_argument("--yes", action="store_true", help="confirm promotion; required")
    args = parser.parse_args(argv)
    if not args.yes:
        print("refusing: pass --yes to promote the draft into the production asset", file=sys.stderr)
        return 2
    try:
        result = approve(Path(args.draft), Path(args.asset), Path(args.approval), args.approved_by)
    except (OSError, ValueError) as exc:
        print(f"approval failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
