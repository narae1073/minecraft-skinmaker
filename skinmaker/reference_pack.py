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


def extract_hood_up(image: Image.Image) -> dict | None:
    """L2 head coverage for an up hood; five faces."""
    faces: dict[str, list[list[int]]] = {}
    coverage = 0
    for name in HEAD_FACES:
        l2 = _face_array(image, "head", name, 1)
        mask = (l2[..., 3] > 0).astype(np.uint8)
        coverage += int(mask.sum())
        faces[name] = mask.tolist()
    if coverage < 24:
        return None
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
               k_hood_down: int = 2) -> dict:
    """Build a derived pack from out/reference_skins."""
    root = Path(root)
    hair: dict[str, list[dict]] = {"short": [], "long": []}
    eyes: list[dict] = []
    seen_eyes: set[tuple] = set()

    for length in ("short", "long"):
        for path in sorted((root / f"{length}_hair").glob("*.png")):
            image = _rgba(path)
            hp = extract_hair_pattern(image)
            if hp:
                hp["source"] = path.name
                hair[length].append(hp)
            ep = extract_eye_pattern(image)
            if ep:
                key = (tuple(map(tuple, ep["sclera"])), tuple(map(tuple, ep["iris"])))
                if key not in seen_eyes:
                    seen_eyes.add(key)
                    ep["source"] = path.name
                    eyes.append(ep)

    hood_up = []
    for path in sorted((root / "hood_up").rglob("*.png")):
        hp = extract_hood_up(_rgba(path))
        if hp:
            hp["source"] = path.name
            hood_up.append(hp)
    hood_down = []
    for path in sorted((root / "hood_down").rglob("*.png")):
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
        "eyes": _medoids(eyes, "eye", k_eyes),
        "hoods": {
            "up": _medoids(hood_up, "hood", k_hood_up),
            "down": _medoids(hood_down, "hood", k_hood_down),
        },
    }
    for patterns in (pack["hair"]["short"], pack["hair"]["long"], pack["eyes"],
                     pack["hoods"]["up"], pack["hoods"]["down"]):
        for p in patterns:
            # Keep provenance hashes, not file paths in the renderer-facing pack.
            p["id"] = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()[:12]
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


def select_eyes(pack: dict, seed: str = "") -> dict | None:
    return _pick(pack.get("eyes", []), f"eyes:{seed}")


def select_hood(pack: dict, kind: str, seed: str = "") -> dict | None:
    return _pick(pack.get("hoods", {}).get(kind, []), f"hood:{kind}:{seed}")
