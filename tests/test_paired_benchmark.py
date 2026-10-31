from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image
from skinmaker.paired_benchmark import check_pairs


def _skin(path: Path) -> None:
    from test_render import observed, attrs
    from skinmaker import render as R
    R.render(observed(), attrs(), ()).image.save(path)


def test_paired_benchmark_requires_approved_pairs(tmp_path):
    root = tmp_path / "pairs" / "p1"
    root.mkdir(parents=True)
    Image.new("RGB", (128, 128), (100, 100, 100)).save(root / "photo.jpg")
    _skin(root / "skin.png")
    (root / "meta.json").write_text(json.dumps({"approved": False}), encoding="utf-8")
    r = check_pairs(tmp_path)
    assert r["pair_count"] == 1 and r["approved_count"] == 0 and not r["accepted"]

    (root / "meta.json").write_text(json.dumps({"approved": True}), encoding="utf-8")
    r = check_pairs(tmp_path)
    assert r["approved_count"] == 1 and r["accepted"]


def test_paired_benchmark_reports_missing_files(tmp_path):
    (tmp_path / "pairs" / "broken").mkdir(parents=True)
    r = check_pairs(tmp_path)
    assert r["pair_count"] == 1
    assert any("missing" in p for p in r["structural"][0]["problems"])
