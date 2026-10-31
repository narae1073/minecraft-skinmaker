#!/usr/bin/env python3
"""Set bang depth/exposure labels or summarize the labeled reference set."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker.bang_benchmark import load_labels, set_label, summarize, label_quality

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("out/production_benchmark"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("summary")
    p = sub.add_parser("set"); p.add_argument("id"); p.add_argument("--depth", type=int, required=True); p.add_argument("--exposure", choices=("covered", "partial", "exposed"), required=True)
    args = ap.parse_args()
    labels = args.root / "bang_labels.json"
    cands = json.loads((args.root / "bang_candidates.json").read_text(encoding="utf-8"))
    if args.cmd == "set":
        if not any(c["id"] == args.id for c in cands):
            raise SystemExit("unknown id")
        set_label(labels, args.id, args.depth, args.exposure)
        print("saved")
    else:
        print(json.dumps(summarize(load_labels(labels), cands), indent=2))

if __name__ == "__main__":
    main()
