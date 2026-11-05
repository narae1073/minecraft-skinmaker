"""Runs the 2D atlas helper unit tests (tools/mask_editor/atlas.test.mjs)."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_atlas_helpers_pass_node_unit_tests():
    result = subprocess.run(
        [NODE, "--test", str(ROOT / "tools" / "mask_editor" / "atlas.test.mjs")],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
