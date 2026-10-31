"""Labeled bang/exposure benchmark from reference head fronts (train only)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from .format import get_layout

DEPTHS = range(0, 9)
EXPOSURES = ("covered", "partial", "exposed")


def select_candidates(root: Path, split: dict, n: int = 60) -> list[dict]:
    root = Path(root)
    by_group: dict[str, list[str]] = {"long": [], "short": []}
    for rel in split.get("train", []):
        parts = Path(rel).parts
        if parts and parts[0] == "long_hair":
            by_group["long"].append(rel)
        elif parts and parts[0] == "short_hair":
            by_group["short"].append(rel)
    out: list[dict] = []
    for length, rels in by_group.items():
        rels = sorted(rels, key=lambda r: hashlib.sha256(f"bang:{r}".encode()).hexdigest())
        take = max(1, round(n * len(rels) / max(1, sum(len(v) for v in by_group.values()))))
        for rel in rels[:take]:
            out.append({"id": Path(rel).stem, "length": length, "source": rel})
    return out[:n]


def _head(path: Path) -> Image.Image:
    im = Image.open(path).convert("RGBA")
    L = get_layout("classic")
    l1 = L.face("head", "front", 0); l2 = L.face("head", "front", 1)
    head = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    head.paste(im.crop((l1.x, l1.y, l1.x + 8, l1.y + 8)), (0, 0))
    head.paste(im.crop((l2.x, l2.y, l2.x + 8, l2.y + 8)), (0, 0), im.crop((l2.x, l2.y, l2.x + 8, l2.y + 8)))
    return head.resize((120, 120), Image.NEAREST)


def build_sheet(root: Path, candidates: list[dict], out: Path) -> None:
    cols, W, H, label = 6, 130, 150, 22
    rows = (len(candidates) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * W, rows * (H + label) + 8), (226, 232, 240))
    d = ImageDraw.Draw(sheet)
    for i, c in enumerate(candidates):
        x = (i % cols) * W; y = (i // cols) * (H + label) + label
        sheet.paste(_head(Path(root) / c["source"]), (x + 5, y))
        d.text((x + 4, y - 18), f"{c['id'][:8]} {c['length']}", fill=(30, 36, 44))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def load_labels(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def set_label(path: Path, candidate_id: str, depth: int, exposure: str) -> None:
    if depth not in DEPTHS or exposure not in EXPOSURES:
        raise ValueError("invalid label")
    data = load_labels(path)
    data[candidate_id] = {"depth": int(depth), "exposure": exposure}
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def summarize(labels: dict, candidates: list[dict]) -> dict:
    by_length = {length: [] for length in ("long", "short")}
    for c in candidates:
        lab = labels.get(c["id"])
        if lab:
            by_length[c["length"]].append(lab)
    out = {}
    for length, rows in by_length.items():
        if not rows:
            out[length] = {"n": 0}
            continue
        depths = sorted(r["depth"] for r in rows)
        out[length] = {
            "n": len(rows),
            "median_depth": depths[len(depths) // 2],
            "exposure": {k: sum(1 for r in rows if r["exposure"] == k) for k in EXPOSURES},
        }
    return out
