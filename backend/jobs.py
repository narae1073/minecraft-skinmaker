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
from skinmaker import attributes as A
from skinmaker import colors as C
from skinmaker import job_codec as JC
from skinmaker import render as R

ROOT = Path(__file__).resolve().parent
PRIVATE_DIR = ROOT / "private"
JOBS_DIR = PRIVATE_DIR / "jobs"
INPUTS_DIR = PRIVATE_DIR / "inputs"
OWNER_COOKIE = "skinmaker_owner"
OVERLAY_MAX_BYTES = 512 * 1024
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
    """Overlay entries must be known mask keys with well-formed 0/1 grids."""
    if not isinstance(masks, dict):
        return ["masks must be an object"]
    if len(json.dumps(masks)) > OVERLAY_MAX_BYTES:
        return ["overlay too large"]
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
