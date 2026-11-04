"""Generated-skin jobs: what is needed to re-render a skin with per-skin mask edits.

A job is stored under backend/private/ (never mounted): the observed colours and
hair stencil, each candidate's attributes and noise seed, and the owner's cookie
hash. Edits are a per-job mask overlay applied on top of the production masks, so
they never touch the shared assets. The owner is identified by a per-browser
secret sent as an HttpOnly cookie; the job keeps only its SHA-256.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
from pathlib import Path

from skinmaker import attribute_masks as AM
from skinmaker import attribute_seeds as AS
from skinmaker import attributes as A
from skinmaker import colors as C
from skinmaker import job_codec as JC
from skinmaker import render as R

ROOT = Path(__file__).resolve().parent
PRIVATE_DIR = ROOT / "private"
JOBS_DIR = PRIVATE_DIR / "jobs"
INPUTS_DIR = PRIVATE_DIR / "inputs"
OWNER_COOKIE = "skinmaker_owner"
OVERLAY_MAX_BYTES = 512 * 1024   # stored overlay (only differing entries)
EDITOR_BODY_MAX_BYTES = 4 * 1024 * 1024  # a full effective-mask payload from the editor
TOKEN_RE = re.compile(r"^[0-9a-f]{12}$")


def new_owner_secret() -> str:
    return secrets.token_urlsafe(24)


def owner_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def owner_secret_from_request(request) -> str | None:
    value = request.cookies.get(OWNER_COOKIE)
    return value or None


def is_owner(record: dict, request) -> bool:
    secret = owner_secret_from_request(request)
    if not secret or not record.get("owner_hash"):
        return False
    return hmac.compare_digest(owner_hash(secret), record["owner_hash"])


def valid_token(token: str) -> bool:
    return bool(TOKEN_RE.match(token or ""))


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def save_record(record: dict) -> None:
    _atomic_write_json(JOBS_DIR / f"{record['id']}.json", record)


def load_record(token: str) -> dict | None:
    if not valid_token(token):
        return None
    try:
        return json.loads((JOBS_DIR / f"{token}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def create_record(token: str, owner: str, observed: C.ObservedColors, candidates, *,
                  model: str, noise_level: float, degrade: tuple[str, ...], input_name: str) -> dict:
    """Snapshot everything a candidate render needs. ``candidates`` are the
    skinmaker.candidates.Candidate objects from the generation run."""
    record = {
        "id": token,
        "owner_hash": owner,
        "model": model,
        "noise_level": noise_level,
        "degrade": list(degrade),
        "input": input_name,
        "observed": JC.dump_dataclass(observed),
        "candidates": [
            {"index": c.index, "varied": c.varied, "seed": c.noise_seed,
             "attributes": JC.dump_dataclass(c.attributes)}
            for c in candidates
        ],
        "overlay": {},
        "revision": 0,
    }
    save_record(record)
    return record


def validate_overlay(masks) -> list[str]:
    return validate_masks(masks, OVERLAY_MAX_BYTES)


def validate_masks(masks, limit: int) -> list[str]:
    """Mask entries must be known mask keys with well-formed 0/1 grids."""
    if not isinstance(masks, dict):
        return ["masks must be an object"]
    if len(json.dumps(masks)) > limit:
        return ["masks too large"]
    errors = AM.validate_asset({"masks": masks})
    for key in masks:
        if AM._split_key(key) is None:
            errors.append(f"unknown mask key: {key!r}")
    return errors


def candidate(record: dict, index: int) -> dict | None:
    for c in record["candidates"]:
        if c["index"] == index:
            return c
    return None


def render_candidate(record: dict, index: int, overlay: dict | None = None):
    """Render one candidate with the job's overlay on top of the production masks.
    Returns (image, flat_image, problems)."""
    cand = candidate(record, index)
    if cand is None:
        raise KeyError(index)
    observed = JC.load_dataclass(record["observed"], C.ObservedColors)
    attrs = JC.load_dataclass(cand["attributes"], A.Attributes)
    masks = dict(AM.load_masks())
    masks.update(record.get("overlay", {}) if overlay is None else overlay)
    degrade = tuple(record.get("degrade") or ())
    common = dict(noise_seed=cand["seed"], noise_level=record["noise_level"], mask_override=masks)
    canvas = R.render(observed, attrs, degrade, record["model"], **common)
    flat = R.render(observed, attrs, degrade, record["model"], shoe_two_tone=False, **common)
    from skinmaker.validate import validate_image
    problems = [str(p) for img in (canvas.image, flat.image) for p in validate_image(img, record["model"])]
    return canvas.image, flat.image, problems


# ---- per-skin editor -----------------------------------------------------------

_BASELINE_CACHE: dict[tuple[str, int], dict] = {}
_BASELINE_CACHE_MAX = 64


def seed_context(record: dict, index: int) -> AS.SeedContext:
    """Seeds for this job and candidate: the job's own observed colours and attributes."""
    cand = candidate(record, index)
    if cand is None:
        raise KeyError(index)
    observed = JC.load_dataclass(record["observed"], C.ObservedColors)
    attrs = JC.load_dataclass(cand["attributes"], A.Attributes)
    base = dict(attrs.values, hair_bbox=attrs.hair_bbox, hood="none")
    return AS.SeedContext(observed=observed, base=base)


def _normalized(entry: dict) -> dict:
    return AS._normalize_key(entry)


def baseline_masks(record: dict, index: int) -> dict:
    """What the editor starts from for this job: production entries where they exist,
    else the job's procedural seed. Cached per (job, candidate)."""
    key = (record["id"], index)
    if key in _BASELINE_CACHE:
        return _BASELINE_CACHE[key]
    with AS.using(seed_context(record, index)):
        seeds = AS.seed_masks()
    production = AM.load_masks()
    merged = {}
    for name, seeded in seeds.items():
        merged[name] = _normalized(production[name]) if name in production else seeded
    if len(_BASELINE_CACHE) >= _BASELINE_CACHE_MAX:
        _BASELINE_CACHE.clear()
    _BASELINE_CACHE[key] = merged
    return merged


def effective_masks(record: dict, index: int) -> dict:
    """Baseline with this job's overlay on top: what the editor shows and renders."""
    base = baseline_masks(record, index)
    out = dict(base)
    for name, entry in record.get("overlay", {}).items():
        out[name] = _normalized(entry)
    return out


def diff_against_baseline(masks: dict, record: dict, index: int) -> dict:
    """Store only the entries the user changed; unchanged entries stay procedural."""
    base = baseline_masks(record, index)
    changed = {}
    for name, entry in masks.items():
        norm = _normalized(entry)
        if name not in base or norm != base[name]:
            changed[name] = norm
    return changed


def editor_payload(record: dict, index: int) -> dict:
    cand = candidate(record, index)
    attrs = JC.load_dataclass(cand["attributes"], A.Attributes)
    from skinmaker.format import get_layout
    layout = get_layout("classic")
    return {
        "parts": list(AS.PARTS), "part_faces": {p: list(f) for p, f in AS.PART_FACES.items()},
        "faces": AS.FACES, "dims": {k: list(v) for k, v in AS.DIMS.items()}, "layers": AS.LAYERS,
        "enums": {name: list(A.ENUMS[name]) for name in A.FIELD_ORDER},
        "defaults": dict(attrs.values), "combo": {name: attrs.get(name) for name in A.FIELD_ORDER},
        "models": [record["model"]],
        "atlas": {"size": 64, "rects": _rects(layout)},
        "slim": {"sub_faces": sorted(AS.SLIM_FACES),
                 "dims": {f: list(d) for f, d in AS.SLIM_FACES.items()},
                 "atlas": {"size": 64, "rects": AS._slim_rects()}},
        "maskable": AS.MASKABLE,
        "masks": effective_masks(record, index),
        "candidate": {"index": index, "varied": cand["varied"]},
        "revision": record["revision"],
    }


def _rects(layout) -> dict:
    rects = {}
    for layer, idx in (("L1", 0), ("L2", 1)):
        rects[layer] = {}
        for face in AS.FACES:
            part, short = face.split(".", 1)
            rects[layer][face] = list(layout.face(part, short, idx).rect)
    return rects


def preview_png(record: dict, index: int, masks: dict) -> tuple[bytes, list[str]]:
    """Preview = the render that Save + render would produce: the editor's full masks
    are converted to the overlay they differ by, then rendered the same way. PNG bytes,
    nothing written."""
    import io
    overlay = diff_against_baseline(masks, record, index)
    image, _flat, problems = render_candidate(record, index, overlay)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue(), problems
