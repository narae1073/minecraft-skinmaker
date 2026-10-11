"""heldout.py 스모크 테스트. 순수 헬퍼만 검증한다 (YuNet·inspect 미사용).

검출 판정은 detect 콜러블 주입으로 떼어냈으므로 테스트는 모델 코드에
의존하지 않는다. 목적: 라벨 제외·프레이밍 밴드·결정적 균등 샘플링.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from skinmaker import eval as E
from skinmaker import heldout as H
from skinmaker import quality as Q


def photo(face_h: int, img_h: int = 1000):
    face = Q.FaceBox(10, 10, 20, face_h)
    return Q.PhotoInput(
        "t.jpg", Image.new("RGB", (40, img_h)), face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ()
    )


def test_framing_band_matches_eval_cuts():
    # duplicate-definition 방지: eval.report_band 과 정확히 같은 분할이어야 한다.
    for fh, ih in ((99, 1001), (100, 1001), (199, 1001), (200, 1000), (41, 200), (40, 200)):
        ratio = fh / ih
        assert H.framing_band(ratio) == E.report_band(photo(fh, ih)), ratio


def test_evenly_spaced_picks_linspace_indices():
    items = [f"p{i}" for i in range(10)]
    assert H.evenly_spaced(items, 4) == ["p0", "p3", "p6", "p9"]


def test_evenly_spaced_single_returns_first():
    assert H.evenly_spaced(["a", "b"], 1) == ["a"]


def test_evenly_spaced_short_returns_all():
    assert H.evenly_spaced(["a", "b", "c"], 5) == ["a", "b", "c"]


def test_band_budget_proportional_largest_remainder():
    got = H.band_budget({"full": 9, "mid": 30, "portrait": 6}, 7)
    assert got == {"full": 1, "mid": 5, "portrait": 1}


def test_band_budget_never_exceeds_available():
    got = H.band_budget({"full": 1, "mid": 1, "portrait": 1}, 6)
    assert got == {"full": 1, "mid": 1, "portrait": 1}


def test_collect_excludes_labeled_and_rejected():
    kept_photo = photo(250)  # 0.25 -> portrait
    rejected = Q.PhotoInput("r.jpg", Image.new("RGB", (10, 10)), None, None, ())
    candidates = [("keep.jpg", kept_photo), ("labeled.jpg", photo(60)), ("rejected.jpg", rejected)]
    labels = {"labeled.jpg": "blue"}
    kept, excluded = H.collect(candidates, labels)
    assert [k["photo"] for k in kept] == ["keep.jpg"]
    assert kept[0]["band"] == "portrait"
    assert kept[0]["face_h_over_img_h"] == 0.25
    reasons = {e["photo"]: e["reason"] for e in excluded}
    assert reasons == {"labeled.jpg": "already_labeled", "rejected.jpg": "no_face"}


def test_select_deterministic_within_band():
    kept = [{"photo": f"p{i}", "band": "full", "face_h_over_img_h": 0.05 + i / 1000} for i in range(4)]
    kept += [{"photo": f"m{i}", "band": "mid", "face_h_over_img_h": 0.12 + i / 1000} for i in range(2)]
    picked = H.select(kept, 2)
    # 예산은 비례+최대나머지: {full:1.33 -> 1, mid:0.67 -> 0+1} -> full 1, mid 1.
    assert [p["photo"] for p in picked] == ["p0", "m0"]
