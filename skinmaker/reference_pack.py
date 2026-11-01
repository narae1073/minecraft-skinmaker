"""Reference-skin pattern extraction for hair L2, eyes, and clothing hoods.

References are 64x64 Minecraft skins. We never emit a reference skin: the
pack stores derived tone maps and tiny masks, then the renderer composes them
over the current photo-driven UV stencil.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image

from .format import get_layout

HEAD_FACES = ("top", "front", "back", "right", "left")
EYE_ROWS = (4, 5)
EYE_COLS = 8
HAIR_DEFAULT = 100


def load_eye_blocklist(path: Path | None = None) -> set[str]:
    path = path or Path(__file__).resolve().parent.parent / "assets" / "eye_source_blocklist.json"
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return {str(x) for x in data.get("sources", [])}
    except (OSError, ValueError):
        return set()


def eye_source_blocked(stem: str) -> bool:
    return stem in load_eye_blocklist()


def _rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def _face_array(image: Image.Image, part: str, face: str, layer: int) -> np.ndarray:
    box = get_layout("classic").face(part, face, layer)
    crop = image.crop((box.x, box.y, box.x + box.w, box.y + box.h))
    return np.asarray(crop, dtype=np.uint8)


def _luma(rgb: np.ndarray) -> np.ndarray:
    return (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2])


def extract_hair_pattern(image: Image.Image) -> dict | None:
    """L2 hair tone map (percent of the face median luma), five head faces."""
    faces: dict[str, list[list[int]]] = {}
    coverage = 0
    for name in HEAD_FACES:
        l2 = _face_array(image, "head", name, 1)
        opaque = l2[..., 3] > 0
        n = int(opaque.sum())
        coverage += n
        if n < 4:
            faces[name] = [[HAIR_DEFAULT] * 8 for _ in range(8)]
            continue
        lum = _luma(l2[..., :3].astype(np.float32))
        median = float(np.median(lum[opaque]))
        if median < 1.0:
            faces[name] = [[HAIR_DEFAULT] * 8 for _ in range(8)]
            continue
        tones = np.full((8, 8), HAIR_DEFAULT, dtype=np.int16)
        ratio = np.clip(np.rint(100.0 * lum / median), 78, 126).astype(np.int16)
        tones[opaque] = ratio[opaque]
        faces[name] = tones.tolist()
    if coverage < 12:
        return None
    return {"faces": faces, "coverage": coverage}


MASK_FACES = HEAD_FACES + ("bottom",)
# L1 crown colour distance (sum |dRGB|) under which an L2 pixel counts as hair.
# Rejects bows/clips/glasses on L2 (3-9% of reference L2 pixels).
HAIR_COLOUR_TOL = 150


def extract_hair_mask(image: Image.Image) -> dict[str, np.ndarray] | None:
    """Hair-coloured L2 cells per head face (8x8 bool), or None if no L2 hair.

    Reference L2 hair is a sparse sculpt (median coverage top 0.12, sides
    0.20, back 0.38, front 0.45), not a copy of the L1 silhouette.
    """
    crown = _face_array(image, "head", "top", 0)[..., :3].reshape(-1, 3).astype(np.int32)
    hair_c = np.median(crown, axis=0)
    masks: dict[str, np.ndarray] = {}
    total = 0
    for name in MASK_FACES:
        l2 = _face_array(image, "head", name, 1).astype(np.int32)
        hairish = np.abs(l2[..., :3] - hair_c).sum(axis=-1) < HAIR_COLOUR_TOL
        m = (l2[..., 3] > 0) & hairish
        masks[name] = m
        total += int(m.sum())
    return masks if total >= 12 else None


def _mask_vec(masks: dict[str, np.ndarray]) -> np.ndarray:
    return np.concatenate([np.asarray(masks[f], dtype=bool).reshape(-1) for f in MASK_FACES])


def cluster_hair_masks(masks: list[dict[str, np.ndarray]], k: int, iters: int = 12,
                       min_count: int = 10) -> list[dict]:
    """Deterministic k-medoids (Hamming) over whole-head masks.

    Each cluster template is the per-cell majority vote of its members, so
    one-off accessories and noise fall out while shared strands survive.
    Whole-head (not per-face) clustering keeps corners coherent across faces.
    Clusters with fewer than min_count members are dropped: they are one-off
    skins (accessories, hoods) rather than a shared hair shape.
    """
    if not masks:
        return []
    X = np.stack([_mask_vec(m) for m in masks]).astype(np.int8)
    n = len(X)
    k = min(k, n)
    D = (X[:, None, :] != X[None, :, :]).sum(axis=-1)
    medoids = [int(np.argmin(D.sum(axis=1)))]
    while len(medoids) < k:
        d = D[:, medoids].min(axis=1)
        d[medoids] = -1
        medoids.append(int(np.argmax(d)))
    for _ in range(iters):
        assign = np.argmin(D[:, medoids], axis=1)
        new = []
        for c in range(k):
            members = np.flatnonzero(assign == c)
            if not members.size:
                new.append(medoids[c])
                continue
            sub = D[np.ix_(members, members)].sum(axis=1)
            new.append(int(members[int(np.argmin(sub))]))
        if new == medoids:
            break
        medoids = new
    assign = np.argmin(D[:, medoids], axis=1)
    out = []
    for c in range(k):
        members = np.flatnonzero(assign == c)
        if members.size < max(1, min(min_count, n)):
            continue
        vote = X[members].mean(axis=0) >= 0.5
        faces = {}
        for i, f in enumerate(MASK_FACES):
            faces[f] = vote[i * 64:(i + 1) * 64].reshape(8, 8).astype(np.uint8).tolist()
        out.append({"faces": faces, "count": int(members.size)})
    out.sort(key=lambda t: -t["count"])
    return out


def extract_eye_pattern(image: Image.Image) -> dict | None:
    """Sclera/iris masks in the standard front rows 4-5.

    Skin pixels are deliberately left out (0,0); they remain the rendered face.
    """
    front = _face_array(image, "head", "front", 0)
    band = front[EYE_ROWS[0]:EYE_ROWS[1] + 1, :, :]
    rgb = band[..., :3].astype(np.float32)
    alpha = band[..., 3] > 0
    # Face baseline from the lower face / row 3.
    baseline_rows = np.concatenate([front[3:4, :, :3], front[6:8, :, :3]], axis=0)
    baseline_rows = baseline_rows.reshape(-1, 3)
    skin = np.median(baseline_rows, axis=0)
    dist = np.sqrt(((rgb - skin) ** 2).sum(axis=2))

    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    sclera = alpha & (mx > 170) & ((mx - mn) < 38)
    iris = alpha & ~sclera & (dist > 42) & (mx < 225)
    # Use the left eye as the canonical template and mirror it: references
    # often hide one eye under bangs, which must not make the face one-eyed.
    ls = sclera[:, 1:3]
    li = iris[:, 1:3]
    ns, ni = int(ls.sum()), int(li.sum())
    if not (2 <= ns <= 4 and 2 <= ni <= 4):
        return None
    sclera = np.zeros((2, 8), dtype=bool)
    iris = np.zeros((2, 8), dtype=bool)
    sclera[:, 1:3] = ls
    sclera[:, 5:7] = ls[:, ::-1]
    iris[:, 1:3] = li
    iris[:, 5:7] = li[:, ::-1]
    return {
        "sclera": sclera.astype(np.uint8).tolist(),
        "iris": iris.astype(np.uint8).tolist(),
        "coverage": int((sclera | iris).sum()),
    }


def _close_mask(mask: np.ndarray) -> np.ndarray:
    """Fill small interior gaps; keep the outer silhouette."""
    a = np.asarray(mask, dtype=bool)
    for _ in range(2):
        n = np.zeros_like(a, dtype=int)
        n[1:, :] += a[:-1, :]
        n[:-1, :] += a[1:, :]
        n[:, 1:] += a[:, :-1]
        n[:, :-1] += a[:, 1:]
        a |= (~a) & (n >= 3)
    return a


def extract_hood_up(image: Image.Image) -> dict | None:
    """Solid L2 crown for a clothing hood; five faces.

    A raw L2 alpha mask is hair + hood + gaps. A hood shell needs full crown
    coverage, so sparse masks are rejected and the front becomes a solid brim
    with a face opening below it.
    """
    raw: dict[str, np.ndarray] = {}
    for name in HEAD_FACES:
        l2 = _face_array(image, "head", name, 1)
        raw[name] = l2[..., 3] > 0
    coverage = int(sum(int(m.sum()) for m in raw.values()))
    if int(raw["top"].sum()) < 56 or coverage < 160:
        return None
    faces: dict[str, list[list[int]]] = {}
    for name, mask in raw.items():
        solid = np.ones((8, 8), dtype=bool)  # a hood shell is contiguous
        if name == "front":
            solid[:3, :] = True     # solid brim
            solid[3:, :] = False    # face opening
        faces[name] = solid.astype(np.uint8).tolist()
    return {"faces": faces, "coverage": coverage}


def extract_hood_down(image: Image.Image) -> dict | None:
    """L2 body cowl near the neck; front/back rows 0-3."""
    masks: dict[str, list[list[int]]] = {}
    coverage = 0
    for name in ("front", "back"):
        l2 = _face_array(image, "body", name, 1)[:4, :, :]
        mask = (l2[..., 3] > 0).astype(np.uint8)
        coverage += int(mask.sum())
        masks[name] = mask.tolist()
    if coverage < 8:
        return None
    return {"faces": masks, "coverage": coverage}


def _feature(pattern: dict, kind: str) -> np.ndarray:
    if kind == "hair":
        return np.asarray(
            [pattern["faces"][f] for f in HEAD_FACES], dtype=np.float32
        ).reshape(-1) / 100.0
    if kind == "eye":
        return np.concatenate([
            np.asarray(pattern["sclera"], dtype=np.float32).reshape(-1),
            np.asarray(pattern["iris"], dtype=np.float32).reshape(-1),
        ])
    # hood up/down
    return np.concatenate([
        np.asarray(pattern["faces"][f], dtype=np.float32).reshape(-1)
        for f in pattern["faces"]
    ])


def _medoids(patterns: list[dict], kind: str, k: int) -> list[dict]:
    if not patterns:
        return []
    feats = np.stack([_feature(p, kind) for p in patterns])
    # Normalize dimensions so big masks do not dominate.
    scale = np.maximum(feats.std(axis=0), 1e-3)
    norm = (feats - feats.mean(axis=0)) / scale
    chosen = [int(np.argmax([p.get("coverage", 0) for p in patterns]))]
    while len(chosen) < min(k, len(patterns)):
        d = np.min(
            np.stack([
                np.abs(norm - norm[i]).mean(axis=1) for i in chosen
            ]),
            axis=0,
        )
        d[chosen] = -1
        chosen.append(int(np.argmax(d)))
    return [patterns[i] for i in chosen]


def build_pack(root: Path, k_hair: int = 6, k_eyes: int = 6, k_hood_up: int = 4,
               k_hood_down: int = 2, include: set[str] | None = None,
               k_masks: int = 8) -> dict:
    """Build a derived pack from out/reference_skins.

    include: optional relative paths (posix) to use; used to build a train-only
    pack so the benchmark holdout stays unseen.
    """
    root = Path(root)
    def allowed(path: Path) -> bool:
        if include is None:
            return True
        return path.relative_to(root).as_posix() in include
    hair: dict[str, list[dict]] = {"short": [], "long": []}
    bang_tips: dict[str, list[list[int]]] = {"short": [], "long": []}
    edge_bits: dict[str, dict[str, list[list[int]]]] = {
        "long": {"right": [], "left": [], "back": []},
        "short": {"right": [], "left": [], "back": []},
    }
    eyes: list[dict] = []
    seen_eyes: set[tuple] = set()
    hair_masks: dict[str, list[dict[str, np.ndarray]]] = {"short": [], "long": []}

    for length in ("short", "long"):
        for path in sorted((root / f"{length}_hair").glob("*.png")):
            if not allowed(path):
                continue
            image = _rgba(path)
            hm = extract_hair_mask(image)
            if hm:
                hair_masks[length].append(hm)
            hp = extract_hair_pattern(image)
            if hp:
                hp["source"] = path.name
                hair[length].append(hp)
                l2 = _face_array(image, "head", "front", 1)
                bits = [1 if l2[4][u][3] else 0 for u in range(8)]
                bang_tips[length].append(bits)
                for face_name in ("right", "left", "back"):
                    ef = _face_array(image, "head", face_name, 1)
                    for u in (0, 7):
                        edge_bits[length][face_name].append([1 if ef[v][u][3] else 0 for v in range(8)])
            ep = None if eye_source_blocked(path.stem) else extract_eye_pattern(image)
            if ep:
                key = (tuple(map(tuple, ep["sclera"])), tuple(map(tuple, ep["iris"])))
                if key not in seen_eyes:
                    seen_eyes.add(key)
                    ep["source"] = path.name
                    eyes.append(ep)

    hood_up = []
    for path in sorted((root / "hood_up").rglob("*.png")):
        if not allowed(path):
            continue
        hp = extract_hood_up(_rgba(path))
        if hp:
            hp["source"] = path.name
            hood_up.append(hp)
    hood_down = []
    for path in sorted((root / "hood_down").rglob("*.png")):
        if not allowed(path):
            continue
        hp = extract_hood_down(_rgba(path))
        if hp:
            hp["source"] = path.name
            hood_down.append(hp)

    pack = {
        "version": 1,
        "kind": "reference-pattern-pack",
        "license": "derived from user-provided reference skins; no raw skin pixels",
        "source_counts": {
            "long_hair": len(hair["long"]),
            "short_hair": len(hair["short"]),
            "eyes_unique": len(eyes),
            "hood_up": len(hood_up),
            "hood_down": len(hood_down),
        },
        "hair": {
            "short": _medoids(hair["short"], "hair", k_hair),
            "long": _medoids(hair["long"], "hair", k_hair),
        },
        "bang_tips": {
            # Most frequent reference L2 row4 patterns (e.g. 11011011).
            length: [list(bits) for bits, _ in
                     sorted(__import__("collections").Counter(map(tuple, bang_tips[length])).items(),
                            key=lambda kv: -kv[1])[:3]]
            for length in ("short", "long")
        },
        "edge_masks": {
            face: [list(bits) for bits, _ in
                   sorted(__import__("collections").Counter(
                       map(tuple, edge_bits["long"][face] + edge_bits["short"][face])
                   ).items(), key=lambda kv: -kv[1])[:3]]
            for face in ("right", "left", "back")
        },
        "edge_masks_by_length": {
            length: {
                face: [list(bits) for bits, _ in
                       sorted(__import__("collections").Counter(map(tuple, edge_bits[length][face])).items(),
                              key=lambda kv: -kv[1])[:3]]
                for face in ("right", "left", "back")
            }
            for length in ("long", "short")
        },
        # Whole-head L2 hair sculpt templates (majority vote per cluster).
        "hair_masks": {
            length: cluster_hair_masks(hair_masks[length], k_masks)
            for length in ("short", "long")
        },
        "eyes": _medoids(eyes, "eye", k_eyes),
        "hoods": {
            "up": _medoids(hood_up, "hood", k_hood_up),
            "down": _medoids(hood_down, "hood", k_hood_down),
        },
    }
    for patterns in (pack["hair"]["short"], pack["hair"]["long"], pack["eyes"],
                     pack["hair_masks"]["short"], pack["hair_masks"]["long"],
                     pack["hoods"]["up"], pack["hoods"]["down"]):
        for p in patterns:
            # Keep provenance hashes, not file paths in the renderer-facing pack.
            p["id"] = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()[:12]
    return pack


def apply_template_approvals(pack: dict, candidates: dict, approvals: dict) -> dict:
    """Replace pack eye/hood templates with human-approved candidates only.

    Approved patterns are copied from the train-only candidate set; unapproved
    candidates never enter the pack. Hair templates remain train-only.
    """
    template_approvals: dict[str, list[str]] = {}
    for kind, pack_key in (("eyes", "eyes"), ("hood_up", "up"), ("hood_down", "down")):
        approved = {
            cid for cid, meta in approvals.get(kind, {}).items()
            if isinstance(meta, dict) and meta.get("approved")
        }
        chosen = [c for c in candidates.get(kind, []) if c.get("id") in approved]
        if chosen:
            if kind == "eyes":
                pack["eyes"] = chosen
            else:
                pack.setdefault("hoods", {})[pack_key] = chosen
            template_approvals[kind] = [c["id"] for c in chosen]
    if template_approvals:
        pack["template_approvals"] = template_approvals
    return pack


def save_pack(pack: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pack, separators=(",", ":"), sort_keys=True), encoding="utf-8")


@lru_cache(maxsize=1)
def load_pack(path: str | None = None) -> dict | None:
    path = path or str(Path(__file__).resolve().parent.parent / "assets" / "reference_pack.json")
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _pick(items: Iterable[dict], seed: str) -> dict | None:
    items = list(items)
    if not items:
        return None
    h = int.from_bytes(hashlib.sha256(seed.encode()).digest()[:4], "big")
    return items[h % len(items)]


def select_hair(pack: dict, length: str, style: str, seed: str = "") -> dict | None:
    bucket = "long" if length in ("long", "very_long") or style in (
        "long_straight", "long_wavy", "curly", "ponytail", "bun"
    ) else "short"
    return _pick(pack.get("hair", {}).get(bucket, []), f"{bucket}:{style}:{seed}")


def select_eyes(pack: dict, seed: str = "", hooded: bool = False) -> dict | None:
    """Weighted selection; explicit eye_weights make c252 the dominant style.

    The previous hooded/source filter left only eye-463 for hooded renders. The
    user's explicit preference now wins: all approved eyes are eligible for
    hooded and non-hooded photos, with c252 weighted most frequent.
    """
    eyes = pack.get("eyes", [])
    if not eyes:
        return None
    weights = pack.get("eye_weights", {})
    total = sum(max(1, int(weights.get(e.get("id", ""), 1))) for e in eyes)
    h = int.from_bytes(hashlib.sha256(f"eyes:{seed}:{'hood' if hooded else 'general'}".encode()).digest()[:4], "big")
    pick = h % total
    for e in eyes:
        w = max(1, int(weights.get(e.get("id", ""), 1)))
        if pick < w:
            return e
        pick -= w
    return eyes[-1]


def select_bang_tips(pack: dict, length: str, style: str, seed: str = "") -> list[int] | None:
    bucket = "long" if length in ("long", "very_long") or style in (
        "long_straight", "long_wavy", "curly", "ponytail", "bun"
    ) else "short"
    tips = pack.get("bang_tips", {}).get(bucket) or []
    if not tips:
        return None
    h = int.from_bytes(hashlib.sha256(f"tips:{bucket}:{style}:{seed}".encode()).digest()[:4], "big")
    return tips[h % len(tips)]


def select_edge_mask(pack: dict, face_name: str, seed: str = "", length: str = "long") -> list[int] | None:
    bucket = "long" if length in ("long", "very_long") else "short"
    masks = pack.get("edge_masks_by_length", {}).get(bucket, {}).get(face_name)
    if masks is None:
        masks = pack.get("edge_masks", {}).get(face_name) or []
    if not masks:
        return None
    h = int.from_bytes(hashlib.sha256(f"edge:{face_name}:{seed}".encode()).digest()[:4], "big")
    return masks[h % len(masks)]


def select_hood(pack: dict, kind: str, seed: str = "") -> dict | None:
    return _pick(pack.get("hoods", {}).get(kind, []), f"hood:{kind}:{seed}")


def select_hair_mask(pack: dict, length: str, style: str, seed: str = "") -> dict | None:
    """Count-weighted pick of a whole-head L2 hair template for the length bucket."""
    bucket = "long" if length in ("long", "very_long") or style in (
        "long_straight", "long_wavy", "curly", "ponytail", "bun"
    ) else "short"
    items = (pack or {}).get("hair_masks", {}).get(bucket) or []
    if not items:
        return None
    total = sum(max(1, int(t.get("count", 1))) for t in items)
    pick = int.from_bytes(hashlib.sha256(f"mask:{bucket}:{style}:{seed}".encode()).digest()[:4], "big") % total
    for t in items:
        w = max(1, int(t.get("count", 1)))
        if pick < w:
            return t
        pick -= w
    return items[-1]
