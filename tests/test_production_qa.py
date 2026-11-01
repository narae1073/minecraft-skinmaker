from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker import production_qa as Q
from skinmaker import render as R
from skinmaker.canvas import rgba, shade
from skinmaker.production_qa import run_matrix


def test_every_hood_template_passes_render_invariants(monkeypatch):
    """Roadmap item 4: the 49-case matrix exercises one seeded template per
    style. Force each pack hood template and run the same invariant check at
    noise 0 and 50%."""
    pack = R.RP.load_pack()
    # Pinned counts: update deliberately when the pack is rebuilt, so new
    # variants are reviewed instead of silently gaining coverage.
    assert len(pack["hoods"]["up"]) == 4
    assert len(pack["hoods"]["down"]) == 2
    for hood in ("up", "down"):
        for template in pack["hoods"][hood]:
            def select(pack, kind, seed="", template=template, hood=hood):
                return template if kind == hood else None

            monkeypatch.setattr(R.RP, "select_hood", select)
            for level in (0.0, 0.5):
                canvas = R.render(
                    Q._observed(),
                    Q._attrs("long", "long_straight", hood),
                    (),
                    noise_seed=12345 if level else None,
                    noise_level=level or 1.0,
                )
                problems = Q._check(canvas, "long", "long_straight", hood, "none")
                assert not problems, (hood, template.get("id"), level, problems)


def test_every_eye_template_renders_both_eyes(monkeypatch):
    """Forcing each approved eye template must keep both eye halves and the
    bottom eye row free of L2 hair."""
    pack = R.RP.load_pack()
    skin = shade(rgba("#e0ac69"), R.FACE_SHADE["front"])[:3]
    assert len(pack["eyes"]) == 4  # pinned: see hood test comment
    for eye in pack["eyes"]:
        def select(pack, seed="", hooded=False, eye=eye):
            return eye

        monkeypatch.setattr(R.RP, "select_eyes", select)
        for level in (0.0, 0.5):
            canvas = R.render(
                Q._observed(), Q._attrs("short", "short", "none"), (),
                noise_seed=12345 if level else None, noise_level=level or 1.0,
            )
            left = any(canvas.get("head", "front", u, v)[:3] != skin for u in (1, 2) for v in (5, 6))
            right = any(canvas.get("head", "front", u, v)[:3] != skin for u in (5, 6) for v in (5, 6))
            assert left and right, (eye.get("id"), level, "both eyes must render")
            for u in (1, 2, 5, 6):
                assert canvas.get("head", "front", u, 6, 1)[3] == 0, (eye.get("id"), level, u)


def test_production_matrix_passes_current_contract():
    r = run_matrix(styles=(("short", "short"), ("long_straight", "long")),
                   hoods=("none", "up", "down"), noise_levels=(0.0, 0.5))
    assert r["ok"], r["failures"]
    assert r["case_count"] == 12 + 2  # beard case + slim-geometry case
    assert any(c.get("model") == "slim" for c in r["cases"])


def test_production_matrix_reports_beard_case():
    r = run_matrix(styles=(("short", "short"),), hoods=("none",), noise_levels=(0.0,))
    # The explicit beard case is appended; the normal short case must pass.
    assert r["ok"], r["failures"]
