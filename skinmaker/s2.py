"""python -m skinmaker.s2 — 전송 계층 상태 확인 + 실제 분류 실행.

    python -m skinmaker.s2 --probe
    python -m skinmaker.s2 --transport gemini --photo a.jpg --photo b.jpg
    python -m skinmaker.s2 --transport ollama --host http://192.168.0.10:11434 --photo a.jpg
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .attributes import summarize
from .classify import classify
from .measure import SUFFIXES
from .quality import inspect
from .vlm import get_transport

TRANSPORTS = ("mock", "gemini", "ollama")


def probe(name: str, **cfg) -> int:
    transport = get_transport(name, **cfg)
    ok, detail = transport.available()
    print(f"{name:8s} {'OK ' if ok else 'NO '} {detail}")
    if ok and hasattr(transport, "model"):
        try:
            transport.complete(None, "ping", {})  # type: ignore[arg-type]
        except Exception:
            pass
    return 0 if ok else 1


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
        print(
            f"{p.name:34s} {result.elapsed:5.1f}s {'2회' if result.double_checked else '1회'}  "
            f"{summarize(result.attributes, result.uncertain)}"
        )
        if result.hair_bbox_px is not None:
            h = result.hair_bbox_px
            print(f"{'':34s} hair_bbox_px {h.w}x{h.h} @ {h.x},{h.y}")
        if args.dump and result.raw_first:
            print(f"{'':34s} raw1 {result.raw_first}")
            if result.raw_second:
                print(f"{'':34s} raw2 {result.raw_second}")

    print(f"\n{len(paths)}장 중 실패 {failures}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skinmaker.s2")
    parser.add_argument("--photo", action="append", default=[])
    parser.add_argument("--transport", choices=TRANSPORTS, default="mock")
    parser.add_argument("--model", default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--single", action="store_true", help="이중 질의 없이 1회만")
    parser.add_argument("--dump", action="store_true", help="원시 모델 출력 표시")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    if args.probe:
        bad = 0
        for name in TRANSPORTS:
            cfg = {"model": args.model, "host": args.host} if name != "mock" else {}
            bad += probe(name, **cfg)
        return 1 if bad else 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
