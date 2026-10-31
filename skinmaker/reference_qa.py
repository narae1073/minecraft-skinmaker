"""Deterministic reference benchmark split + pack structural QA.

Important: the 600+ references are unpaired skins, not photo→skin examples.
Holdout metrics here measure template/style coverage, not photo→skin likeness.
A separate paired benchmark is required for production acceptance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from . import reference_pack as RP

REF_GROUPS = ("long_hair", "short_hair", "hood_up", "hood_down")
EXCLUDED = ("hat_or_cap",)


def _group(rel: Path) -> str | None:
    parts = rel.parts
    if parts and parts[0] in EXCLUDED:
        return None
    if parts and parts[0] in ("long_hair", "short_hair"):
        return parts[0]
    if len(parts) >= 3 and parts[0] in ("hood_up", "hood_down"):
        return f"{parts[0]}/{parts[1]}"
    return None


def split_references(root: Path, holdout_fraction: float = 0.15,
                     max_holdout: int = 100, salt: str = "production-v1") -> dict:
    """Deterministic stratified split; hat/cap is excluded from the benchmark."""
    root = Path(root)
    files = sorted(p for p in root.rglob("*.png"))
    by_group: dict[str, list[Path]] = {}
    for p in files:
        rel = p.relative_to(root)
        g = _group(rel)
        if g is None:
            continue
        by_group.setdefault(g, []).append(rel)

    holdout: list[str] = []
    train: list[str] = []
    counts: dict[str, dict[str, int]] = {}
    for group in sorted(by_group):
        rels = sorted(by_group[group], key=lambda r: hashlib.sha256(
            f"{salt}|{r.as_posix()}".encode()).hexdigest())
        n = max(1, round(len(rels) * holdout_fraction))
        n = min(n, max(1, len(rels) - 1))
        holdout.extend(r.as_posix() for r in rels[:n])
        train.extend(r.as_posix() for r in rels[n:])
        counts[group] = {"total": len(rels), "holdout": n, "train": len(rels) - n}

    # Cap total holdout; drop the last hashed item from the largest groups.
    held = set(holdout)
    while len(held) > max_holdout:
        group = max(counts, key=lambda g: counts[g]["holdout"])
        candidate = sorted((h for h in held if _group(Path(h)) == group))[-1]
        held.remove(candidate)
        counts[group]["holdout"] -= 1
        counts[group]["train"] += 1
    holdout = sorted(held)
    manifest = {
        "version": 1,
        "salt": salt,
        "holdout_fraction": holdout_fraction,
        "source_count": len(files),
        "benchmark_count": len(holdout) + len(train),
        "holdout_count": len(holdout),
        "train_count": len(train),
        "excluded": list(EXCLUDED),
        "groups": counts,
        "train": sorted(train),
        "holdout": holdout,
        "note": "Unpaired skins: this benchmark measures style/template coverage, not photo→skin likeness.",
    }
    return manifest


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).mean())


def _nearest(feature: np.ndarray, patterns: list[np.ndarray]) -> float | None:
    if not patterns:
        return None
    return min(_dist(feature, p) for p in patterns)


def qa_pack(pack: dict, manifest: dict, root: Path) -> dict:
    """Structural validation + holdout style-coverage baseline."""
    issues: list[str] = []
    for length in ("short", "long"):
        for p in pack.get("hair", {}).get(length, []):
            faces = p.get("faces", {})
            if set(faces) != set(RP.HEAD_FACES):
                issues.append(f"hair {p.get('id')}: missing faces")
            for f in RP.HEAD_FACES:
                a = np.asarray(faces.get(f, []), dtype=float)
                if a.shape != (8, 8):
                    issues.append(f"hair {p.get('id')}: {f} shape {a.shape}")
    for p in pack.get("eyes", []):
        for key in ("sclera", "iris"):
            a = np.asarray(p.get(key, []), dtype=float)
            if a.shape != (2, 8):
                issues.append(f"eye {p.get('id')}: {key} shape {a.shape}")
    for kind in ("up", "down"):
        for p in pack.get("hoods", {}).get(kind, []):
            for face, rows in p.get("faces", {}).items():
                a = np.asarray(rows)
                if a.ndim != 2 or a.shape[1] != 8:
                    issues.append(f"hood {kind} {p.get('id')}: {face} shape {a.shape}")

    train_refs = [root / r for r in manifest["train"]]
    holdout_refs = [root / r for r in manifest["holdout"]]
    def safe_features(items, kind):
        out = []
        for p in items:
            try:
                out.append(RP._feature(p, kind))
            except (KeyError, ValueError):
                pass
        return out

    patterns = {
        "short": safe_features(pack.get("hair", {}).get("short", []), "hair"),
        "long": safe_features(pack.get("hair", {}).get("long", []), "hair"),
        "eyes": safe_features(pack.get("eyes", []), "eye"),
        "hood_up": safe_features(pack.get("hoods", {}).get("up", []), "hood"),
        "hood_down": safe_features(pack.get("hoods", {}).get("down", []), "hood"),
    }
    cover = {"hair": [], "eyes": [], "hood_up": [], "hood_down": []}
    for path in holdout_refs:
        try:
            image = RP._rgba(path)
        except OSError:
            continue
        parts = path.relative_to(root).parts
        length = "long" if parts[0].startswith("long") or (len(parts) > 1 and parts[1] == "long_hair") else "short"
        hp = RP.extract_hair_pattern(image)
        if hp and patterns[length]:
            cover["hair"].append(_nearest(RP._feature(hp, "hair"), patterns[length]))
        ep = RP.extract_eye_pattern(image)
        if ep and patterns["eyes"]:
            cover["eyes"].append(_nearest(RP._feature(ep, "eye"), patterns["eyes"]))
        if parts[0] == "hood_up":
            hood = RP.extract_hood_up(image)
            if hood and patterns["hood_up"]:
                cover["hood_up"].append(_nearest(RP._feature(hood, "hood"), patterns["hood_up"]))
        elif parts[0] == "hood_down":
            hood = RP.extract_hood_down(image)
            if hood and patterns["hood_down"]:
                cover["hood_down"].append(_nearest(RP._feature(hood, "hood"), patterns["hood_down"]))

    summary = {}
    for kind, values in cover.items():
        vals = [v for v in values if v is not None]
        summary[kind] = {
            "n": len(vals),
            "mean_distance": round(float(np.mean(vals)), 4) if vals else None,
            "p90_distance": round(float(np.percentile(vals, 90)), 4) if vals else None,
        }
    training = pack.get("training")
    return {
        "version": 1,
        "structural_issues": issues,
        "structural_ok": not issues,
        "coverage": summary,
        "training": training,
        "contamination": None if training else "Pack has no training-split metadata; it may include holdout references.",
        "paired_benchmark": "Not present. A photo→skin pair set is required before claiming production quality.",
        "train_refs": len(train_refs),
        "holdout_refs": len(holdout_refs),
    }


def write_report(root: Path, out_dir: Path, holdout_fraction: float = 0.15,
                 max_holdout: int = 100) -> dict:
    root = Path(root)
    manifest = split_references(root, holdout_fraction, max_holdout)
    pack = RP.load_pack()
    report = qa_pack(pack or {}, manifest, root)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "split.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {"manifest": manifest, "report": report}
