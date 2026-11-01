#!/usr/bin/env python3
"""A/B current hair styles against train-only reference head fronts."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker import render as R
from skinmaker.format import get_layout
from skinmaker.reference_pack import load_pack
from tests.test_render import observed, attrs

L = get_layout("classic")

def head_crop(path: Path) -> Image.Image:
    im = Image.open(path).convert("RGBA")
    out = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    for layer in (0, 1):
        f = L.face("head", "front", layer)
        bit = im.crop((f.x, f.y, f.x + 8, f.y + 8))
        out.paste(bit, (0, 0), bit)
    return out.resize((150, 150), Image.NEAREST)

def composite_head(im: Image.Image) -> Image.Image:
    out = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    for layer in (0, 1):
        f = L.face("head", "front", layer)
        bit = im.crop((f.x, f.y, f.x + 8, f.y + 8))
        out.paste(bit, (0, 0), bit)
    return out.resize((150, 150), Image.NEAREST)

def render_head(style: str, length: str) -> Image.Image:
    c = R.render(observed(), attrs(hair_length=length, hair_style=style), ())
    return composite_head(c.image)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refs", type=Path, default=Path("out/reference_skins"))
    ap.add_argument("--split", type=Path, default=Path("out/production_benchmark/split.json"))
    ap.add_argument("--out", type=Path, default=Path("out/production_benchmark/hair_ab.png"))
    args = ap.parse_args()
    split = json.loads(args.split.read_text(encoding="utf-8"))
    refs = {"long": [], "short": []}
    for rel in split["train"]:
        bucket = "long" if Path(rel).parts[0] == "long_hair" else ("short" if Path(rel).parts[0] == "short_hair" else None)
        if bucket and len(refs[bucket]) < 4:
            refs[bucket].append(args.refs / rel)
    styles = {
        "long": [("long_straight", "long"), ("long_wavy", "very_long"), ("curly", "long"), ("bob", "medium")],
        "short": [("short", "short"), ("pixie", "short"), ("ponytail", "long"), ("bun", "long")],
    }
    W, H, lab = 160, 175, 22
    sheet = Image.new("RGB", (5 * W, 2 * (4 * H + 30) + 12), (226, 232, 240))
    d = ImageDraw.Draw(sheet)
    y = 4
    for bucket in ("long", "short"):
        d.text((6, y), f"{bucket.upper()} — current 4 styles (left) | 4 train reference heads", fill=(30, 36, 44))
        y += lab
        for row, (style, length) in enumerate(styles[bucket]):
            x = 6
            sheet.paste(render_head(style, length), (x, y + row * H))
            d.text((x, y + row * H - 16), style, fill=(30, 36, 44))
            x += W
            for ref in refs[bucket][:4]:
                sheet.paste(head_crop(ref), (x, y + row * H))
                d.text((x, y + row * H - 16), ref.stem[:8], fill=(30, 36, 44))
                x += W
        y += 4 * H + 8
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out)
    print(args.out, sheet.size)

if __name__ == "__main__":
    main()
