"""Aggregate fail-closed production gate (v4 attribute masks, 2026-11-02)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MASK_ASSET = ROOT / "assets" / "attribute_masks.json"
MASK_APPROVAL = ROOT / "assets" / "attribute_masks_approval.json"
RENDER_POLICY = "attribute-masks-2026-11-02"

TARGETS = {
    "holdout_min": 50, "holdout_max": 100,
    "hair_n_min": 50, "hair_p90_max": 0.10,
    "approved_pairs_target": 30, "approved_pairs_min": 1,
    "approved_eyes_min": 3,
}


def _load(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ""


def _mask_status(mask_asset: Path, mask_approval: Path, policy: str) -> tuple[bool, str, str]:
    if not Path(mask_asset).is_file():
        return False, "missing attribute mask asset", ""
    sha = _sha256(mask_asset)
    approval = _load(mask_approval, {}) or {}
    if not approval.get("approved"):
        return False, "approved attribute masks missing", sha
    if approval.get("sha256") != sha:
        return False, "attribute mask approval stale (hash mismatch)", sha
    if approval.get("policy") != policy:
        return False, "attribute mask approval policy mismatch", sha
    return True, "", sha


def build_status(bench_root: Path = Path("out/production_benchmark"),
                 paired_root: Path = Path("out/paired_benchmark"),
                 qa_path: Path = Path("out/production_qa/report.json"),
                 mask_asset: Path = MASK_ASSET,
                 mask_approval: Path = MASK_APPROVAL,
                 policy: str = RENDER_POLICY) -> dict:
    split = _load(bench_root / "split.json", {})
    report = _load(bench_root / "report.json", {})
    approvals = _load(bench_root / "template_approvals.json", {})
    paired = _load(paired_root / "report.json", {})
    baseline = _load(paired_root / "benchmark_baseline.json", {})
    qa = _load(qa_path, {})
    cov = report.get("coverage", {}) if report else {}

    def approved(kind):
        return sum(1 for v in approvals.get(kind, {}).values() if v.get("approved"))

    blockers: list[str] = []
    if not split:
        blockers.append("missing benchmark split")
    else:
        h = split.get("holdout_count", 0)
        if not (TARGETS["holdout_min"] <= h <= TARGETS["holdout_max"]):
            blockers.append(f"holdout {h} outside {TARGETS['holdout_min']}-{TARGETS['holdout_max']}")
    if not report:
        blockers.append("missing pack report")
    else:
        if not report.get("structural_ok"):
            blockers.append("structural pack QA failed")
        if not report.get("quality_ok"):
            blockers.append("template quality QA failed")
        if not report.get("training"):
            blockers.append("pack has no train-split provenance")
        hair = cov.get("hair", {})
        if hair.get("n", 0) < TARGETS["hair_n_min"] or (hair.get("p90_distance") or 1) > TARGETS["hair_p90_max"]:
            blockers.append("hair holdout coverage below target")
        # v3: hood holdout coverage is reported but not gated — the hood is
        # driven by assets/hood_masks.json, not by pack hood templates.
    if not qa or not qa.get("ok"):
        blockers.append("deterministic production QA matrix failed/missing")

    mask_ok, mask_msg, mask_sha = _mask_status(mask_asset, mask_approval, policy)
    if not mask_ok:
        blockers.append(mask_msg)

    n = approved("eyes")
    if n < TARGETS["approved_eyes_min"]:
        blockers.append(f"approved eyes templates {n} < {TARGETS['approved_eyes_min']}")

    if not paired:
        blockers.append("missing paired benchmark report")
    else:
        a = paired.get("approved_count", 0)
        if a < TARGETS["approved_pairs_min"]:
            blockers.append("no approved paired photo→skin examples")
        elif not paired.get("accepted"):
            blockers.append("approved paired benchmark has structural problems")
        if a < TARGETS["approved_pairs_target"]:
            blockers.append(f"approved pairs {a}/{TARGETS['approved_pairs_target']}")
    if not baseline:
        blockers.append("paired benchmark baseline missing (regenerate/re-approve)")
    elif baseline.get("mask_sha") != mask_sha or baseline.get("policy") != policy:
        blockers.append("paired benchmark stale (mask/render policy changed)")

    return {
        "version": 4,
        "ready": not blockers,
        "targets": TARGETS,
        "policy": {
            "eyes": "user-accepted, data-limited; holdout n is reported but not gated",
            "hood": "mask-driven (assets/attribute_masks.json + human approval); pack hood coverage is reported but not gated",
            "paired": "must carry benchmark_baseline.json with the current mask SHA and render policy",
        },
        "blockers": blockers,
        "approved": {
            "pairs": paired.get("approved_count", 0) if paired else 0,
            "eyes": approved("eyes"),
            "hood_masks": mask_ok,
        },
        "coverage": cov,
        "mask_sha": mask_sha,
        "note": "Gate v3 (2026-11-02) fails closed; a changed attribute-mask/render policy invalidates the paired baseline.",
    }
