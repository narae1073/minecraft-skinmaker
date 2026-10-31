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


def eye_score(c: dict) -> dict:
    """Objective readability score for human shortlisting (never approval)."""
    import numpy as np
    s = np.asarray(c["sclera"], dtype=bool)
    i = np.asarray(c["iris"], dtype=bool)
    ns, ni = int(s.sum()), int(i.sum())
    both = all(bool(s[:, a:b].any() and i[:, a:b].any()) for a, b in ((1, 3), (5, 7)))
    # Symmetry is guaranteed by extraction, but count adjacent sclera/iris support.
    adjacent = False
    for v in range(2):
        for u in range(1, 7):
            if s[v][u]:
                for du, dv in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    if 0 <= v + dv < 2 and 0 <= u + du < 8 and i[v + dv][u + du]:
                        adjacent = True
    score = (2 if ns >= 2 else 1 if ns else 0) + (2 if ni >= 2 else 1 if ni else 0)
    score += 2 if both else 0
    score += 1 if adjacent else 0
    return {"score": score, "both_eyes": both, "sclera_iris_adjacent": adjacent}


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
            e["source"] = rel
            e.update(eye_score(e))
            eyes[e["id"]] = e
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
    eye_list = sorted(eyes.values(), key=lambda c: (-c.get("score", 0), c["id"]))
    # recommended = objective shortlist, NOT approval
    for idx, c in enumerate(eye_list):
        c["recommended"] = idx < 6 and c.get("both_eyes", False) and c.get("score", 0) >= 5
    return {"eyes": eye_list, "hood_up": list(hood_up.values()),
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


def eye_preview_image(candidate: dict, scale: int = 24) -> Image.Image:
    """Render a candidate on a neutral 8x8 face (sclera/iris only)."""
    im = Image.new("RGB", (8, 8), (224, 172, 105))
    for v in range(2):
        for u in range(8):
            if candidate["sclera"][v][u]:
                im.putpixel((u, v + 4), (242, 242, 242))
            elif candidate["iris"][v][u]:
                im.putpixel((u, v + 4), (59, 42, 26))
    return im.resize((8 * scale, 8 * scale), Image.NEAREST)


def build_eye_preview(candidates: dict, out: Path) -> None:
    eyes = candidates.get("eyes", [])
    if not eyes:
        return
    W, H, label = 240, 260, 26
    cols = 4
    rows = (len(eyes) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * W + 20, rows * (H + label) + 10), (226, 232, 240))
    d = ImageDraw.Draw(sheet)
    for i, c in enumerate(eyes):
        x = (i % cols) * W + 6; y = (i // cols) * (H + label) + label
        sheet.paste(eye_preview_image(c), (x + 10, y + 4))
        d.text((x + 6, y - 18), f"{c['id']} score={c.get('score','-')} rec={c.get('recommended',False)}", fill=(30, 36, 44))
        d.text((x + 6, y + H - 8), c.get("source", "")[:34], fill=(60, 68, 78))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


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
        label_text = f"{kind} {c['id']}"
        if kind == "eye":
            label_text += f" score={c.get('score','-')} recommended={c.get('recommended', False)}"
        label_text += f" src={c.get('source','')[:24]}"
        d.text((6, y - 18), label_text, fill=(30, 36, 44))
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
