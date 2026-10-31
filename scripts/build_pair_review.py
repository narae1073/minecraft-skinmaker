#!/usr/bin/env python3
"""Build [photo | skin front | skin back] review sheets for paired benchmark."""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image, ImageDraw, ImageOps
from skinmaker.paired_benchmark import discover_pairs

def render_pair(pair, root: Path) -> tuple[Path, Path]:
    out = root / "renders" / pair.id
    if not (out / "front_right.png").is_file():
        subprocess.run([sys.executable, "-m", "skinmaker.qarender", str(pair.skin),
                        "--out", str(out), "--views", "hair"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out / "front_right.png", out / "back_right.png"

def fit(path: Path, size=(220, 300)) -> Image.Image:
    im = Image.open(path).convert("RGB")
    im = ImageOps.contain(im, size)
    canvas = Image.new("RGB", size, (240, 244, 250))
    canvas.paste(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
    return canvas

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("out/paired_benchmark"))
    ap.add_argument("--out", type=Path, default=Path("out/paired_benchmark/review_sheet.png"))
    args = ap.parse_args()
    pairs = discover_pairs(args.root)
    if not pairs:
        print("no pairs"); return
    cell_w, cell_h, label = 220, 300, 26
    sheet = Image.new("RGB", (3 * cell_w + 20, len(pairs) * (cell_h + label) + 10), (226, 232, 240))
    d = ImageDraw.Draw(sheet)
    for row, pair in enumerate(pairs):
        front, back = render_pair(pair, args.root)
        y = row * (cell_h + label) + label
        for col, (path, tag) in enumerate(((pair.photo, "photo"), (front, "front"), (back, "back"))):
            x = col * (cell_w + 10) + 5
            sheet.paste(fit(path), (x, y))
            d.text((x, y - 18), f"{pair.id} {tag}", fill=(30, 36, 44))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out)
    print(args.out)

if __name__ == "__main__":
    main()
