"""Render a representative photo sheet comparing production vs draft hair masks.

For each photo: observe it (YuNet + SCHP, no VLM), then render a hair matrix and
crop the torso so the body drape is readable. Production and draft are rendered
side by side; cells that differ are marked.

    .venv/bin/python scripts/render_photo_sheet.py --out out/theme/125-photo-sheet.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw

from skinmaker import attribute_masks as AM
from skinmaker import attributes as A
from skinmaker import colors as C
from skinmaker import parsing as P
from skinmaker import quality as QU
from skinmaker import render as R
from skinmaker.format import get_layout

PHOTO_ROOT = ROOT / "out" / "people_photos_original"
STYLES = ("long_straight", "long_wavy", "curly")
LENGTHS = ("short", "medium", "long", "very_long")
BASE = {
    "top_garment": "tee", "bottom_garment": "jeans", "pattern": "plain",
    "sleeve_len": "short", "hair_bbox": [200, 50, 800, 600],
}
SCALE = 5
PAD = 10
LABEL_H = 16
BG = (30, 26, 22)
INK = (200, 192, 178)
DIM = (140, 132, 120)
DIFF = (240, 190, 80)


def pick_photos(per_group: int) -> list[tuple[str, Path]]:
    picks: list[tuple[str, Path]] = []
    if not PHOTO_ROOT.is_dir():
        return picks
    for folder in sorted(p for p in PHOTO_ROOT.iterdir() if p.is_dir()):
        files = sorted(f for f in folder.rglob("*") if f.is_file())
        for f in files[:per_group]:
            picks.append((folder.name, f))
    return picks


def observe(path: Path):
    photo = QU.inspect(str(path))
    if photo.face is None:
        return None
    try:
        seg = P.bottom_mask(photo.image) if P.parsing_on() else None
    except Exception:
        seg = None
    return C.extract(photo, hair_bbox=QU.hair_region(photo.face), seg=seg, hair_overlay=True)


def body_crop(skin: Image.Image) -> Image.Image:
    """Torso front + back, the faces where the drape shows."""
    layout = get_layout("classic")
    parts = []
    for face in ("front", "back"):
        f = layout.face("body", face, 0)
        parts.append(skin.crop((f.x, f.y, f.x + f.w, f.y + f.h)))
    front, back = parts
    out = Image.new("RGBA", (front.width + back.width + 2, max(front.height, back.height)), (0, 0, 0, 0))
    out.paste(front, (0, 0))
    out.paste(back, (front.width + 2, 0))
    return out.resize((out.width * SCALE, out.height * SCALE), Image.NEAREST)


def max_channel_delta(a: Image.Image, b: Image.Image) -> int:
    """Largest per-channel difference between two crops (0 = identical)."""
    worst = 0
    pa, pb = a.convert("RGBA").load(), b.convert("RGBA").load()
    for y in range(a.height):
        for x in range(a.width):
            worst = max(worst, max(abs(p - q) for p, q in zip(pa[x, y], pb[x, y])))
    return worst


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "theme" / "125-photo-sheet.png")
    ap.add_argument("--per-group", type=int, default=1)
    ap.add_argument("--draft", type=Path, default=ROOT / "out" / "mask_editor" / "attribute_masks.json")
    ap.add_argument("--asset", type=Path, default=None)
    args = ap.parse_args(argv)

    prod = AM.load_masks(args.asset or AM.ASSET_PATH)
    draft = json.loads(args.draft.read_text(encoding="utf-8"))["masks"]

    photos = pick_photos(args.per_group)
    print(f"photos: {len(photos)}")
    rows = []
    for group, path in photos:
        observed = observe(path)
        if observed is None:
            print(f"  skip {group}/{path.name}: no face")
            continue
        thumb = Image.open(path).convert("RGB")
        thumb.thumbnail((72, 72))
        rows.append((group, path.name, thumb, observed))
        print(f"  observed {group}/{path.name} hair={observed.hair.hex}")
    if not rows:
        print("no usable photos", file=sys.stderr)
        return 2

    # Measure the first row to size the sheet.
    probe = body_crop(R.render(rows[0][3], A.validate(dict(BASE, hair_style=STYLES[0],
                                                           hair_length=LENGTHS[0])), (),
                               mask_override=prod).image)
    cw, ch = probe.size
    n_len = len(LENGTHS)
    row_w = PAD + 72 + PAD + n_len * (cw * 2 + PAD) + PAD
    row_h = ch + LABEL_H + PAD
    header = LABEL_H * 2
    width = row_w
    height = PAD + header + len(rows) * row_h + PAD

    sheet = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(sheet)
    draw.text((PAD, 4), f"torso front+back  ·  {', '.join(STYLES)}  ·  left = production, right = draft, gold = differs",
              fill=INK)
    x = PAD + 72 + PAD
    for length in LENGTHS:
        draw.text((x, PAD + LABEL_H - 4), length, fill=DIFF)
        x += cw * 2 + PAD

    y = PAD + header
    for group, name, thumb, observed in rows:
        sheet.paste(thumb, (PAD, y))
        draw.text((PAD, y + thumb.height + 2), group, fill=INK)
        draw.text((PAD, y + thumb.height + 14), name[:16], fill=DIM)
        x = PAD + 72 + PAD
        diffs = []
        for style in STYLES:
            for length in LENGTHS:
                attrs = A.validate(dict(BASE, hair_style=style, hair_length=length))
                a = body_crop(R.render(observed, attrs, (), mask_override=prod).image)
                b = body_crop(R.render(observed, attrs, (), mask_override=draft).image)
                delta = max_channel_delta(a, b)
                if delta > 0:
                    diffs.append(f"{style[:4]}/{length[:3]}={delta}")
                sheet.paste(a, (x, y))
                sheet.paste(b, (x + cw + 2, y))
                if delta > 2:
                    draw.rectangle([x - 2, y - 2, x + cw * 2 + 2, y + ch + 2], outline=DIFF)
                x += cw * 2 + PAD
        if diffs:
            draw.text((PAD + 72 + PAD, y + ch + 2), "mask delta: " + ", ".join(diffs), fill=DIFF)
        y += row_h

    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out)
    worst = 0
    for group, name, thumb, obs in rows:
        for style in STYLES:
            for length in LENGTHS:
                attrs = A.validate(dict(BASE, hair_style=style, hair_length=length))
                a = body_crop(R.render(obs, attrs, (), mask_override=prod).image)
                b = body_crop(R.render(obs, attrs, (), mask_override=draft).image)
                worst = max(worst, max_channel_delta(a, b))
    print(f"saved {args.out} ({sheet.width}x{sheet.height}), {len(rows)} photos, max channel delta {worst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
