"""S0 계측 도구. 폴더의 사진에拒绝율과 품질 신호 분포를 뽑는다.

    .venv/bin/python -m skinmaker.measure path/to/photos
"""
from __future__ import annotations

import argparse
import statistics
from collections import Counter
from pathlib import Path

from .quality import PhotoInput, inspect

SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic")


def collect(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in SUFFIXES)


def analyze(paths: list[Path], score_min: float) -> list[PhotoInput]:
    out = []
    for p in paths:
        try:
            out.append(inspect(p, score_min))
        except Exception as exc:
            out.append(PhotoInput(str(p), None, None, None, (f"error:{type(exc).__name__}",)))
    return out


def report(results: list[PhotoInput], show: int = 40) -> str:
    total = len(results)
    if total == 0:
        return "이미지 없음"
    errors = [r for r in results if r.degrade and r.degrade[0].startswith("error:")]
    rejected = [r for r in results if r.rejected and r not in errors]
    ok = [r for r in results if not r.rejected and r not in errors]

    lines = [f"전체 {total}  ·  검출 성공 {len(ok)}  ·  거절 {len(rejected)}  ·  오류 {len(errors)}"]
    if total:
        lines.append(f"거절율 {len(rejected) / total * 100:.1f}%  (목표 10% 이하)")

    flags = Counter(f for r in results for f in r.degrade if not f.startswith("error:"))
    if flags:
        lines.append("품질 플래그: " + "  ".join(f"{k}={v}" for k, v in sorted(flags.items())))

    measured = [r.quality for r in ok if r.quality and r.quality.measured]
    for label, values in (
        ("detection_score", [q.detection_score for q in measured]),
        ("face_px", [q.face_px for q in measured]),
        ("brightness", [q.brightness for q in measured]),
        ("sharpness", [q.sharpness for q in measured]),
        ("saturation", [q.saturation for q in measured]),
    ):
        if values:
            lines.append(
                f"  {label:16s} min={min(values):9.1f}  p50={statistics.median(values):9.1f}  max={max(values):9.1f}"
            )

    for r in results[:show]:
        face = "-" if r.face is None else f"{r.face.w}x{r.face.h}@{r.face.x},{r.face.y}"
        print(f"  {'REJ' if r.rejected else 'ok '} {Path(r.path).name:38s} {face:18s} {','.join(r.degrade)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skinmaker.measure")
    parser.add_argument("folder")
    parser.add_argument("--score-min", type=float, default=0.60)
    parser.add_argument("--show", type=int, default=40)
    args = parser.parse_args(argv)

    paths = collect(Path(args.folder))
    print(report(analyze(paths, args.score_min), args.show))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
