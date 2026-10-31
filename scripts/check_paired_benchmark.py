#!/usr/bin/env python3
"""Validate the hand-approved paired benchmark and write a report."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker.paired_benchmark import check_pairs

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("out/paired_benchmark"))
    ap.add_argument("--out", type=Path, default=Path("out/paired_benchmark/report.json"))
    args = ap.parse_args()
    report = check_pairs(args.root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("pair_count", "approved_count", "accepted")}, indent=2))

if __name__ == "__main__":
    main()
