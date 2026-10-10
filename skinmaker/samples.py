"""입력 사진마다 단계별 샘플 시트를 만든다.

    python -m skinmaker.samples out/s0_photos -o out/samples
    python -m skinmaker.samples out/s0_photos -o out/samples --no-placeholder

기본은 더미 스킨이다. --no-placeholder면 S3 실렌더(S1 색 + 기본 enum)로 그린다.
S2 미연결이므로 enum 은 전부 기본값이다. S2 VLM 분류까지 연결하는 건 S4에서 한다.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from .colors import extract
from .debugview import PANEL_W, build_panels, contact_sheet
from .measure import SUFFIXES
from .placeholder import build_placeholder
from .quality import inspect

PLACEHOLDER_NOTE = "PLACEHOLDER skin (S3 not built yet)"
REAL_NOTE = "S3 real render (S1 colors + default enums, S2 not wired)"

PLACEHOLDER_STYLE = {
    "placeholder_classic": ("#e0ac69", "#3a2a1c", "#2f6fb5", "#3c4450"),
    "placeholder_slim": ("#c98d5f", "#141414", "#8a3b3b", "#2a2f38"),
}


def render_for(path: Path, model: str, use_placeholder: bool, observed=None, attrs=None, degrade=()) -> Image.Image:
    if use_placeholder:
        style = PLACEHOLDER_STYLE[f"placeholder_{model}"]
        return build_placeholder(model=model, skin=style[0], hair=style[1], shirt=style[2], pants=style[3]).image
    from .attributes import EMPTY
    from .render import render as render_s3

    return render_s3(observed, attrs or EMPTY, tuple(degrade), model).image


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skinmaker.samples")
    parser.add_argument("target", help="이미지 파일 또는 폴더")
    parser.add_argument("-o", "--out", default="out/samples")
    parser.add_argument("--model", choices=("classic", "slim"), default="classic")
    parser.add_argument("--no-placeholder", action="store_true")
    parser.add_argument("--patterned", action="store_true", help="상의가 무늬 있는 천일 때")
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
        observed = extract(photo, patterned=args.patterned)
        if photo.rejected:
            skin = render_for(p, args.model, True)
        else:
            from .attributes import EMPTY

            skin = render_for(p, args.model, placeholder, observed, EMPTY, photo.degrade)
        panels = build_panels(photo, skin, args.model, observed)
        tag = PLACEHOLDER_NOTE if placeholder else REAL_NOTE
        panels[-1].note = (panels[-1].note + "  |  " + tag).strip()
        def fmt(c):
            return "--" if c.missing else f"{c.hex}({c.share:.0%})"

        print(
            f"    skin={fmt(observed.skin)} hair={fmt(observed.hair)} "
            f"top={fmt(observed.top)} bottom={fmt(observed.bottom)} "
            f"wb={','.join(f'{g:.2f}' for g in observed.wb_gain)}"
            f"{'' if observed.wb_confident else ' CLIPPED'}"
        )
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
