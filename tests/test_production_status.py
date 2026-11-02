from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker.production_status import RENDER_POLICY, build_status


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _mask(tmp_path: Path):
    asset = tmp_path / "hood_masks.json"
    asset.write_text('{"version": 1}', encoding="utf-8")
    sha = hashlib.sha256(asset.read_bytes()).hexdigest()
    approval = tmp_path / "hood_masks_approval.json"
    _write(approval, {"approved": True, "sha256": sha, "policy": RENDER_POLICY})
    return asset, approval, sha


def _reports(tmp_path: Path, *, approved: int = 30, accepted: bool = True,
             eye_approvals: int = 3, baseline: bool = True,
             baseline_sha: str | None = None, baseline_policy: str = RENDER_POLICY,
             coverage: dict | None = None):
    bench, paired = tmp_path / "bench", tmp_path / "paired"
    _write(bench / "split.json", {"holdout_count": 98})
    _write(bench / "report.json", {
        "structural_ok": True, "quality_ok": True, "training": {"salt": "x"},
        "coverage": coverage or {"hair": {"n": 98, "p90_distance": 0.08}},
    })
    _write(bench / "template_approvals.json", {
        "eyes": {str(i): {"approved": True} for i in range(eye_approvals)},
    })
    _write(paired / "report.json", {"approved_count": approved, "accepted": accepted})
    qa = tmp_path / "qa.json"
    _write(qa, {"ok": True})
    if baseline:
        sha = baseline_sha or "0" * 64
        _write(paired / "benchmark_baseline.json", {"mask_sha": sha, "policy": baseline_policy})
    return bench, paired, qa


def test_gate_fails_closed_without_approvals(tmp_path):
    asset, approval, sha = _mask(tmp_path)
    bench, paired, qa = _reports(tmp_path, approved=0, accepted=False, eye_approvals=0, baseline=False)
    s = build_status(bench, paired, qa, mask_asset=asset, mask_approval=approval)
    assert not s["ready"]
    assert any("approved paired" in b for b in s["blockers"])
    assert any("approved eyes" in b for b in s["blockers"])
    assert any("baseline missing" in b for b in s["blockers"])


def test_gate_can_pass_with_mask_approval_and_baseline(tmp_path):
    asset, approval, sha = _mask(tmp_path)
    coverage = {"hair": {"n": 98, "p90_distance": 0.08}, "eyes": {"n": 1},
                "hood_up": {"n": 0}, "hood_down": {"n": 0, "p90_distance": 0.40}}
    bench, paired, qa = _reports(tmp_path, baseline_sha=sha, coverage=coverage)
    s = build_status(bench, paired, qa, mask_asset=asset, mask_approval=approval)
    assert s["ready"], s["blockers"]  # hood coverage is reported, not gated


def test_gate_v3_blocks_stale_paired_baseline(tmp_path):
    asset, approval, sha = _mask(tmp_path)
    bench, paired, qa = _reports(tmp_path, baseline_sha=sha)
    _write(paired / "benchmark_baseline.json", {"mask_sha": "f" * 64, "policy": RENDER_POLICY})
    s = build_status(bench, paired, qa, mask_asset=asset, mask_approval=approval)
    assert any("paired benchmark stale" in b for b in s["blockers"])

    _write(paired / "benchmark_baseline.json", {"mask_sha": sha, "policy": RENDER_POLICY})
    s = build_status(bench, paired, qa, mask_asset=asset, mask_approval=approval)
    assert s["ready"], s["blockers"]


def test_gate_v3_blocks_mask_hash_mismatch(tmp_path):
    asset, approval, sha = _mask(tmp_path)
    _write(approval, {"approved": True, "sha256": "f" * 64, "policy": RENDER_POLICY})
    bench, paired, qa = _reports(tmp_path, baseline_sha=sha)
    s = build_status(bench, paired, qa, mask_asset=asset, mask_approval=approval)
    assert any("hood mask approval stale" in b for b in s["blockers"])
