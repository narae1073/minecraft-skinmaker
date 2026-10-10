"""python -m skinmaker.s4 — 사진 → S2 분류 → S4 후보 N개 저장 + 검증 보고.

    python -m skinmaker.s4 --transport mock --photo out/s0_photos/lena.jpg --out out/s4
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .attributes import summarize
from .candidates import build
from .classify import classify
from .colors import extract
from .measure import SUFFIXES
from .quality import inspect
from .vlm import get_transport


def run(args) -> int:
    paths: list[Path] = []
    for target in args.photo:
        p = Path(target)
        if p.is_dir():
            paths.extend(sorted(x for x in p.rglob("*") if x.suffix.lower() in SUFFIXES))
        elif p.suffix.lower() in SUFFIXES:
            paths.append(p)
        else:
            print(f"건너뜀: {p}")
    if not paths:
        print("처리할 이미지 없음")
        return 1

    transport = get_transport(args.transport, model=args.model, host=args.host)
    ok, detail = transport.available()
    print(f"{args.transport:8s} {'OK ' if ok else 'NO '} {detail}")
    if not ok and not args.force:
        print("사용 불가. --force 로 강행 가능")
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for p in paths:
        photo = inspect(p)
        if photo.rejected:
            print(f"{p.name:34s} REJECTED (얼굴 미검출)")
            continue
        result = classify(photo, transport, double_check=not args.single)
        if not result.ok:
            print(f"{p.name:34s} FAIL {result.error}")
            failures += 1
            continue
        observed = extract(photo, patterned=args.patterned)
        candidates = build(observed, result, photo.degrade, args.skin)
        print(f"{p.name:34s} 후보 {len(candidates)}  {summarize(result.attributes, result.uncertain)}")
        for c in candidates:
            dest = out_dir / f"{p.stem}_{args.skin}_c{c.index}.png"
            c.image.save(dest)
            print(f"{'':34s} c{c.index} {c.varied:42s} {'OK' if c.ok else 'FAIL ' + '; '.join(c.problems[:3])}  {dest.name}")
            if not c.ok:
                failures += 1

    print(f"\n{len(paths)}장 중 실패 {failures}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skinmaker.s4")
    parser.add_argument("--photo", action="append", default=[])
    parser.add_argument("--transport", default="mock")
    parser.add_argument("--model", default=None, help="VLM 모델명")
    parser.add_argument("--host", default=None)
    parser.add_argument("--skin", choices=("classic", "slim"), default="classic")
    parser.add_argument("--single", action="store_true", help="이중 질의 없이 1회만")
    parser.add_argument("--patterned", action="store_true", help="상의가 무늬 있는 천일 때")
    parser.add_argument("--out", default="out/s4")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
