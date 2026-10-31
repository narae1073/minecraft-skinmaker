"""Human review workflow for eye/hood template candidates.

Candidates are extracted from the TRAIN split only. Nothing enters the shipped
pack until a human approves it; this module never auto-approves.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import reference_pack as RP

EYE_ZONE = np.zeros((2, 8), dtype=bool)
EYE_ZONE[:, 1:3] = True
EYE_ZONE[:, 5:7] = True


def _hash(prefix: str, obj) -> str:
    return prefix + hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:10]


def extract_eye_candidate(image: Image.Image) -> dict | None:
    """Permissive eye shape (sclera optional) for human review only."""
    front = RP._face_array(image, "head", "front", 0)
    band = front[4:6, :, :]
    rgb = band[..., :3].astype(np.float32)
    alpha = band[..., 3] > 0
    baseline = np.concatenate([front[3:4, :, :3], front[6:8, :, :3]], axis=0).reshape(-1, 3)
    skin = np.median(baseline, axis=0)
    dist = np.sqrt(((rgb - skin) ** 2).sum(axis=2))
    mx = rgb.max(axis=2); mn = rgb.min(axis=2)
    sclera = alpha & (mx > 170) & ((mx - mn) < 38) & EYE_ZONE
    iris = alpha & ~sclera & (dist > 42) & (mx < 225) & EYE_ZONE
    ls = sclera[:, 1:3]; li = iris[:, 1:3]
    if int(ls.sum() + li.sum()) < 2:
        return None
    # Debug/approval data is full-width, mirrored from the left eye.
    s = np.zeros((2, 8), dtype=np.uint8); i = np.zeros((2, 8), dtype=np.uint8)
    s[:, 1:3] = ls; s[:, 5:7] = ls[:, ::-1]
    i[:, 1:3] = li; i[:, 5:7] = li[:, ::-1]
    return {
        "sclera": s.tolist(), "iris": i.tolist(),
        "sclera_px": int(s.sum()), "iris_px": int(i.sum()),
        "id": _hash("eye-", {"s": s.tolist(), "i": i.tolist()}),
    }


def collect_candidates(root: Path, split: dict) -> dict:
    root = Path(root)
    eyes: dict[str, dict] = {}
    hood_up: dict[str, dict] = {}
    hood_down: dict[str, dict] = {}
    for rel in split.get("train", []):
        path = root / rel
        try:
            im = RP._rgba(path)
        except OSError:
            continue
        e = extract_eye_candidate(im)
        if e and e["id"] not in eyes:
            e["source"] = rel; eyes[e["id"]] = e
        if rel.startswith("hood_up/"):
            h = RP.extract_hood_up(im)
            if h:
                hid = _hash("hood-up-", h["faces"])
                if hid not in hood_up:
                    h["id"] = hid; h["source"] = rel; hood_up[hid] = h
        elif rel.startswith("hood_down/"):
            h = RP.extract_hood_down(im)
            if h:
                hid = _hash("hood-down-", h["faces"])
                if hid not in hood_down:
                    h["id"] = hid; h["source"] = rel; hood_down[hid] = h
    return {"eyes": list(eyes.values()), "hood_up": list(hood_up.values()),
            "hood_down": list(hood_down.values())}


def load_approvals(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def set_approval(path: Path, kind: str, candidate_id: str, approved: bool, notes: str = "") -> None:
    """Human review only."""
    data = load_approvals(path)
    data.setdefault(kind, {})[candidate_id] = {"approved": bool(approved), "notes": notes}
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def build_gallery(candidates: dict, out: Path) -> None:
    """Contact sheet of eye/hood candidates; IDs are used by the review CLI."""
    rows = [("eye", c) for c in candidates.get("eyes", [])]
    rows += [("hood_up", c) for c in candidates.get("hood_up", [])]
    rows += [("hood_down", c) for c in candidates.get("hood_down", [])]
    cell_w, cell_h, label = 220, 190, 24
    sheet = Image.new("RGB", (cell_w * 4 + 20, len(rows) * (cell_h + label) + 10), (226, 232, 240))
    d = ImageDraw.Draw(sheet)
    for idx, (kind, c) in enumerate(rows):
        y = idx * (cell_h + label) + label
        d.text((6, y - 18), f"{kind} {c['id']} src={c.get('source','')[:24]}", fill=(30, 36, 44))
        if kind == "eye":
            im = Image.new("RGB", (8, 2), (35, 35, 35))
            for v in range(2):
                for u in range(8):
                    if c["sclera"][v][u]: im.putpixel((u, v), (242, 242, 242))
                    elif c["iris"][v][u]: im.putpixel((u, v), (220, 80, 60))
            im = im.resize((cell_w, cell_h), Image.NEAREST)
        else:
            faces = c["faces"]
            name = "front" if "front" in faces else next(iter(faces))
            arr = faces[name]
            im = Image.new("RGB", (8, len(arr)), (255, 255, 255))
            for v, row in enumerate(arr):
                for u, val in enumerate(row):
                    if val: im.putpixel((u, v), (70, 70, 80))
            im = im.resize((cell_w, cell_h), Image.NEAREST)
        sheet.paste(im, (6, y))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
