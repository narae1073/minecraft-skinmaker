"""입력 사진마다 단계별 샘플 시트를 만든다.

    python -m skinmaker.samples out/s0_photos -o out/samples

S1~S3 가 아직 없으므로 skin 자리는 더미 스킨으로 채운다. 헤더에 PLACEHOLDER 가
붙으므로 실제 결과로 오인하지 않는다.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from .debugview import PANEL_W, build_panels, contact_sheet
from .measure import SUFFIXES
from .placeholder import build_placeholder
from .quality import inspect

PLACEHOLDER_NOTE = "PLACEHOLDER skin (S3 not built yet)"

PLACEHOLDER_STYLE = {
    "placeholder_classic": ("#e0ac69", "#3a2a1c", "#2f6fb5", "#3c4450"),
    "placeholder_slim": ("#c98d5f", "#141414", "#8a3b3b", "#2a2f38"),
}


def render_for(path: Path, model: str, use_placeholder: bool) -> Image.Image:
    if use_placeholder:
        style = PLACEHOLDER_STYLE[f"placeholder_{model}"]
        return build_placeholder(model=model, skin=style[0], hair=style[1], shirt=style[2], pants=style[3]).image
    raise NotImplementedError("실제 렌더러는 S3 에서 추가된다")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skinmaker.samples")
    parser.add_argument("target", help="이미지 파일 또는 폴더")
    parser.add_argument("-o", "--out", default="out/samples")
    parser.add_argument("--model", choices=("classic", "slim"), default="classic")
    parser.add_argument("--no-placeholder", action="store_true")
    parser.add_argument("--scale-width", type=int, default=0, help="0 = 원본 폭")
    args = parser.parse_args(argv)

    target = Path(args.target)
    paths = [target] if target.is_file() else sorted(
        p for p in target.rglob("*") if p.suffix.lower() in SUFFIXES
    )
    if not paths:
        print("이미지 없음")
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    placeholder = not args.no_placeholder

    for p in paths:
        try:
            photo = inspect(p)
        except Exception as exc:
            print(f"SKIP {p.name}: {type(exc).__name__} {exc}")
            continue
        skin = render_for(p, args.model, placeholder)
        panels = build_panels(photo, skin, args.model)
        if placeholder:
            panels[0].note = (panels[0].note + "  |  " + PLACEHOLDER_NOTE).strip()
        sheet = contact_sheet(panels)
        if args.scale_width and args.scale_width != sheet.width:
            sheet = sheet.resize(
                (args.scale_width, int(sheet.height * args.scale_width / sheet.width)), Image.LANCZOS
            )
        dest = out_dir / f"{p.stem}_{args.model}.png"
        sheet.convert("RGB").save(dest)
        print(f"{dest}  ({'REJECTED' if photo.rejected else 'ok'} {','.join(photo.degrade) or 'clean'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
