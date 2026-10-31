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
    collapsed = {str(i): {"depth": 5, "exposure": "covered"} for i in range(19)}
    collapsed["19"] = {"depth": 2, "exposure": "partial"}
    q = label_quality(collapsed, cands)
    assert not q["usable"]
    varied = {}
    for i in range(20):
        varied[str(i)] = {"depth": i % 6, "exposure": ("covered", "partial", "exposed")[i % 3]}
    q2 = label_quality(varied, cands)
    assert q2["usable"], q2
