"""python -m skinmaker — 더미 스킨 생성 + 검증 + 프리뷰."""
from __future__ import annotations

import argparse
from pathlib import Path

from .placeholder import build_placeholder
from .preview import save_preview
from .validate import report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skinmaker", description="Minecraft 64x64 스킨 생성기")
    parser.add_argument("--model", choices=("classic", "slim"), default="classic")
    parser.add_argument("--out", default="out")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    canvas = build_placeholder(model=args.model)
    stem = f"placeholder_{args.model}"
    skin_path = out_dir / f"{stem}.png"
    preview_path = out_dir / f"{stem}_preview.png"

    canvas.image.save(skin_path)
    save_preview(canvas.image, str(preview_path), args.model)

    print(f"skin    : {skin_path} ({canvas.image.size[0]}x{canvas.image.size[1]} {canvas.image.mode})")
    print(f"preview : {preview_path}")
    print(f"check   : {report(canvas.image, args.model)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
