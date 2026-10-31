from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker.production_qa import run_matrix


def test_production_matrix_passes_current_contract():
    r = run_matrix(styles=(("short", "short"), ("long_straight", "long")),
                   hoods=("none", "up", "down"), noise_levels=(0.0, 0.5))
    assert r["ok"], r["failures"]
    assert r["case_count"] == 12 + 1


def test_production_matrix_reports_beard_case():
    r = run_matrix(styles=(("short", "short"),), hoods=("none",), noise_levels=(0.0,))
    # The explicit beard case is appended; the normal short case must pass.
    assert r["ok"], r["failures"]
