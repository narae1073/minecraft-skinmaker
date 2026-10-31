#!/usr/bin/env python3
"""Build train-only eye/hood candidate gallery + approval manifest."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker.template_review import collect_candidates, build_gallery

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refs", type=Path, default=Path("out/reference_skins"))
    ap.add_argument("--split", type=Path, default=Path("out/production_benchmark/split.json"))
    ap.add_argument("--out", type=Path, default=Path("out/production_benchmark"))
    args = ap.parse_args()
    split = json.loads(args.split.read_text(encoding="utf-8"))
    c = collect_candidates(args.refs, split)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "template_candidates.json").write_text(json.dumps(c, indent=2), encoding="utf-8")
    approvals = args.out / "template_approvals.json"
    if not approvals.is_file():
        approvals.write_text(json.dumps({}, indent=2), encoding="utf-8")
    build_gallery(c, args.out / "template_gallery.png")
    print(json.dumps({k: len(v) for k, v in c.items()}, indent=2))

if __name__ == "__main__":
    main()
