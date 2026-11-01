#!/usr/bin/env python3
"""Write the reference bang prior from human labels (skew is allowed)."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker.bang_benchmark import load_labels, summarize

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("out/production_benchmark"))
    ap.add_argument("--out", type=Path, default=Path("assets/bang_prior.json"))
    args = ap.parse_args()
    labels = load_labels(args.root / "bang_labels.json")
    cands = json.loads((args.root / "bang_candidates.json").read_text(encoding="utf-8"))
    summary = summarize(labels, cands)
    if not summary["quality"]["usable"]:
        raise SystemExit(f"labels unusable: {summary['quality']['reason']}")
    prior = {"version": 1, "source": "human bang labels", "quality": summary["quality"], "by_length": summary["by_length"]}
    args.out.write_text(json.dumps(prior, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(prior, indent=2))

if __name__ == "__main__":
    main()
