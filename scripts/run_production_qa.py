#!/usr/bin/env python3
"""Run the deterministic production QA matrix and render a contact sheet."""
from __future__ import annotations
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker import attribute_masks as AM
from skinmaker.production_qa import write_report

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("out/production_qa/report.json"))
    ap.add_argument("--image", type=Path, default=Path("out/production_qa/contact_sheet.png"))
    ap.add_argument("--asset", type=Path, help="QA a specific mask asset instead of the production default")
    ap.add_argument("--title")
    args = ap.parse_args()
    if args.asset:
        AM.ASSET_PATH = args.asset
    title = args.title or f"skinmaker production QA · {AM.ASSET_PATH.name} · {AM.ASSET_PATH}"
    report = write_report(args.out, image=args.image, title=title)
    print(f"{report['case_count']} cases, ok={report['ok']}")
    print(f"image: {args.image}")
    for f in report["failures"]:
        print(f)
    raise SystemExit(0 if report["ok"] else 1)

if __name__ == "__main__":
    main()
