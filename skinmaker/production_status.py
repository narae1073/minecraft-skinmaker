"""Aggregate fail-closed production gate from benchmark/approval reports."""
from __future__ import annotations

import json
from pathlib import Path

TARGETS = {
    "holdout_min": 50, "holdout_max": 100,
    "hair_n_min": 50, "hair_p90_max": 0.10,
    # v2 (2026-11-02): eyes are user-accepted / data-limited (no n gate);
    # hood_up target follows the corpus ceiling (3 full-crown holdout);
    # hood_down keeps n>=5 and adds a coverage-distance gate.
    "hood_up_n_min": 3, "hood_down_n_min": 5, "hood_down_p90_max": 0.25,
    "approved_pairs_target": 30, "approved_pairs_min": 1,
    "approved_eyes_min": 3, "approved_hood_up_min": 2, "approved_hood_down_min": 1,
}


def _load(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def build_status(bench_root: Path = Path("out/production_benchmark"),
                 paired_root: Path = Path("out/paired_benchmark"),
                 qa_path: Path = Path("out/production_qa/report.json")) -> dict:
    split = _load(bench_root / "split.json", {})
    report = _load(bench_root / "report.json", {})
    approvals = _load(bench_root / "template_approvals.json", {})
    paired = _load(paired_root / "report.json", {})
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
        up = cov.get("hood_up", {})
        if up.get("n", 0) < TARGETS["hood_up_n_min"]:
            blockers.append(f"hood_up holdout n below {TARGETS['hood_up_n_min']}")
        down = cov.get("hood_down", {})
        if down.get("n", 0) < TARGETS["hood_down_n_min"]:
            blockers.append(f"hood_down holdout n below {TARGETS['hood_down_n_min']}")
        elif down.get("p90_distance") is None or down["p90_distance"] > TARGETS["hood_down_p90_max"]:
            blockers.append(
                f"hood_down coverage p90 {down.get('p90_distance')} > {TARGETS['hood_down_p90_max']}"
            )
    if not qa or not qa.get("ok"):
        blockers.append("deterministic production QA matrix failed/missing")
    for kind, key in (("eyes", "approved_eyes_min"), ("hood_up", "approved_hood_up_min"),
                      ("hood_down", "approved_hood_down_min")):
        n = approved(kind)
        if n < TARGETS[key]:
            blockers.append(f"approved {kind} templates {n} < {TARGETS[key]}")
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
    return {
        "version": 2,
        "ready": not blockers,
        "targets": TARGETS,
        "policy": {
            "eyes": "user-accepted, data-limited; holdout n is reported but not gated",
            "hood_up": "n>=3 (corpus ceiling: 3 full-crown holdout)",
            "hood_down": "n>=5 and p90<=0.25",
        },
        "blockers": blockers,
        "approved": {
            "pairs": paired.get("approved_count", 0) if paired else 0,
            "eyes": approved("eyes"), "hood_up": approved("hood_up"),
            "hood_down": approved("hood_down"),
        },
        "coverage": cov,
        "note": "Gate v2 (2026-11-02) fails closed; style coverage alone is not production approval.",
    }
