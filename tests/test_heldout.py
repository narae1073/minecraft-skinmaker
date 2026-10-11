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


# --- 감사 Fix 1: 내용 해시 무결성 -------------------------------------------
# audit 2026-10-11: 파일명만으로는 이름만 바꾼 중복이 통과한다 (false-negative).

import hashlib
import json


def test_sha256_file_deterministic(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"abc")
    assert H.sha256_file(f) == hashlib.sha256(b"abc").hexdigest()


def test_sha256_file_cache_hit_without_rereading(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"abc")
    st = f.stat()
    cache = tmp_path / "cache.json"
    cache.write_text(
        json.dumps({str(f.resolve()): {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": "sentinel"}}),
        encoding="utf-8",
    )
    assert H.sha256_file(f, cache_path=cache) == "sentinel"
    assert json.loads(cache.read_text(encoding="utf-8"))[str(f.resolve())]["sha256"] == "sentinel"


def test_sha256_file_recomputes_after_content_change(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"abcdef")
    cache = tmp_path / "cache.json"
    h1 = H.sha256_file(f, cache_path=cache)
    f.write_bytes(b"xyz")
    h2 = H.sha256_file(f, cache_path=cache)
    assert h2 != h1 and h2 == hashlib.sha256(b"xyz").hexdigest()


def test_labeled_hashes_resolves_only_existing_pool_files(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.jpg").write_bytes(b"A")
    (src / "b.jpg").write_bytes(b"B")
    got = H.labeled_photo_hashes(src, {"a.jpg", "missing.jpg"}, cache_path=tmp_path / "c.json")
    assert got == {"a.jpg": H.sha256_file(src / "a.jpg")}


def test_collect_rejects_duplicate_content(tmp_path):
    # 이름은 새것이지만 내용이 이미 라벨된 사진과 같다 -> duplicate_content.
    kept, excluded = H.collect(
        [("new.jpg", photo(250), "deadbeef"), ("other.jpg", photo(120), "cafebabe")],
        {},
        labeled_hashes={"deadbeef"},
    )
    assert [k["photo"] for k in kept] == ["other.jpg"]
    assert excluded == [{"photo": "new.jpg", "reason": "duplicate_content"}]


def test_build_candidates_hashes_files(tmp_path):
    from PIL import Image

    Image.new("RGB", (64, 64)).save(tmp_path / "p1.png")
    cands = H.build_candidates(tmp_path)
    assert len(cands) == 1
    name, _ph, sha = cands[0]
    assert name == "p1.png"
    assert sha == H.sha256_file(tmp_path / "p1.png")


# --- 감사 Fix 2: 라벨 파일 검증 ---------------------------------------------

def _bottom(path, labels, categories=("blue", "dark", "colored")):
    path.write_text(json.dumps({"labeler": "v1", "categories": list(categories), "labels": labels}), encoding="utf-8")


def test_validate_flags_key_overlap(tmp_path):
    bottom = tmp_path / "bottom.json"
    held = tmp_path / "held.json"
    _bottom(bottom, {"a.jpg": "blue", "b.jpg": "dark"})
    held.write_text(json.dumps({"labeler": "h", "categories": ["blue"], "labels": {"a.jpg": "blue", "c.jpg": "blue"}}), encoding="utf-8")
    problems = H.validate_heldout_labels(held, bottom)
    assert any("a.jpg" in p and "overlap_key" in p for p in problems), problems
    assert not any("b.jpg" in p for p in problems)


def test_validate_flags_missing_labels_key(tmp_path):
    bottom = tmp_path / "bottom.json"
    held = tmp_path / "held.json"
    _bottom(bottom, {"a.jpg": "blue"})
    held.write_text(json.dumps({"labeler": "h"}), encoding="utf-8")
    problems = H.validate_heldout_labels(held, bottom)
    assert problems and "labels" in problems[0]


def test_validate_flags_unknown_category(tmp_path):
    bottom = tmp_path / "bottom.json"
    held = tmp_path / "held.json"
    _bottom(bottom, {"a.jpg": "blue"})
    held.write_text(json.dumps({"labeler": "h", "categories": ["purple"], "labels": {"x.jpg": "purple"}}), encoding="utf-8")
    problems = H.validate_heldout_labels(held, bottom)
    assert any("x.jpg" in p for p in problems), problems


def test_validate_flags_duplicate_content_when_sources_given(tmp_path):
    src = tmp_path / "src"
    (src / "a.jpg").parent.mkdir(parents=True)
    (src / "a.jpg").write_bytes(b"same")
    hsrc = tmp_path / "hsrc"
    (hsrc / "c.jpg").parent.mkdir(parents=True)
    (hsrc / "c.jpg").write_bytes(b"same")
    bottom = tmp_path / "bottom.json"
    held = tmp_path / "held.json"
    _bottom(bottom, {"a.jpg": "blue"})
    held.write_text(json.dumps({"labeler": "h", "categories": ["blue"], "labels": {"c.jpg": "blue"}}), encoding="utf-8")
    problems = H.validate_heldout_labels(held, bottom, bottom_source=src, heldout_source=hsrc)
    assert any("c.jpg" in p and "overlap_content" in p for p in problems), problems


def test_validate_clean_passes(tmp_path):
    bottom = tmp_path / "bottom.json"
    held = tmp_path / "held.json"
    _bottom(bottom, {"a.jpg": "blue"})
    held.write_text(json.dumps({"labeler": "h", "categories": ["blue"], "labels": {"c.jpg": "blue"}}), encoding="utf-8")
    assert H.validate_heldout_labels(held, bottom) == []


def test_cli_validate_exit_nonzero_names_key(tmp_path, capsys):
    bottom = tmp_path / "bottom.json"
    held = tmp_path / "held.json"
    _bottom(bottom, {"a.jpg": "blue"})
    held.write_text(json.dumps({"labeler": "h", "categories": ["blue"], "labels": {"a.jpg": "blue"}}), encoding="utf-8")
    rc = H.main(["--validate", str(held), "--labels", str(bottom)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "a.jpg" in out


# --- 감사 Fix 3: 부족분 경고 + 장면 기록 -------------------------------------

def test_main_sampling_exits_nonzero_on_shortfall(tmp_path, monkeypatch, capsys):
    src = tmp_path / "src"
    src.mkdir()
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"labeler": "x", "categories": ["blue"], "labels": {}}), encoding="utf-8")
    manifest = tmp_path / "m.json"
    stub = [("a.jpg", photo(250), "aa")]
    monkeypatch.setattr(H, "build_candidates", lambda source, suffixes=None: stub)
    rc = H.main(["--source", str(src), "--labels", str(labels), "--n", "45", "--out", str(manifest), "--scene-note", "night city"])
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert rc == 1
    assert "WARNING" in capsys.readouterr().out
    assert len(data["selected"]) == 1
    assert data["lighting_scene_note"] == "night city"


def test_main_sampling_exits_zero_when_target_met(tmp_path, monkeypatch, capsys):
    src = tmp_path / "src"
    src.mkdir()
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"labeler": "x", "categories": ["blue"], "labels": {}}), encoding="utf-8")
    stub = [(f"p{i}.jpg", photo(250), f"{i:02x}") for i in range(3)]
    monkeypatch.setattr(H, "build_candidates", lambda source, suffixes=None: stub)
    rc = H.main(["--source", str(src), "--labels", str(labels), "--n", "1"])
    assert rc == 0
