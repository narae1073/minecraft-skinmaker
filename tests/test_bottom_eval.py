"""bottom_eval 하네스 스모크 테스트. 네트워크·VLM 없이 실행된다.

rejected 사진(얼굴 없음)은 extract 없이 행 하나로 기록되고,
폴백 정책 비교는 synthetic 행으로 결정적으로 검증한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from skinmaker import bottom_eval as BE


def test_load_labels_reads_json(tmp_path):
    path = tmp_path / "labels.json"
    path.write_text('{"labels": {"a.jpg": "blue", "b.jpg": "none"}}', encoding="utf-8")
    assert BE.load_labels(path) == {"a.jpg": "blue", "b.jpg": "none"}


def test_evaluate_records_faceless_photo_as_rejected(tmp_path):
    src = tmp_path / "photos"
    src.mkdir()
    Image.new("RGB", (24, 24), (128, 128, 128)).save(src / "noface.png")
    rows = BE.evaluate({"noface.png": "blue"}, src)
    assert len(rows) == 1
    assert rows[0]["rejected"] is True
    assert rows[0]["label"] == "blue"


def test_policy_summary_gate_falls_back_implausible_rows():
    rows = [
        {
            "photo": "a.jpg",
            "label": "blue",
            "rejected": False,
            "on_hex": "#e0ac69",  # 피부색(맨다리 재측정): gate/기본값 경로
            "on_conf": False,
            "on_plausible": False,
            "on_rgb": (224, 172, 105),
        }
    ]
    gate = BE.policy_summary(rows, "gate")
    trust = BE.policy_summary(rows, "trust_measured")
    conf = BE.policy_summary(rows, "confident_only")
    # gate: 그럴듯하지 않으므로 기본값 #3c4450 → blue → 정답. trust_measured:
    # 피부색을 그대로 쓰므로 colored → 오답. confident_only: 미확신이라 기권아닌
    # 기본값 경로(usable=False) → 기본값 → 정답.
    assert gate["agree"] == 1 and gate["measured_used"] == 0
    assert conf["agree"] == 1 and conf["measured_used"] == 0
    assert trust["agree"] == 0 and trust["measured_used"] == 1


def test_policy_summary_keeps_confident_sample():
    rows = [
        {
            "photo": "b.jpg",
            "label": "blue",
            "rejected": False,
            "on_hex": "#374047",
            "on_conf": True,
            "on_plausible": False,
            "on_rgb": (55, 64, 71),
        }
    ]
    for name in ("gate", "confident_only", "trust_measured"):
        got = BE.policy_summary(rows, name)
        assert got["agree"] == 1 and got["measured_used"] == 1, name


def test_main_end_to_end(tmp_path, capsys):
    src = tmp_path / "photos"
    src.mkdir()
    Image.new("RGB", (24, 24), (128, 128, 128)).save(src / "noface.png")
    labels = tmp_path / "labels.json"
    labels.write_text('{"labels": {"noface.png": "blue"}}', encoding="utf-8")
    rc = BE.main(["--labels", str(labels), "--source", str(src)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "[mask on" in out and "[mask off" in out
    assert "render fallback policy" in out
