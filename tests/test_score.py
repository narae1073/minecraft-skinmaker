"""Similarity scoring: parse/clamp, ranking, resume (fake transport)."""
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skinmaker import score as S


class FakeTransport:
    name = "fake"
    model = "fake-model"

    def __init__(self, values=None, fail=False):
        self.values = values or {"head": 5, "top": 5, "bottom": 5, "overall": 5, "issues": ["x"]}
        self.fail = fail
        self.calls = 0
        self.last_error = None

    def available(self):
        return True, "fake"

    def complete(self, image, prompt, schema):
        self.calls += 1
        assert set(schema["properties"]) >= {"head", "top", "bottom", "overall"}
        assert "side-by-side" in prompt
        return None if self.fail else dict(self.values)


def _fixture(tmp_path, sources, values=None):
    batch = tmp_path / "batch"
    renders = tmp_path / "renders"
    for source in sources:
        dest = batch / source
        dest.mkdir(parents=True)
        (dest / "result.json").write_text(json.dumps({
            "status": "ok",
            "source": source,
            "classification": {"values": {"pattern": "plain", "top_garment": "tee", "bottom_garment": "jeans"}},
        }), encoding="utf-8")
        rdir = renders / source
        rdir.mkdir(parents=True)
        Image.new("RGB", (12, 8), (200, 200, 200)).save(rdir / "compare.png")
    return batch, renders


def test_parse_scores_clamps_and_requires_all():
    got = S.parse_scores({"head": 12, "top": 0, "bottom": 7.4, "overall": 5, "issues": ["a", "b", "c", "d"]})
    assert got["head"] == 10 and got["top"] == 1 and got["bottom"] == 7
    assert got["mean"] == pytest.approx(5.75)
    assert len(got["issues"]) == 3
    assert S.parse_scores({"head": 5}) is None
    assert S.parse_scores(None) is None


def test_run_scoring_writes_worst_first_ranking(tmp_path):
    batch, renders = _fixture(tmp_path, ["a.jpg", "b.jpg", "c.jpg"])
    fake = FakeTransport({"head": 4, "top": 3, "bottom": 2, "overall": 3, "issues": ["top wrong"]})
    out = tmp_path / "scores.json"
    report = S.run_scoring(batch, renders, out, transport=fake)
    assert report["scored"] == 3 and report["errors"] == 0
    assert (out).is_file()
    assert report["ranking"] == ["a.jpg", "b.jpg", "c.jpg"]
    assert report["scores"][0]["mean"] == pytest.approx(3.0)
    assert fake.calls == 3


def test_resume_skips_cached_sources(tmp_path):
    batch, renders = _fixture(tmp_path, ["a.jpg", "b.jpg"])
    fake = FakeTransport()
    out = tmp_path / "scores.json"
    S.run_scoring(batch, renders, out, transport=fake)
    calls = fake.calls
    S.run_scoring(batch, renders, out, transport=fake)
    assert fake.calls == calls  # second run: all cached
    S.run_scoring(batch, renders, out, transport=fake, force=True)
    assert fake.calls == calls + 2


def test_repeat_uses_median(tmp_path):
    batch, renders = _fixture(tmp_path, ["a.jpg"])

    class Sequence(FakeTransport):
        def __init__(self):
            super().__init__()
            self.seq = [
                {"head": 2, "top": 2, "bottom": 2, "overall": 2},
                {"head": 8, "top": 8, "bottom": 8, "overall": 8},
                {"head": 9, "top": 9, "bottom": 9, "overall": 9},
            ]

        def complete(self, image, prompt, schema):
            return self.seq.pop(0)

    report = S.run_scoring(batch, renders, tmp_path / "s.json", transport=Sequence(), repeat=3)
    row = report["scores"][0]
    assert row["head"] == 8 and row["mean"] == pytest.approx(8.0)


def test_transport_failure_is_recorded(tmp_path):
    batch, renders = _fixture(tmp_path, ["a.jpg"])
    report = S.run_scoring(batch, renders, tmp_path / "s.json", transport=FakeTransport(fail=True))
    assert report["errors"] == 1
    assert report["scores"][0]["status"] == "error"
