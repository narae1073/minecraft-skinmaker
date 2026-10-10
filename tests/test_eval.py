"""eval: 렌더 정확성 지표 (네트워크 없음)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from skinmaker import eval as E
from skinmaker import quality as Q
from skinmaker.colors import extract


def photo():
    img = Image.new("RGB", (600, 800), (120, 100, 90))
    face = Q.FaceBox(200, 120, 160, 200)
    q = Q.Quality(0.95, face.area, 120.0, 400.0, 100.0, True)
    return Q.PhotoInput("t.jpg", img, face, q, ())


def test_evaluate_matches_on_synthetic():
    p = photo()
    row = E.evaluate(p, extract(p))
    assert not row.rejected
    assert row.valid and row.crown and row.cheek
    assert row.torso in ("match",) or row.torso.startswith("patterned:")


def test_evaluate_rejected_returns_early():
    img = Image.new("RGB", (100, 100), (0, 0, 0))
    p = Q.PhotoInput("x.jpg", img, None, None, ())
    row = E.evaluate(p, extract(p))
    assert row.rejected
    assert not row.valid


def test_report_counts_and_names_mismatch():
    rows = [E.EvalRow("a.jpg", rejected=True), E.EvalRow("b.jpg", valid=True, crown=True, cheek=True, torso="match")]
    text = E.report(rows)
    assert "전체 2" in text
    assert "거절 1" in text
