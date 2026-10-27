"""Batch runner: discovery, resume, manifest/selection contract (no network)."""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from skinmaker import batch as B

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_discover_recursive_and_photo_list(tmp_path):
    root = tmp_path / "photos"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir()
    for rel in ("a/one.jpg", "a/two.png", "b/three.webp", "skip.txt"):
        (root / rel).write_bytes(b"x")
    got = [p.relative_to(root).as_posix() for p in B.discover(root)]
    assert got == ["a/one.jpg", "a/two.png", "b/three.webp"]

    listing = tmp_path / "list.txt"
    listing.write_text("a/one.jpg\n# comment\nb/three.webp\n", encoding="utf-8")
    picked = [p.relative_to(root).as_posix() for p in B.discover(root, listing)]
    assert picked == ["a/one.jpg", "b/three.webp"]

    listing.write_text("a/one.jpg\nmissing.jpg\n", encoding="utf-8")
    try:
        B.discover(root, listing)
    except FileNotFoundError as exc:
        assert "missing.jpg" in str(exc)
    else:
        raise AssertionError("missing entry must raise")


def test_relative_key_preserves_nested_paths(tmp_path):
    root = tmp_path / "photos"
    nested = root / "skirt" / "image400.webp"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"x")
    assert B.relative_key(root, nested) == "skirt/image400.webp"


def test_run_batch_smoke_resume_manifest_selection(tmp_path):
    """실제 목 파이프라인 1장: JSON/스킨 + 재실행 skip + manifest/selection."""
    root = tmp_path / "photos"
    root.mkdir()
    shutil.copy(FIXTURES / "ex6(half).png", root / "ex6(half).png")
    out = tmp_path / "out"

    manifest = B.run_batch(root, out, transport_name="mock", max_side=512, sleep=0)
    assert manifest["count"] == 1
    assert manifest["status_counts"] == {"ok": 1}
    row = manifest["photos"][0]
    assert row["source"] == "ex6(half).png"
    assert row["status"] == "ok"
    assert row["primary_skin"] in row["skins"]
    assert (out / "ex6(half).png" / "result.json").is_file()
    assert (out / "ex6(half).png" / row["primary_skin"]).is_file()
    for key in ("classification", "observed", "resolved_bottom", "bottom_source", "summary"):
        assert key in row, key

    selection = json.loads((out / "qa_selection.json").read_text(encoding="utf-8"))
    assert selection["photos"] == ["ex6(half).png"]
    assert set(selection["groups"]) == {
        "dress", "skirt", "upper_body_fallback", "measured_pants", "bare_legs"}

    # 재실행: 완료된 사진은 skip (result.json mtime 불변)
    before = (out / "ex6(half).png" / "result.json").stat().st_mtime_ns
    B.run_batch(root, out, transport_name="mock", max_side=512, sleep=0)
    after = (out / "ex6(half).png" / "result.json").stat().st_mtime_ns
    assert before == after


def test_build_selection_groups(tmp_path):
    out = tmp_path / "out"
    rows = {
        "dress": {"status": "ok", "source": "d.jpg", "classification": {"values": {"top_garment": "dress", "bottom_garment": "none"}}, "resolved_bottom": "dress", "bottom_source": "dress"},
        "skirt": {"status": "ok", "source": "s.jpg", "classification": {"values": {"top_garment": "tee", "bottom_garment": "skirt"}}, "resolved_bottom": "skirt", "bottom_source": "skirt"},
        "upper": {"status": "ok", "source": "u.jpg", "classification": {"values": {"top_garment": "tee", "bottom_garment": "none"}}, "resolved_bottom": "jeans", "bottom_source": "default_jeans"},
        "pants": {"status": "ok", "source": "p.jpg", "classification": {"values": {"top_garment": "tee", "bottom_garment": "none"}}, "resolved_bottom": "pants", "bottom_source": "measured"},
        "bare": {"status": "ok", "source": "b.jpg", "classification": {"values": {"top_garment": "tee", "bottom_garment": "none"}}, "resolved_bottom": "none", "observed": {"lower_body_bare": True}},
        "bad": {"status": "error", "source": "x.jpg"},
    }
    for key, row in rows.items():
        dest = out / key
        dest.mkdir(parents=True)
        (dest / "result.json").write_text(json.dumps(row), encoding="utf-8")
    sel = B.build_selection(out)
    assert sel["groups"]["dress"] == ["d.jpg"]
    assert sel["groups"]["skirt"] == ["s.jpg"]
    assert sel["groups"]["upper_body_fallback"] == ["u.jpg"]
    assert sel["groups"]["measured_pants"] == ["p.jpg"]
    assert sel["groups"]["bare_legs"] == ["b.jpg"]
    assert "x.jpg" not in sel["photos"]


def test_replay_reprocesses_from_stored_json(tmp_path):
    root = tmp_path / "photos"
    root.mkdir()
    shutil.copy(FIXTURES / "ex6(half).png", root / "ex6(half).png")
    out = tmp_path / "out"
    B.run_batch(root, out, transport_name="mock", max_side=512, sleep=0)
    manifest = B.run_batch(root, out, transport_name="mock", max_side=512, sleep=0, replay=True)
    row = manifest["photos"][0]
    assert row["status"] == "ok"
    assert row["transport"] == "replay"
