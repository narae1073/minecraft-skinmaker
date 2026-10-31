from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image
from skinmaker.paired_benchmark import check_pairs, set_approval


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


def test_set_approval_requires_pair_and_updates_meta(tmp_path):
    import pytest
    root = tmp_path / "pairs" / "p1"; root.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        set_approval(tmp_path, "missing", True)
    _skin(root / "skin.png")
    Image.new("RGB", (128, 128), (100, 100, 100)).save(root / "photo.jpg")
    (root / "meta.json").write_text("{}", encoding="utf-8")
    set_approval(tmp_path, "p1", True, "looks good")
    meta = json.loads((root / "meta.json").read_text())
    assert meta["approved"] is True and meta["notes"] == "looks good"
    set_approval(tmp_path, "p1", False)
    assert json.loads((root / "meta.json").read_text())["approved"] is False


def test_template_review_approval_and_eye_candidate(tmp_path):
    from skinmaker import template_review as TR
    from skinmaker.format import get_layout
    from PIL import Image
    L = get_layout("classic")
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    f = L.face("head", "front", 0)
    for v in range(8):
        for u in range(8):
            im.putpixel((f.x + u, f.y + v), (224, 172, 105, 255))
    for v in (4, 5):
        for u in (1, 5):
            im.putpixel((f.x + u, f.y + v), (245, 245, 245, 255))
        for u in (2, 6):
            im.putpixel((f.x + u, f.y + v), (40, 70, 140, 255))
    c = TR.extract_eye_candidate(im)
    assert c and c["sclera_px"] >= 2 and c["iris_px"] >= 2
    p = tmp_path / "approvals.json"
    TR.set_approval(p, "eyes", c["id"], True, "ok")
    assert TR.load_approvals(p)["eyes"][c["id"]]["approved"] is True


def test_eye_candidate_ranking_is_not_approval():
    from skinmaker.template_review import eye_score
    c = {"sclera": [[0, 1, 1, 0, 0, 1, 1, 0] for _ in range(2)],
         "iris": [[0, 0, 1, 0, 0, 1, 0, 0] for _ in range(2)]}
    s = eye_score(c)
    assert s["both_eyes"] and s["sclera_iris_adjacent"]
    assert s["score"] >= 5
