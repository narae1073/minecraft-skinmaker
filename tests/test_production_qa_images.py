"""The QA report also renders a pass/fail contact sheet for humans."""
from __future__ import annotations

from skinmaker.production_qa import render_contact_sheet


def test_contact_sheet_renders_pass_and_fail(tmp_path):
    cases = [
        {"style": "short", "length": "short", "hood": "none", "noise": 0.0, "problems": []},
        {"style": "long_straight", "length": "long", "hood": "up", "noise": 0.0,
         "problems": ["hood-up back hair at (0,0)"]},
    ]
    path = render_contact_sheet(cases, tmp_path / "sheet.png", "qa test")
    assert path.exists() and path.stat().st_size > 0
    from PIL import Image
    with Image.open(path) as im:
        assert im.width > 0 and im.height > 0
