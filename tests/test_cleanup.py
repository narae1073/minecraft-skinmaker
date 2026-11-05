"""Legacy photo-artifact purge (bash script; Linux/macOS only)."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "purge_photo_artifacts.sh"

pytestmark = pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="bash script (Linux/macOS only)",
)


def test_purge_removes_photo_artifacts_and_keeps_skins(tmp_path):
    skins = tmp_path / "backend" / "static" / "skins"
    steps = tmp_path / "backend" / "static" / "steps"
    inputs = tmp_path / "backend" / "private" / "inputs"
    for d in (skins, steps, inputs):
        d.mkdir(parents=True)
    (skins / "input_abc.jpg").write_bytes(b"photo")
    (skins / "abc_c1.png").write_bytes(b"skin")
    (steps / "abc_steps.png").write_bytes(b"sheet")
    (inputs / "abc.jpg").write_bytes(b"photo")

    r = subprocess.run(
        ["bash", str(SCRIPT), "--root", str(tmp_path), "--yes"],
        capture_output=True, text=True,
    )

    assert r.returncode == 0, r.stderr
    assert not (skins / "input_abc.jpg").exists()
    assert (skins / "abc_c1.png").exists()
    assert not any(steps.iterdir())
    assert not any(inputs.iterdir())


def test_purge_refuses_without_yes(tmp_path):
    skins = tmp_path / "backend" / "static" / "skins"
    skins.mkdir(parents=True)
    (skins / "input_abc.jpg").write_bytes(b"photo")

    r = subprocess.run(
        ["bash", str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True, text=True,
    )

    assert r.returncode == 2
    assert (skins / "input_abc.jpg").exists()
