#!/usr/bin/env python3
"""Build assets/reference_pack.json from out/reference_skins.

Usage:
  .venv/bin/python scripts/build_reference_pack.py --refs out/reference_skins
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skinmaker.reference_pack import build_pack, save_pack


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refs", type=Path, default=Path("out/reference_skins"))
    ap.add_argument("--out", type=Path, default=Path("assets/reference_pack.json"))
    ap.add_argument("--hair", type=int, default=6)
    ap.add_argument("--eyes", type=int, default=6)
    ap.add_argument("--hood-up", type=int, default=4)
    ap.add_argument("--hood-down", type=int, default=2)
    ap.add_argument("--split", type=Path, default=None,
                    help="production split.json; builds from its train list only")
    args = ap.parse_args()
    include = None
    training = None
    if args.split:
        import json
        split = json.loads(args.split.read_text(encoding="utf-8"))
        include = set(split["train"])
        training = {"split": args.split.name, "salt": split.get("salt"),
                    "train_count": len(include), "holdout_count": split.get("holdout_count")}
    pack = build_pack(args.refs, args.hair, args.eyes, args.hood_up, args.hood_down,
                      include=include)
    if training:
        pack["training"] = training
    save_pack(pack, args.out)
    print(json.dumps({
        "out": str(args.out),
        "bytes": args.out.stat().st_size,
        "counts": pack["source_counts"],
        "patterns": {
            "hair_short": len(pack["hair"]["short"]),
            "hair_long": len(pack["hair"]["long"]),
            "eyes": len(pack["eyes"]),
            "hood_up": len(pack["hoods"]["up"]),
            "hood_down": len(pack["hoods"]["down"]),
        },
    }, indent=2))


if __name__ == "__main__":
    main()
