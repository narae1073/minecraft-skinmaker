#!/usr/bin/env python3
"""Build a train-only bang/exposure review sheet and empty label file."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker.bang_benchmark import build_sheet, select_candidates

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refs", type=Path, default=Path("out/reference_skins"))
    ap.add_argument("--split", type=Path, default=Path("out/production_benchmark/split.json"))
    ap.add_argument("--out", type=Path, default=Path("out/production_benchmark"))
    ap.add_argument("--n", type=int, default=60)
    args = ap.parse_args()
    split = json.loads(args.split.read_text(encoding="utf-8"))
    cands = select_candidates(args.refs, split, args.n)
    (args.out / "bang_candidates.json").write_text(json.dumps(cands, indent=2), encoding="utf-8")
    labels = args.out / "bang_labels.json"
    if not labels.is_file():
        labels.write_text("{}\n", encoding="utf-8")
    build_sheet(args.refs, cands, args.out / "bang_review_sheet.png")
    print(json.dumps({"candidates": len(cands), "sheet": str(args.out / "bang_review_sheet.png")}))

if __name__ == "__main__":
    main()
