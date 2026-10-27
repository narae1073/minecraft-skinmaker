"""QA render tool: camera contract + headless-Chrome smoke test (no display)."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from skinmaker import format as F
from skinmaker import qarender as QR


def test_view_specs_are_parallel_opposites():
    views = QR.view_specs(24.0, 30.0)
    assert [v["name"] for v in views] == ["front_right", "back_right"]
    assert views[0]["yaw"] == pytest.approx(24.0)
    assert views[1]["yaw"] == pytest.approx(204.0)
    assert views[0]["pitch"] == views[1]["pitch"] == pytest.approx(30.0)


def test_camera_positions_are_mirrored_across_y():
    front = QR.camera_position(24.0, 30.0, 24.0)
    back = QR.camera_position(204.0, 30.0, 24.0)
    assert front[1] == pytest.approx(back[1])  # same height -> parallel horizon
    assert front[0] == pytest.approx(-back[0])
    assert front[2] == pytest.approx(-back[2])
    assert front[0] > 0 and front[2] > 0  # +24 deg looks from the front-right


def test_find_browser_override(monkeypatch):
    monkeypatch.setenv("SKINMAKER_CHROME", "/bin/true")
    assert QR.find_browser() == "/bin/true"


def _synthetic_skin(path: Path) -> None:
    layout = F.get_layout("classic")
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))

    def paint(part, face, color, layer=0):
        rect = layout.face(part, face, layer)
        for y in range(rect.y, rect.y + rect.h):
            for x in range(rect.x, rect.x + rect.w):
                image.putpixel((x, y), color)

    for face in ("front", "back", "left", "right", "top", "bottom"):
        paint("head", face, (222, 172, 132, 255))
        paint("body", face, (90, 120, 190, 255))
        for part in ("r_arm", "l_arm"):
            paint(part, face, (222, 172, 132, 255))
        for part in ("r_leg", "l_leg"):
            paint(part, face, (45, 52, 70, 255))
    # L2 hair strands: a couple of opaque cells, the rest transparent.
    paint("head", "front", (30, 24, 20, 255), layer=1)
    image.save(path)


BROWSER = QR.find_browser()
NO_BROWSER = pytest.mark.skipif(BROWSER is None, reason="Chrome/Chromium not installed")
CI_SKIP = pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="browser smoke test is local-only (software WebGL on CI runners is flaky)",
)


@NO_BROWSER
@CI_SKIP
def test_render_views_writes_the_pair_and_metadata(tmp_path):
    skin = tmp_path / "skin.png"
    _synthetic_skin(skin)

    result = QR.render_views(skin, tmp_path / "qa", width=256, height=320, timeout=90)

    out = tmp_path / "qa"
    front, back = out / "front_right.png", out / "back_right.png"
    assert front.is_file() and back.is_file()
    assert Image.open(front).size == (256, 320)
    assert Image.open(back).size == (256, 320)
    assert front.read_bytes() != back.read_bytes()
    assert (out / "contact_sheet.png").is_file()

    metadata = json.loads((out / "render.json").read_text(encoding="utf-8"))
    assert metadata["views"][0]["yaw"] == pytest.approx(24.0)
    assert metadata["views"][1]["yaw"] == pytest.approx(204.0)
    assert metadata["model"] == "classic"
    assert metadata["skin"]["texture"]["l2_opaque"] > 0
    assert metadata["contact_sheet"] == "contact_sheet.png"
    assert result["views"][0]["path"] == "front_right.png"
