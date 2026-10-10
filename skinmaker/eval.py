"""python -m skinmaker.eval — 출력물 품질의 객관 지표. VLM 없이 S1+기본값으로 잰다.

    python -m skinmaker.eval out/s0_photos --show 200

지표 (전부 코드로 재현 가능):
- valid: validate_image 통과율. 100% 아니면 렌더 버그.
- crown/cheek/torso: 렌더된 픽셀이 결정된 색과 정확히 일치하는가.
  렌더는 결정적이라 어긋나면 배선 버그다. 무늬 렌더면 torso 는 기록만 한다.
- yield: 영역별 실측 확신 비율. 낮으면 입력 탓, 어긋나면 코드 탓을 구분한다.

주관(닮음)은 contact sheet 로 사람이 본다. 이 CLI 는 그 전 단계의 버그 가리개다.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .attributes import EMPTY
from .canvas import shade
from .colors import ObservedColors, extract
from .measure import SUFFIXES
from .quality import FaceBox, PhotoInput, inspect
from .render import FACE_SHADE, effective_pattern, render, resolve_colors
from .validate import validate_image


@dataclass
class EvalRow:
    name: str
    rejected: bool = False
    valid: bool = False
    crown: bool = False
    cheek: bool = False
    torso: str = "-"
    fell_back: tuple[str, ...] = ()
    degrade: tuple[str, ...] = ()
    framing: str = "-"


# 리포트 밴드는 face_h/img_h 비율에서 직접 잰다 (고정 세트 선정 컷과 동일:
# full<0.10 / mid<0.20 / portrait≥0.20. docs/superpowers/specs/fixed10.txt 헤더 참조).
# classify.framing()의 0.12 2값 판정은 해상도 선택용으로만 쓰고 리포트에는 쓰지 않는다.
REPORT_FULL_MAX = 0.10
REPORT_MID_MAX = 0.20
_BANDS = ("full", "mid", "portrait")
_FALLBACK_KEYS = ("bottom", "hair", "skin", "top")


def report_band(photo: PhotoInput) -> str:
    """고정 세트와 같은 컷으로 구도 밴드를 돌려준다. 얼굴 없으면 "-" (거절 행)."""
    face = photo.face
    if face is None:
        return "-"
    _w, img_h = photo.image.size
    if img_h <= 0:
        return "-"
    ratio = face.h / img_h
    if ratio < REPORT_FULL_MAX:
        return "full"
    if ratio < REPORT_MID_MAX:
        return "mid"
    return "portrait"


def expected_pixel(observed: ObservedColors, key: str, face: str) -> tuple:
    return shade(resolve_colors(observed)[key], FACE_SHADE[face])


# --hair-box는 배선 확인용이다. 전 사진에 같은 고정 박스를 주입하므로
# 크기·구도가 다른 사진들에는 맞지 않아 <50% 기준의 증거가 될 수 없다.
# 그 기준에는 per-photo 박스(진짜 VLM 출력)가 필요하다. 동작 변경 없음.
HAIR_BOX_HELP = (
    '고정 헤어 박스 주입 "x,y,w,h" (배선 확인용. 전 사진 공통 박스라 '
    "<50%% 기준 증거가 안 됨. per-photo 박스는 VLM 출력 필요)"
)


def parse_hair_box(text: str) -> FaceBox:
    """`--hair-box "x,y,w,h"` 고정 주입 박스. VLM 없이 eval을 재현할 때 쓴다."""
    try:
        nums = [int(v) for v in text.split(",")]
    except ValueError:
        raise ValueError(f"--hair-box 형식 오류: {text!r} (x,y,w,h 정수 4개)")
    if len(nums) != 4 or min(nums) < 0:
        raise ValueError(f"--hair-box 형식 오류: {text!r} (x,y,w,h 정수 4개, 전부 0 이상)")
    if nums[2] < 2 or nums[3] < 2:
        raise ValueError(f"--hair-box가 너무 작다: {text!r}")
    return FaceBox(*nums)


def evaluate(photo: PhotoInput, observed: ObservedColors, model: str = "classic") -> EvalRow:
    row = EvalRow(photo.image.filename if hasattr(photo.image, "filename") else photo.path,
                  rejected=photo.rejected, degrade=photo.degrade)
    if photo.rejected:
        return row
    row.framing = report_band(photo)
    canvas = render(observed, EMPTY, photo.degrade, model)
    row.valid = validate_image(canvas.image, model) == []
    row.crown = canvas.get("head", "top", 0, 0) == expected_pixel(observed, "hair", "top")
    row.cheek = canvas.get("head", "front", 3, 5) == expected_pixel(observed, "skin", "front")
    pattern = effective_pattern(EMPTY.get("pattern"), observed, EMPTY, photo.degrade)
    if pattern == "plain":
        row.torso = "match" if canvas.get("body", "front", 0, 5) == expected_pixel(observed, "top", "front") else "MISMATCH"
    else:
        row.torso = f"patterned:{pattern}"
    colors = resolve_colors(observed)
    from .render import DEFAULT_BOTTOM, DEFAULT_HAIR, DEFAULT_SKIN, DEFAULT_TOP

    defaults = {"skin": DEFAULT_SKIN, "hair": DEFAULT_HAIR, "top": DEFAULT_TOP, "bottom": DEFAULT_BOTTOM}
    fell = []
    for key, dflt in defaults.items():
        sample = getattr(observed, key)
        if sample.missing or not sample.confident:
            fell.append(key)
    row.fell_back = tuple(fell)
    return row


def report(rows: list[EvalRow], show: int = 20) -> str:
    ok = [r for r in rows if not r.rejected]
    lines = [f"전체 {len(rows)}  ·  평가 {len(ok)}  ·  거절 {len(rows) - len(ok)}"]
    if ok:
        for label, sel in (
            ("valid", [r.valid for r in ok]),
            ("crown==hair", [r.crown for r in ok]),
            ("cheek==skin", [r.cheek for r in ok]),
            ("torso==top(plain만)", [r.torso == "match" for r in ok if r.torso in ("match", "MISMATCH")]),
        ):
            lines.append(f"  {label:20s} {sum(sel)}/{len(sel)}")
        torso_kinds = Counter(r.torso for r in ok)
        lines.append("  torso: " + "  ".join(f"{k}={v}" for k, v in sorted(torso_kinds.items())))
        all_fell = Counter(f for r in ok for f in r.fell_back)
        lines.append("  fallback: " + "  ".join(f"{k}={v}" for k, v in sorted(all_fell.items())))
        lines.append("  framing별 fallback:")
        for band in _BANDS:
            members = [r for r in ok if r.framing == band]
            if not members:
                lines.append(f"    {band}: n=0")
                continue
            fell = Counter(f for r in members for f in r.fell_back)
            detail = "  ".join(f"{k}={fell.get(k, 0)}/{len(members)}" for k in _FALLBACK_KEYS)
            lines.append(f"    {band}: n={len(members)} {detail}")
    bad = [r for r in ok if not (r.valid and r.crown and r.cheek and r.torso != "MISMATCH")]
    if bad:
        lines.append(f"불일치 {len(bad)}:")
        for r in bad[:show]:
            lines.append(f"  {Path(r.name).name:38s} valid={r.valid} crown={r.crown} cheek={r.cheek} torso={r.torso}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skinmaker.eval")
    parser.add_argument("target", help="이미지 파일 또는 폴더")
    parser.add_argument("--model", choices=("classic", "slim"), default="classic")
    parser.add_argument("--show", type=int, default=20)
    parser.add_argument("--hair-box", type=parse_hair_box, default=None, help=HAIR_BOX_HELP)
    args = parser.parse_args(argv)

    target = Path(args.target)
    paths = [target] if target.is_file() else sorted(
        p for p in target.rglob("*") if p.suffix.lower() in SUFFIXES
    )
    rows = []
    for p in paths:
        try:
            photo = inspect(p)
        except Exception as exc:
            print(f"SKIP {p.name}: {type(exc).__name__} {exc}")
            continue
        try:
            rows.append(evaluate(photo, extract(photo, hair_bbox=args.hair_box), args.model))
        except Exception as exc:
            print(f"SKIP {p.name}: {type(exc).__name__} {exc}")
            continue
    print(report(rows, args.show))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
