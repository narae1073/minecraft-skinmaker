#!/usr/bin/env python3
"""List/approve/reject paired-benchmark candidates. Approval is a human action."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker.paired_benchmark import discover_pairs, set_approval


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("out/paired_benchmark"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    for name in ("approve", "reject"):
        p = sub.add_parser(name); p.add_argument("id"); p.add_argument("--notes", default="")
    args = ap.parse_args()
    if args.cmd == "list":
        for pair in discover_pairs(args.root):
            print(f"{pair.id}\tapproved={pair.approved}\t{pair.notes}")
        return
    try:
        set_approval(args.root, args.id, args.cmd == "approve", args.notes)
    except FileNotFoundError:
        raise SystemExit(f"unknown pair: {args.id}")
    print(f"{args.id}: {'approved' if args.cmd == 'approve' else 'rejected'}")

if __name__ == "__main__":
    main()
