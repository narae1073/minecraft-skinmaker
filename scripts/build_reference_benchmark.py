#!/usr/bin/env python3
"""Build the stratified reference split + pack QA baseline."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker.reference_qa import write_report

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refs", type=Path, default=Path("out/reference_skins"))
    ap.add_argument("--out", type=Path, default=Path("out/production_benchmark"))
    ap.add_argument("--holdout", type=float, default=0.15)
    ap.add_argument("--max-holdout", type=int, default=100)
    args = ap.parse_args()
    result = write_report(args.refs, args.out, args.holdout, args.max_holdout)
    print(json.dumps({
        "out": str(args.out),
        "holdout": result["manifest"]["holdout_count"],
        "train": result["manifest"]["train_count"],
        "structural_ok": result["report"]["structural_ok"],
        "coverage": result["report"]["coverage"],
        "contamination": result["report"]["contamination"],
    }, indent=2))

if __name__ == "__main__":
    main()
