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


def test_parse_hair_box():
    assert E.parse_hair_box("150,0,100,60") == Q.FaceBox(150, 0, 100, 60)


def test_parse_hair_box_rejects_garbage():
    import pytest

    for bad in ("a,b,c,d", "1,2,3", "1,2,3,4,5", "10,10,-5,20"):
        with pytest.raises(ValueError):
            E.parse_hair_box(bad)


def _bbox_photo():
    img = Image.new("RGB", (400, 500), (30, 30, 30))
    px = img.load()
    for y in range(0, 60):
        for x in range(150, 250):
            px[x, y] = (150, 90, 40)
    for y in range(171, 207):
        for x in range(170, 230):
            px[x, y] = (204, 161, 141)  # WB 앵커
    face = Q.FaceBox(150, 100, 100, 130)
    q = Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True)
    return Q.PhotoInput("t.jpg", img, face, q, ())


def test_eval_accepts_fixed_hair_box():
    # 모자가 bbox에 들어오면 모자색이 머리가 되는 것은 알려진 한계로 둔다.
    # 여기서 고정하는 것은 결정성(같은 박스→같은 crown)과 파이프 무결성이다.
    box = Q.FaceBox(150, 0, 100, 60)
    rows = [E.evaluate(_bbox_photo(), extract(_bbox_photo(), hair_bbox=box)) for _ in range(2)]
    assert all(r.valid for r in rows)
    assert all(r.crown for r in rows)
    assert rows[0].fell_back == rows[1].fell_back
    assert "hair" not in rows[0].fell_back


def test_eval_main_accepts_hair_box_flag(tmp_path):
    blank = tmp_path / "blank.png"
    Image.new("RGB", (200, 200), (30, 60, 90)).save(blank)
    assert E.main([str(blank), "--hair-box", "10,10,50,50"]) == 0
