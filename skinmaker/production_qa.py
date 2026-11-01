"""Deterministic production QA matrix for hair/eyes/hood/noise invariants."""
from __future__ import annotations

from pathlib import Path

from . import attributes as A
from . import colors as C
from . import render as R
from .canvas import rgba, shade
from .format import get_layout
from .validate import validate_image


def _sample(hex_value: str, share: float = 0.5) -> C.ColorSample:
    r = int(hex_value[1:3], 16); g = int(hex_value[3:5], 16); b = int(hex_value[5:7], 16)
    return C.ColorSample(hex_value, share, True, (r, g, b), 100)


def _observed() -> C.ObservedColors:
    return C.ObservedColors(
        _sample("#e0ac69"), _sample("#3a2a1c"), _sample("#2f6fb5"), _sample("#3c4450"),
        (1.0, 1.0, 1.0), True, (0.5, 0.3, 0.2),
    )


def _attrs(length: str, style: str, hood: str, beard: str = "none") -> A.Attributes:
    return A.validate({
        "top_garment": "hoodie", "bottom_garment": "jeans", "pattern": "plain",
        "sleeve_len": "long", "hair_length": length, "hair_style": style,
        "hood": hood, "beard": beard, "hair_bbox": [200, 50, 800, 600],
    })


STYLES = (
    ("short", "short"), ("pixie", "short"), ("bob", "medium"),
    ("long_straight", "long"), ("long_wavy", "long"), ("curly", "long"),
    ("ponytail", "long"), ("bun", "long"),
)
HOODS = ("none", "up", "down")


def _check(canvas, length: str, style: str, hood: str, beard: str) -> list[str]:
    problems: list[str] = []
    L = get_layout("classic")
    problems += [str(p) for p in validate_image(canvas.image)]
    skin = shade(rgba("#e0ac69"), R.FACE_SHADE["front"])[:3]
    # Beard must never be painted. Side columns may be intentional side hair;
    # check the center jaw only (where a beard would be visible).
    # Eyes now occupy row 6; verify the chin row 7 and the center between eyes.
    for u in range(2, 6):
        c = canvas.get("head", "front", u, 7)[:3]
        if max(abs(c[i] - skin[i]) for i in range(3)) > R.NOISE_TOL:
            problems.append(f"beard/skin mismatch at front({u},7): {c}")
    for u in (3, 4):
        c = canvas.get("head", "front", u, 6)[:3]
        if max(abs(c[i] - skin[i]) for i in range(3)) > R.NOISE_TOL:
            problems.append(f"beard/skin mismatch at front({u},6): {c}")
    # Both eye regions must contain at least one non-skin pixel.
    for u in (1, 2, 5, 6):
        for v in (5, 6):
            if canvas.get("head", "front", u, v)[:3] != skin:
                break
        else:
            problems.append(f"no eye pixels at column {u}")
    # Bang policy: loose styles cover the eyebrow row (4); tied-up and
    # short/exposed-forehead styles keep it open. Eyes are rows 5-6.
    hair = shade(rgba("#3a2a1c"), R.FACE_SHADE["front"])[:3]
    loose = {"bob", "long_straight", "long_wavy", "curly"}
    for u in range(2, 6):
        c = canvas.get("head", "front", u, 4)[:3]
        if style in loose:
            if max(abs(c[i] - hair[i]) for i in range(3)) > R.NOISE_TOL:
                problems.append(f"loose style misses eyebrow row at ({u},4)")
        else:
            if max(abs(c[i] - skin[i]) for i in range(3)) > R.NOISE_TOL:
                problems.append(f"exposed/tied style covers eyebrow row at ({u},4)")

    # The bottom eye row (6) must never receive an L2 hair fringe.
    for u in (1, 2, 5, 6):
        if canvas.get("head", "front", u, 6, 1)[3]:
            problems.append(f"L2 fringe covers bottom eye row at ({u},6)")

    if hood == "up":
        top = [[canvas.get("head", "top", u, v, 1) for u in range(8)] for v in range(8)]
        # Seam/highlight accents are allowed, but no accent may be an isolated
        # 1px island (the defect that produced a 4x4 grid).
        for v in range(8):
            for u in range(8):
                c = top[v][u]
                if not c[3]:
                    continue
                neighbors = [
                    top[nv][nu] for nu, nv in ((u + 1, v), (u - 1, v), (u, v + 1), (u, v - 1))
                    if 0 <= nu < 8 and 0 <= nv < 8
                ]
                if all(n[:3] != c[:3] for n in neighbors):
                    problems.append(f"isolated hood pixel at top({u},{v})")
        # Face rows 4-5 must not get a hood L2 shell.
        for u in (1, 2, 5, 6):
            for v in (5, 6):
                if canvas.get("head", "front", u, v, 1)[3]:
                    problems.append(f"hood covers eye at ({u},{v})")
        # Hood-up policy (2026-11-01): the hood covers the back of the head and
        # upper back, so long hair must not show on the body back. The chest
        # locks do show and must start at the shoulder: the cowl is clothing
        # and the hair falls over it (production bug: locks cut 2 rows down).
        top_back = shade(rgba("#2f6fb5"), R.FACE_SHADE["back"])[:3]
        for u in range(8):
            for v in range(12):
                c = canvas.get("body", "back", u, v)[:3]
                if max(abs(c[i] - top_back[i]) for i in range(3)) > R.NOISE_TOL:
                    problems.append(f"hood-up back hair at ({u},{v}): {c}")
                    break
        if style in ("long_straight", "long_wavy", "curly"):
            hair_front = shade(rgba("#3a2a1c"), R.FACE_SHADE["front"])[:3]
            for u in (0, 1, 6, 7):
                l2 = canvas.get("body", "front", u, 0, 1)
                c = l2[:3] if l2[3] else canvas.get("body", "front", u, 0)[:3]
                if max(abs(c[i] - hair_front[i]) for i in range(3)) > R.NOISE_TOL * 1.5:
                    problems.append(f"hood-up chest lock cut at ({u},0): {c}")
    if hood == "down":
        # Hood down uses the reference cowl (front rim + back fold), not a
        # solid 8x3 band over the chest (max reference front coverage is 8).
        n = sum(1 for v in range(3) for u in range(8)
                if canvas.get("body", "front", u, v, 1)[3])
        if n > 8:
            problems.append(f"hood-down solid front band ({n} cells)")
    return problems


def run_matrix(styles=STYLES, hoods=HOODS, noise_levels=(0.0, 0.5)) -> dict:
    cases = []
    for style, length in styles:
        for hood in hoods:
            for level in noise_levels:
                attrs = _attrs(length, style, hood)
                seed = 12345 if level else None
                canvas = R.render(_observed(), attrs, (), noise_seed=seed, noise_level=level or 1.0)
                problems = _check(canvas, length, style, hood, "none")
                cases.append({
                    "style": style, "length": length, "hood": hood,
                    "noise": level, "problems": problems,
                })
    # Beard matrix on one style/hood.
    attrs = _attrs("short", "short", "none", "full")
    canvas = R.render(_observed(), attrs, ())
    problems = _check(canvas, "short", "short", "none", "full")
    cases.append({"style": "short", "length": "short", "hood": "none", "noise": 0.0,
                  "beard": "full", "problems": problems})
    return {
        "version": 1,
        "case_count": len(cases),
        "ok": all(not c["problems"] for c in cases),
        "failures": [c for c in cases if c["problems"]],
        "cases": cases,
    }


def write_report(path: Path) -> dict:
    import json
    report = run_matrix()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
