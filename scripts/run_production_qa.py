#!/usr/bin/env python3
"""Run the deterministic production QA matrix."""
from __future__ import annotations
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker.production_qa import write_report

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("out/production_qa/report.json"))
    args = ap.parse_args()
    report = write_report(args.out)
    print(f"{report['case_count']} cases, ok={report['ok']}")
    for f in report["failures"]:
        print(f)
    raise SystemExit(0 if report["ok"] else 1)

if __name__ == "__main__":
    main()
