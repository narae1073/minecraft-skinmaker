#!/usr/bin/env python3
"""List/approve/reject eye/hood template candidates. Human only."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker.template_review import load_approvals, set_approval

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("out/production_benchmark"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    for name in ("approve", "reject"):
        p = sub.add_parser(name); p.add_argument("kind"); p.add_argument("id"); p.add_argument("--notes", default="")
    args = ap.parse_args()
    cand_path = args.root / "template_candidates.json"
    cand = json.loads(cand_path.read_text(encoding="utf-8"))
    if args.cmd == "list":
        appr = load_approvals(args.root / "template_approvals.json")
        for kind, items in cand.items():
            for c in items:
                state = appr.get(kind, {}).get(c["id"], {}).get("approved", False)
                print(f"{kind}\t{c['id']}\tapproved={state}\tsrc={c.get('source','')}")
        return
    if args.kind not in cand or not any(c["id"] == args.id for c in cand[args.kind]):
        raise SystemExit("unknown candidate")
    set_approval(args.root / "template_approvals.json", args.kind, args.id,
                 args.cmd == "approve", args.notes)
    print(f"{args.kind}/{args.id}: {args.cmd}")

if __name__ == "__main__":
    main()
