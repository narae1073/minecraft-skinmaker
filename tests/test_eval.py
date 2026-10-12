"""eval: 렌더 정확성 지표 (네트워크 없음)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PIL import Image

from skinmaker import eval as E
from skinmaker import quality as Q
from skinmaker.colors import ColorSample, ObservedColors, extract

FLAG_PHOTO = Path(__file__).resolve().parent.parent / "out" / "s0_photos" / "7f18cb16d51f6228b635d23c18772c05.jpg"


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


def test_report_breaks_down_by_framing():
    text = E.report([
        E.EvalRow("a.jpg", valid=True, crown=True, cheek=True, torso="match"),
    ])
    assert "full" in text and "mid" in text and "portrait" in text


def test_report_fallback_per_framing_band():
    rows = [
        E.EvalRow("f.jpg", valid=True, crown=True, cheek=True, torso="match",
                  framing="full", fell_back=("hair",)),
        E.EvalRow("m.jpg", valid=True, crown=True, cheek=True, torso="match",
                  framing="mid", fell_back=("hair", "bottom")),
        E.EvalRow("p.jpg", valid=True, crown=True, cheek=True, torso="match",
                  framing="portrait", fell_back=()),
    ]
    text = E.report(rows)
    assert "full: n=1" in text and "hair=1/1" in text
    assert "mid: n=1" in text and "bottom=1/1" in text
    assert "portrait: n=1" in text and "hair=0/1" in text


def _ratio_photo(face_h, img_h=1000, img_w=1000):
    img = Image.new("RGB", (img_w, img_h), (120, 100, 90))
    face = Q.FaceBox(100, 100, 100, face_h)
    q = Q.Quality(0.95, face.area, 120.0, 400.0, 100.0, True)
    return Q.PhotoInput("t.jpg", img, face, q, ())


def test_report_band_matches_fixed10_cuts():
    # 고정 세트 실측 양끝값: full 최대 0.0989 / mid 최소 0.1000 / portrait 최소 0.2059.
    assert E.report_band(_ratio_photo(98)) == "full"
    assert E.report_band(_ratio_photo(99)) == "full"
    assert E.report_band(_ratio_photo(100)) == "mid"  # 0.10 경계는 mid
    assert E.report_band(_ratio_photo(190)) == "mid"
    assert E.report_band(_ratio_photo(199)) == "mid"
    assert E.report_band(_ratio_photo(200)) == "portrait"  # 0.20 경계는 portrait
    assert E.report_band(_ratio_photo(206)) == "portrait"
    noface = Q.PhotoInput("x.jpg", Image.new("RGB", (100, 100)), None, None, ())
    assert E.report_band(noface) == "-"


def test_evaluate_records_ratio_band():
    p = photo()  # 600x800, face h=200 → 0.25 → portrait
    row = E.evaluate(p, extract(p))
    assert row.framing == "portrait"


def test_hair_box_help_states_plumbing_only():
    assert "배선" in E.HAIR_BOX_HELP
    assert "VLM" in E.HAIR_BOX_HELP


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


@pytest.mark.skipif(not FLAG_PHOTO.exists(), reason="픽스처 없음(out/ 미포함 클론)")
def test_eval_main_accepts_hair_box_flag(monkeypatch):
    # faceless synthetic 이미지로는 photo.rejected 조기 반환이라 --hair-box 배선을
    # 검증 못 한다. 실측 얼굴 사진 + extract 스파이로 bbox 도착을 고정한다.
    photo_path = FLAG_PHOTO
    seen = {}
    orig_extract = E.extract

    def spy(photo, *args, **kwargs):
        seen["hair_bbox"] = kwargs.get("hair_bbox", args[0] if args else None)
        return orig_extract(photo, *args, **kwargs)

    monkeypatch.setattr(E, "extract", spy)
    assert E.main([str(photo_path), "--hair-box", "239,46,30,45"]) == 0
    assert seen.get("hair_bbox") == Q.FaceBox(239, 46, 30, 45)


def test_eval_main_skips_extract_failure_and_continues(tmp_path, monkeypatch, capsys):
    for name, color in (("a.png", (30, 60, 90)), ("b.png", (60, 90, 30))):
        Image.new("RGB", (200, 200), color).save(tmp_path / name)
    orig_extract = E.extract

    def flaky(photo, *args, **kwargs):
        if photo.path.endswith("a.png"):
            raise RuntimeError("boom")
        return orig_extract(photo, *args, **kwargs)

    monkeypatch.setattr(E, "extract", flaky)
    assert E.main([str(tmp_path), "--hair-box", "10,10,50,50"]) == 0
    assert "SKIP a.png" in capsys.readouterr().out


# --- 노이즈 시드 경로 + 프로브 톨러런스 (설계 §3, 2026-10-12) ----------------

def sample_n(hex_value, share=0.5, confident=True, n=100):
    r = int(hex_value[1:3], 16)
    g = int(hex_value[3:5], 16)
    b = int(hex_value[5:7], 16)
    return ColorSample(hex_value, share, confident, (r, g, b), n)


def make_noise_observed(skin="#e0ac69", hair="#3a2a1c", top="#2f6fb5", bottom="#3c4450"):
    return ObservedColors(
        sample_n(skin), sample_n(hair), sample_n(top), sample_n(bottom),
        (1.0, 1.0, 1.0), True, (0.5, 0.3, 0.2),
    )


def test_evaluate_pipeline_noise_probes_pass():
    row = E.evaluate(photo(), make_noise_observed())
    assert row.valid is True
    assert row.crown is True
    assert row.cheek is True
    assert row.torso == "match"


def test_probe_tolerance_catches_material_swap():
    obs = make_noise_observed()
    hair_top = E.expected_pixel(obs, "hair", "top")
    skin_front = E.expected_pixel(obs, "skin", "front")
    assert not E.probe_equal(hair_top, skin_front)
    from skinmaker.canvas import shade
    from skinmaker.render import NOISE_STEPS

    for k in NOISE_STEPS:
        assert E.probe_equal(hair_top, shade(hair_top, k)), k
