from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker.production_status import build_status


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(obj), encoding="utf-8")


def test_gate_fails_closed_without_approvals(tmp_path):
    bench, paired = tmp_path / "bench", tmp_path / "paired"
    _write(bench / "split.json", {"holdout_count": 98})
    _write(bench / "report.json", {"structural_ok": True, "quality_ok": True, "training": {"salt": "x"},
        "coverage": {"hair": {"n": 98, "p90_distance": 0.08}, "eyes": {"n": 3}, "hood_up": {"n": 3}, "hood_down": {"n": 0}}})
    _write(bench / "template_approvals.json", {})
    _write(paired / "report.json", {"approved_count": 0, "accepted": False})
    _write(tmp_path / "qa.json", {"ok": True})
    s = build_status(bench, paired, tmp_path / "qa.json")
    assert not s["ready"]
    assert any("approved paired" in b for b in s["blockers"])
    assert any("approved eyes" in b for b in s["blockers"])


def test_gate_can_pass_with_complete_reports(tmp_path):
    bench, paired = tmp_path / "bench", tmp_path / "paired"
    _write(bench / "split.json", {"holdout_count": 98})
    _write(bench / "report.json", {"structural_ok": True, "quality_ok": True, "training": {"salt": "x"},
        "coverage": {"hair": {"n": 98, "p90_distance": 0.08}, "eyes": {"n": 20}, "hood_up": {"n": 10}, "hood_down": {"n": 5}}})
    _write(bench / "template_approvals.json", {"eyes": {str(i): {"approved": True} for i in range(3)},
        "hood_up": {str(i): {"approved": True} for i in range(2)}, "hood_down": {"1": {"approved": True}}})
    _write(paired / "report.json", {"approved_count": 30, "accepted": True})
    _write(tmp_path / "qa.json", {"ok": True})
    s = build_status(bench, paired, tmp_path / "qa.json")
    assert s["ready"], s["blockers"]
