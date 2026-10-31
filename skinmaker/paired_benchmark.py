"""Paired photo→skin benchmark scaffold.

Pairs are hand-approved ground truth, unlike the unpaired 600+ style corpus.
This module only ingests/validates pairs; it does not claim the current outputs
are approved references.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .validate import validate_image

PAIR_DIR = "pairs"
PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp")


@dataclass(frozen=True)
class Pair:
    id: str
    photo: Path
    skin: Path
    approved: bool = False
    notes: str = ""
    problems: tuple[str, ...] = field(default_factory=tuple)


def discover_pairs(root: Path) -> list[Pair]:
    root = Path(root) / PAIR_DIR if (Path(root) / PAIR_DIR).is_dir() else Path(root)
    pairs: list[Pair] = []
    if not root.is_dir():
        return pairs
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        skin = d / "skin.png"
        photos = [d / f"photo{e}" for e in PHOTO_EXTS]
        photo = next((p for p in photos if p.is_file()), None)
        meta = {}
        if (d / "meta.json").is_file():
            try:
                meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            except ValueError:
                meta = {}
        problems: list[str] = []
        if photo is None:
            problems.append("missing photo.<jpg|png|webp>")
        if not skin.is_file():
            problems.append("missing skin.png")
        pairs.append(Pair(
            id=d.name,
            photo=photo or d / "photo",
            skin=skin,
            approved=bool(meta.get("approved", False)),
            notes=str(meta.get("notes", "")),
            problems=tuple(problems),
        ))
    return pairs


def check_pairs(root: Path) -> dict:
    pairs = discover_pairs(root)
    approved = 0
    structural: list[dict] = []
    for p in pairs:
        problems = list(p.problems)
        if p.skin.is_file():
            try:
                with Image.open(p.skin) as im:
                    problems += [str(x) for x in validate_image(im.convert("RGBA"))]
            except OSError as exc:
                problems.append(f"skin unreadable: {exc}")
        if p.photo.is_file():
            try:
                with Image.open(p.photo) as im:
                    if im.width < 64 or im.height < 64:
                        problems.append(f"photo too small: {im.size}")
            except OSError as exc:
                problems.append(f"photo unreadable: {exc}")
        if p.approved:
            approved += 1
        structural.append({
            "id": p.id, "approved": p.approved, "photo": str(p.photo),
            "skin": str(p.skin), "problems": problems,
        })
    return {
        "version": 1,
        "pair_count": len(pairs),
        "approved_count": approved,
        "accepted": approved > 0 and all(not s["problems"] for s in structural if s["approved"]),
        "structural": structural,
        "note": "Approved pairs are ground truth. Unapproved pairs are regression-pilot candidates only.",
    }
