#!/usr/bin/env python3
"""Side/back hair A/B: current styles vs train-only reference faces."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker import render as R
from skinmaker.format import get_layout
from tests.test_render import observed, attrs

L = get_layout("classic")
FACES = ("front", "right", "back")

def strip(im: Image.Image) -> Image.Image:
    out = Image.new("RGBA", (8 * len(FACES), 8), (0, 0, 0, 0))
    for i, face in enumerate(FACES):
        cell = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        for layer in (0, 1):
            f = L.face("head", face, layer)
            bit = im.crop((f.x, f.y, f.x + 8, f.y + 8))
            cell.paste(bit, (0, 0), bit)
        out.paste(cell, (i * 8, 0))
    return out.resize((8 * len(FACES) * 12, 96), Image.NEAREST)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refs", type=Path, default=Path("out/reference_skins"))
    ap.add_argument("--split", type=Path, default=Path("out/production_benchmark/split.json"))
    ap.add_argument("--out", type=Path, default=Path("out/production_benchmark/hair_side_ab.png"))
    args = ap.parse_args()
    split = json.loads(args.split.read_text(encoding="utf-8"))
    refs = {"long": [], "short": []}
    for rel in split["train"]:
        bucket = "long" if Path(rel).parts[0] == "long_hair" else ("short" if Path(rel).parts[0] == "short_hair" else None)
        if bucket and len(refs[bucket]) < 3:
            refs[bucket].append(args.refs / rel)
    styles = {"long": ["long_straight", "long_wavy", "curly"], "short": ["short", "pixie", "ponytail"]}
    W, H, lab = 300, 125, 22
    sheet = Image.new("RGB", (4 * W, 2 * (3 * H + 26) + 8), (226, 232, 240))
    d = ImageDraw.Draw(sheet); y = 4
    for bucket in ("long", "short"):
        d.text((6, y), f"{bucket.upper()} — current 3 styles (col 1) | 3 train refs; front/right/back", fill=(30, 36, 44))
        y += lab
        for row, style in enumerate(styles[bucket]):
            c = R.render(observed(), attrs(hair_length=bucket if bucket == "short" else "long", hair_style=style), ())
            sheet.paste(strip(c.image), (6, y + row * H))
            d.text((6, y + row * H - 15), style, fill=(30, 36, 44))
            for col, ref in enumerate(refs[bucket], start=1):
                sheet.paste(strip(Image.open(ref).convert("RGBA")), (col * W + 6, y + row * H))
                d.text((col * W + 6, y + row * H - 15), ref.stem[:8], fill=(30, 36, 44))
        y += 3 * H + 8
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out)
    print(args.out, sheet.size)

if __name__ == "__main__":
    main()
