#!/usr/bin/env python3
"""Print/write the aggregate production gate. Exit 1 until all gates pass."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker.production_status import build_status

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", type=Path, default=Path("out/production_benchmark"))
    ap.add_argument("--paired", type=Path, default=Path("out/paired_benchmark"))
    ap.add_argument("--qa", type=Path, default=Path("out/production_qa/report.json"))
    ap.add_argument("--out", type=Path, default=Path("out/production_status.json"))
    args = ap.parse_args()
    status = build_status(args.bench, args.paired, args.qa)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps({"ready": status["ready"], "blockers": status["blockers"], "approved": status["approved"]}, indent=2))
    raise SystemExit(0 if status["ready"] else 1)

if __name__ == "__main__":
    main()
