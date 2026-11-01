from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker.bang_benchmark import load_labels, set_label, summarize


def test_bang_labels_and_summary(tmp_path):
    p = tmp_path / "labels.json"
    set_label(p, "a", 5, "covered")
    set_label(p, "b", 3, "exposed")
    labels = load_labels(p)
    cands = [{"id": "a", "length": "long"}, {"id": "b", "length": "short"}]
    s = summarize(labels, cands)["by_length"]
    assert s["long"]["median_depth"] == 5
    assert s["long"]["exposure"]["covered"] == 1
    assert s["short"]["exposure"]["exposed"] == 1
    try:
        set_label(p, "c", 9, "covered")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid depth accepted")


def test_collapsed_labels_are_rejected():
    from skinmaker.bang_benchmark import label_quality
    cands = [{"id": str(i), "length": "long"} for i in range(20)]
    collapsed = {str(i): {"depth": 5, "exposure": "covered"} for i in range(20)}
    q = label_quality(collapsed, cands)
    assert not q["usable"]
    varied = {}
    for i in range(20):
        depth = (3, 4, 5, 6)[i % 4]
        exposure = "covered" if depth >= 5 else ("partial" if depth == 4 else "exposed")
        varied[str(i)] = {"depth": depth, "exposure": exposure}
    q2 = label_quality(varied, cands)
    assert q2["usable"], q2


def test_skewed_long_bang_prior_is_usable():
    from skinmaker.bang_benchmark import label_quality
    cands = [{"id": str(i), "length": "long"} for i in range(60)]
    labels = {}
    for i in range(60):
        if i < 25:
            labels[str(i)] = {"depth": 5, "exposure": "partial"}
        elif i < 45:
            labels[str(i)] = {"depth": 5, "exposure": "covered"}
        elif i < 54:
            labels[str(i)] = {"depth": 5, "exposure": "exposed"}
        elif i < 57:
            labels[str(i)] = {"depth": 6, "exposure": "covered"}
        elif i < 58:
            labels[str(i)] = {"depth": 4, "exposure": "partial"}
        else:
            labels[str(i)] = {"depth": 3, "exposure": "exposed"}
    q = label_quality(labels, cands)
    assert q["usable"], q
    assert q["dominant_share"] >= 0.85


def test_committed_bang_prior_records_dominant_depth():
    import json
    prior = json.loads(Path("assets/bang_prior.json").read_text())
    assert prior["by_length"]["long"]["median_depth"] == 5
    assert prior["by_length"]["short"]["median_depth"] == 5
    assert prior["quality"]["usable"]
