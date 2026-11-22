"""Generated-skin jobs: what is needed to re-render a skin with per-skin mask edits.

A job is stored under backend/private/ (never mounted): the observed colours and
hair stencil, each candidate's attributes and noise seed, and the owner's cookie
hash. Edits are a per-job mask overlay applied on top of the production masks, so
they never touch the shared assets. The owner is identified by a per-browser
secret sent as an HttpOnly cookie; the job keeps only its SHA-256.
"""
from __future__ import annotations

import dataclasses
import datetime
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
OWNER_COOKIE = "skinmaker_owner"
# Per-skin headwear choices. The hat shapes are drafts (not in the production asset).
HEADWEAR_CHOICES = ("none", "cap", "beanie")
# Clothing a user may change in the per-skin editor without re-running the VLM.
# Only values whose render path is attribute-driven (no per-photo masks) belong
# here; hair styles need their seeded stencils and stay out of v1.
ATTRIBUTE_CHOICES = {
    "top_garment": A.ENUMS["top_garment"],
    "bottom_garment": A.ENUMS["bottom_garment"],
    "sleeve_len": A.ENUMS["sleeve_len"],
    "hair_style": A.ENUMS["hair_style"],
    "hair_length": A.ENUMS["hair_length"],
    "inner_top": A.ENUMS["inner_top"],
    "closure_type": A.ENUMS["closure_type"],
    "collar_type": A.ENUMS["collar_type"],
    "pocket_type": A.ENUMS["pocket_type"],
    "neckwear": A.ENUMS["neckwear"],
    "beard": A.ENUMS["beard"],
    "hood": A.ENUMS["hood"],
    "hood_fit": A.ENUMS["hood_fit"],
}
MAX_ATTRIBUTE_CHANGES = len(ATTRIBUTE_CHOICES) + 1  # every editable field + headwear
# Per-candidate mask saves kept for the editor's revision menu. Each entry is a
# diff against the baseline, so ten snapshots stay small.
OVERLAY_HISTORY_MAX = 10
OVERLAY_HISTORY_MAX_BYTES = 2 * 1024 * 1024
HAT_DRAFT_PATHS = {
    "cap": ROOT.parent / "assets" / "headwear_cap.draft.json",
    "beanie": ROOT.parent / "assets" / "headwear_beanie.draft.json",
}
HAT_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
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
                  model: str, noise_level: float, degrade: tuple[str, ...]) -> dict:
    """Snapshot everything a candidate render needs. ``candidates`` are the
    skinmaker.candidates.Candidate objects from the generation run."""
    record = {
        "id": token,
        "owner_hash": owner,
        "model": model,
        "noise_level": noise_level,
        "degrade": list(degrade),
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


def candidate_attributes(record: dict, index: int) -> A.Attributes:
    """The candidate's attributes with this skin's own choices applied (e.g. headwear)."""
    cand = candidate(record, index)
    if cand is None:
        raise KeyError(index)
    attrs = JC.load_dataclass(cand["attributes"], A.Attributes)
    overrides = record.get("attr_overrides") or {}
    if not overrides:
        return attrs
    values = dict(attrs.values)
    values.update(overrides)
    return dataclasses.replace(attrs, values=values)


def photo_attributes(record: dict, index: int) -> A.Attributes:
    """The candidate's photo-derived attributes, ignoring this skin's overrides."""
    cand = candidate(record, index)
    if cand is None:
        raise KeyError(index)
    return JC.load_dataclass(cand["attributes"], A.Attributes)


def hat_draft_entry(value: str) -> dict:
    """A hat draft as a mask entry (L1 head faces)."""
    key = f"headwear.{value}"
    return json.loads(HAT_DRAFT_PATHS[value].read_text(encoding="utf-8"))["masks"][key]


def set_headwear(record: dict, value: str, color: str | None = None) -> dict:
    """Change this skin's headwear and, for a hat, its colour. Choosing a hat puts its
    draft into this skin's overlay (unless the user already has a mask for it)."""
    return set_attributes(record, {"headwear": value}, hat_color=color)


def set_attributes(record: dict, changes: dict, hat_color: str | None = None) -> dict:
    """Merge clothing/headwear choices into this skin's overrides.

    Only ``ATTRIBUTE_CHOICES`` and ``headwear`` are accepted, so a client cannot
    inject arbitrary renderer fields. Other overrides are kept (changing the top
    must not reset a chosen hat). Raising ``ValueError`` carries the bad key.
    """
    if not isinstance(changes, dict):
        raise ValueError("attributes")
    if len(changes) > MAX_ATTRIBUTE_CHANGES:
        raise ValueError("too many attributes")
    for name, value in changes.items():
        if name == "headwear":
            if value not in HEADWEAR_CHOICES:
                raise ValueError(name)
            continue
        choices = ATTRIBUTE_CHOICES.get(name)
        if choices is None or value not in choices:
            raise ValueError(name)
    if hat_color is not None and not HAT_COLOR_RE.match(hat_color):
        raise ValueError("hat_color")

    overrides = dict(record.get("attr_overrides") or {})
    overrides.update(changes)
    record["attr_overrides"] = {k: v for k, v in overrides.items() if v is not None}
    if hat_color is not None:
        record["hat_color"] = hat_color.lower()
    headwear = overrides.get("headwear")
    if headwear in HAT_DRAFT_PATHS:
        overlay = dict(record.get("overlay", {}))
        overlay.setdefault(f"headwear.{headwear}", _normalized(hat_draft_entry(headwear)))
        record["overlay"] = overlay
    return record


def reset_attributes(record: dict) -> dict:
    """Drop every per-skin attribute choice (headwear draft masks stay editable)."""
    record.pop("attr_overrides", None)
    record.pop("hat_color", None)
    return record


def render_candidate(record: dict, index: int, overlay: dict | None = None):
    """Render one candidate with the job's overlay on top of the production masks.
    Returns (image, flat_image, problems)."""
    cand = candidate(record, index)
    if cand is None:
        raise KeyError(index)
    observed = JC.load_dataclass(record["observed"], C.ObservedColors)
    attrs = candidate_attributes(record, index)
    masks = dict(AM.load_masks())
    masks.update(effective_overlay(record, index) if overlay is None else overlay)
    degrade = tuple(record.get("degrade") or ())
    # A skin whose headwear was chosen by the user draws the hat over the hair.
    # Clothing overrides must not change that ordering.
    headwear = (record.get("attr_overrides") or {}).get("headwear")
    hat_on_top = headwear in HAT_DRAFT_PATHS
    common = dict(noise_seed=cand["seed"], noise_level=record["noise_level"], mask_override=masks,
                  hat_on_top=hat_on_top, hat_color=record.get("hat_color"))
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
    attrs = candidate_attributes(record, index)
    base = dict(attrs.values, hair_bbox=attrs.hair_bbox, hood="none")
    return AS.SeedContext(observed=observed, base=base)


def _normalized(entry: dict) -> dict:
    return AS._normalize_key(entry)


def baseline_masks(record: dict, index: int) -> dict:
    """What the editor starts from for this job: production entries where they exist,
    else the job's procedural seed. Cached per (job, candidate)."""
    key = (record["id"], index, json.dumps(record.get("attr_overrides") or {}, sort_keys=True))
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


def candidate_indices(record: dict) -> list[int]:
    return [c["index"] for c in record.get("candidates") or []]


def effective_overlay(record: dict, index: int) -> dict:
    """Shared overlay (hat drafts, legacy edits) plus this candidate's own edits."""
    shared = record.get("overlay") or {}
    own = (record.get("overlays") or {}).get(str(index)) or {}
    if not shared:
        return dict(own)
    out = dict(shared)
    out.update(own)
    return out


def effective_masks(record: dict, index: int) -> dict:
    """Baseline with this job's overlay on top: what the editor shows and renders."""
    base = baseline_masks(record, index)
    out = dict(base)
    for name, entry in effective_overlay(record, index).items():
        out[name] = _normalized(entry)
    return out


def overlay_history(record: dict, index: int) -> list[dict]:
    """Saved revisions for one candidate, newest first (metadata only)."""
    entries = (record.get("overlay_history") or {}).get(str(index)) or []
    return [{"revision": e["revision"], "saved_at": e.get("saved_at", ""),
             "changed": len(e.get("overlay") or {})}
            for e in reversed(entries)]


def save_candidate_overlay(record: dict, index: int, overlay: dict) -> int:
    """Store one candidate's overlay, bump the revision and keep a history entry."""
    overlays = dict(record.get("overlays") or {})
    overlays[str(index)] = overlay
    record["overlays"] = overlays
    revision = int(record.get("revision", 0)) + 1
    record["revision"] = revision
    history = dict(record.get("overlay_history") or {})
    entries = list(history.get(str(index)) or [])
    entries.append({
        "revision": revision,
        "overlay": overlay,
        "saved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    })
    del entries[:-OVERLAY_HISTORY_MAX]
    while len(entries) > 1 and len(json.dumps(entries)) > OVERLAY_HISTORY_MAX_BYTES:
        entries.pop(0)
    history[str(index)] = entries
    record["overlay_history"] = history
    return revision


def restore_candidate_overlay(record: dict, index: int, revision: int) -> int:
    """Restore a saved candidate overlay as a new revision (keeps the old history)."""
    entries = (record.get("overlay_history") or {}).get(str(index)) or []
    for entry in entries:
        if int(entry.get("revision", -1)) == int(revision):
            return save_candidate_overlay(record, index, dict(entry.get("overlay") or {}))
    raise KeyError(revision)


def override_names(record: dict, index: int) -> list[str]:
    """Masks in this candidate that differ from its baseline (shared or own)."""
    base = baseline_masks(record, index)
    current = effective_masks(record, index)
    return sorted(name for name, entry in current.items()
                  if name not in base or entry != base[name])


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
    attrs = candidate_attributes(record, index)
    from skinmaker.format import get_layout
    layout = get_layout("classic")
    return {
        "parts": list(AS.PARTS), "part_faces": {p: list(f) for p, f in AS.PART_FACES.items()},
        "faces": AS.FACES, "dims": {k: list(v) for k, v in AS.DIMS.items()}, "layers": AS.LAYERS,
        "enums": {name: list(A.ENUMS[name]) for name in A.FIELD_ORDER},
        "defaults": dict(attrs.values), "combo": {name: attrs.get(name) for name in A.FIELD_ORDER},
        "photo_combo": {name: photo_attributes(record, index).get(name) for name in A.FIELD_ORDER},
        "attribute_overrides": dict(record.get("attr_overrides") or {}),
        "models": [record["model"]],
        "atlas": {"size": 64, "rects": _rects(layout)},
        "slim": {"sub_faces": sorted(AS.SLIM_FACES),
                 "dims": {f: list(d) for f, d in AS.SLIM_FACES.items()},
                 "atlas": {"size": 64, "rects": AS._slim_rects()}},
        "maskable": AS.MASKABLE,
        "masks": effective_masks(record, index),
        "candidate": {"index": index, "varied": cand["varied"]},
        "candidates": candidate_indices(record),
        "index": index,
        "override_names": override_names(record, index),
        "history": overlay_history(record, index),
        "hat_color": record.get("hat_color"),
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
