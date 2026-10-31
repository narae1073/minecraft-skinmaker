"""Production reference benchmark split/QA contracts."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import copy, json
from skinmaker import reference_pack as RP
from skinmaker import reference_qa as QA


def _touch(tmp_path: Path, rel: str) -> None:
    p = tmp_path / "refs" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")


def test_split_is_deterministic_stratified_and_excludes_hats(tmp_path):
    for i in range(10):
        _touch(tmp_path, f"long_hair/{i}.png")
    for i in range(6):
        _touch(tmp_path, f"short_hair/{i}.png")
    for i in range(4):
        _touch(tmp_path, f"hood_up/long_hair/{i}.png")
        _touch(tmp_path, f"hood_up/short_hair/{i}.png")
    _touch(tmp_path, "hood_down/short_hair/0.png")
    _touch(tmp_path, "hat_or_cap/long_hair/0.png")
    m1 = QA.split_references(tmp_path / "refs", holdout_fraction=0.2, max_holdout=100, salt="t")
    m2 = QA.split_references(tmp_path / "refs", holdout_fraction=0.2, max_holdout=100, salt="t")
    assert m1 == m2
    assert set(m1["train"]).isdisjoint(m1["holdout"])
    assert not any("hat_or_cap" in p for p in m1["train"] + m1["holdout"])
    assert m1["holdout_count"] <= 100
    assert all(v["holdout"] >= 1 for v in m1["groups"].values())


def test_current_pack_structural_contract():
    pack = RP.load_pack()
    report = QA.qa_pack(pack, {"train": [], "holdout": []}, Path("out/reference_skins"))
    assert report["structural_ok"], report["structural_issues"]
    assert report["contamination"]


def test_pack_qa_detects_shape_errors():
    pack = {"hair": {"short": [{"faces": {"top": [[0] * 7]}}]}, "eyes": [], "hoods": {"up": [], "down": []}}
    report = QA.qa_pack(pack, {"train": [], "holdout": []}, Path("."))
    assert not report["structural_ok"]
    assert any("shape" in i for i in report["structural_issues"])
