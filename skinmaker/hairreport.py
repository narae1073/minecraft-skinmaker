"""Deterministic hair QA for 64x64 skins (2026-10-29).

Texture-level checks complement the visual sub-agent:
- bottom rear hair coverage vs chin skin,
- L2 alpha holes inside the L1 hair silhouette,
- L1/L2 side-profile continuity,
- body-drape row count,
- style signature (opaque L2 cells per face).

Usage:
    python -m skinmaker.hairreport skin.png --hair "#1e1c1c" --skin "#c8ad97"
    python -m skinmaker.hairreport --batch out/qa_final --json out/hair_report.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from PIL import Image

from .format import get_layout
from .render import FACE_SHADE
from . import hairstencil as HS

HEAD_GRID = 8
# v0=front(턱), v7=back. Length → rear rows (mirrors hairstencil).
REAR_ROWS = {"short": 1, "medium": 2, "long": 3, "very_long": 4}
TOL = 30


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def _near(pixel, color, tol: int = TOL) -> bool:
    return max(abs(int(a) - int(b)) for a, b in zip(pixel[:3], color)) <= tol


def _shaded(hair, face_name: str):
    f = FACE_SHADE.get(face_name, 1.0)
    return tuple(min(255, int(round(c * f))) for c in hair)


def _rows_of_hair(image: Image.Image, face, hair) -> list[int]:
    return [
        sum(1 for u in range(face.w) if _near(image.getpixel((face.x + u, face.y + v)), hair))
        for v in range(face.h)
    ]


def _profile(image: Image.Image, face, hair) -> list[int]:
    """Contiguous hair rows from the top for each column."""
    out = []
    for u in range(face.w):
        h = 0
        for v in range(face.h):
            if _near(image.getpixel((face.x + u, face.y + v)), hair):
                h += 1
            else:
                break
        out.append(h)
    return out


def analyze(image: Image.Image, *, hair: str, skin: str, hair_length: str = "short",
            hair_style: str = "", model: str = "classic") -> dict:
    image = image.convert("RGBA")
    layout = get_layout(model)
    skin_rgb = _rgb(skin)
    rear = REAR_ROWS.get(hair_length, 1)
    # 실제 스킨의 정수리 색에서 머리 기준을 유도한다. observed hair 가 default 로
    # 대체된 스킨도 정확히 측정하기 위함 (render.resolve_colors 와 같은 결과).
    top_face = layout.face("head", "top", 0)
    top_colors = Counter(
        image.getpixel((top_face.x + u, top_face.y + v))[:3]
        for v in range(top_face.h) for u in range(top_face.w)
    )
    top_dom = top_colors.most_common(1)[0][0] if top_colors else (0, 0, 0)
    observed_hair_top = _shaded(_rgb(hair), "top")
    bald = _near(top_dom, _shaded(skin_rgb, "top"), 45) and not _near(top_dom, observed_hair_top, 80)
    if bald:
        return {
            "bottom_hair": 0, "bottom_rear_hair": 0, "bottom_rear_total": 8 * rear,
            "chin_hair": 0, "l2_holes": 0, "side_profile": [0] * 8, "side_jump": 0,
            "body_rows": 0, "front_holes": 0, "row3_hair": 0, "front_body_rows": 0,
            "back_body_rows": 0, "expected_front": 0, "expected_back": 0,
            "l2_counts": {}, "bald": True, "problems": [], "ok": True,
        }
    # Top face is covered by solid L2, so divide out both the face shade and the
    # dominant L2 highlight to recover the L1 hair base.
    base = tuple(min(255.0, c / (FACE_SHADE["top"] * 1.12)) for c in top_dom)
    hair_faces = {face: _shaded(base, face) for face in FACE_SHADE}

    bottom = layout.face("head", "bottom", 0)
    bottom_px = [
        image.getpixel((bottom.x + u, bottom.y + v))
        for v in range(bottom.h) for u in range(bottom.w)
    ]
    bottom_hair = sum(1 for p in bottom_px if _near(p, hair_faces["bottom"]))
    chin_hair = sum(
        1 for v in range(min(4, bottom.h)) for u in range(bottom.w)
        if _near(image.getpixel((bottom.x + u, bottom.y + v)), hair_faces["bottom"])
    )
    bottom_rear_px = [p for v in range(bottom.h - rear, bottom.h) for u in range(bottom.w)
                      for p in [image.getpixel((bottom.x + u, bottom.y + v))]]
    bottom_rear_hair = sum(1 for p in bottom_rear_px if _near(p, hair_faces["bottom"]))

    holes = 0
    # 머리만 검사한다. 몸통의 어두운 옷/피부가 머리색과 겹쳐 false hole 이 된다.
    for part in ("head",):
        for face_name in layout.part(part, 0).faces:
            l1 = layout.face(part, face_name, 0)
            l2 = layout.face(part, face_name, 1)
            for v in range(l1.h):
                if face_name == "front" and v in (4, 5):
                    continue  # 눈은 L2 가 일부러 덮지 않는다 — hole 아님
                for u in range(l1.w):
                    ref = hair_faces.get(face_name)
                    if ref is not None and _near(image.getpixel((l1.x + u, l1.y + v)), ref):
                        if image.getpixel((l2.x + u, l2.y + v))[3] == 0:
                            holes += 1

    # 앞머리 내부 구멍 / hairline row3 / body front·back drape.
    front0 = layout.face("head", "front", 0)
    fgrid = [[_near(image.getpixel((front0.x + u, front0.y + v)), hair_faces["front"]) for u in range(8)] for v in range(8)]
    front_holes = sum(
        1 for u in range(8) for v in range(1, 4)
        if not fgrid[v][u] and any(fgrid[a][u] for a in range(v)) and any(fgrid[b][u] for b in range(v + 1, 4))
    )
    row3_hair = sum(fgrid[3])
    style = hair_style if hair_style in HS.STYLE_DRAPE else ""
    expect_front, expect_back = HS.style_drape(style) if style else (0, 0)
    l2f = layout.face("body", "front", 1); l2b = layout.face("body", "back", 1)
    def l2_rows(face, u):
        n = 0
        for v in range(face.h):
            if image.getpixel((face.x + u, face.y + v))[3]: n += 1
            else: break
        return n
    front_body = l2_rows(l2f, 0)
    back_body = l2_rows(l2b, 0)
    full_fringe = style in ("bob", "long_straight", "long_wavy", "curly")

    right0 = layout.face("head", "right", 0)
    profile = _profile(image, right0, hair_faces["right"])
    jumps = max((abs(profile[i] - profile[i - 1]) for i in range(1, len(profile))), default=0)
    body = layout.face("body", "back", 0)
    rows = _rows_of_hair(image, body, hair_faces["back"])
    body_rows = 0
    for count in rows:
        if count >= body.w // 2:
            body_rows += 1
        else:
            break

    l2_counts = {}
    for face_name in layout.part("head", 1).faces:
        f = layout.face("head", face_name, 1)
        l2_counts[face_name] = sum(
            1 for v in range(f.h) for u in range(f.w)
            if image.getpixel((f.x + u, f.y + v))[3]
        )

    problems = []
    if bottom_rear_hair < len(bottom_rear_px) * 0.9:
        problems.append(f"bottom rear coverage {bottom_rear_hair}/{len(bottom_rear_px)}")
    if chin_hair:
        problems.append(f"chin hair {chin_hair}px")
    if holes:
        problems.append(f"L2 alpha holes {holes}")
    if jumps > 1:
        problems.append(f"side profile jump {jumps}")
    if front_holes:
        problems.append(f"front bang holes {front_holes}")
    if full_fringe and row3_hair < 6:
        problems.append(f"front hairline skin row3 ({row3_hair}/8)")
    if style and expect_front and front_body < expect_front:
        problems.append(f"front chest {front_body} < {expect_front}")
    if style and back_body > min(6, expect_back + 1):
        problems.append(f"back drape {back_body} > cap {min(6, expect_back + 1)}")
    return {
        "bottom_hair": bottom_hair,
        "bottom_rear_hair": bottom_rear_hair,
        "bottom_rear_total": len(bottom_rear_px),
        "chin_hair": chin_hair,
        "l2_holes": holes,
        "side_profile": profile,
        "side_jump": jumps,
        "body_rows": body_rows,
        "front_holes": front_holes,
        "row3_hair": row3_hair,
        "front_body_rows": front_body,
        "back_body_rows": back_body,
        "expected_front": expect_front,
        "expected_back": expect_back,
        "l2_counts": l2_counts,
        "problems": problems,
        "ok": not problems,
    }


def _batch(batch: Path) -> list[dict]:
    rows = []
    for result in sorted(batch.rglob("result.json")):
        data = json.loads(result.read_text(encoding="utf-8"))
        if data.get("status") != "ok":
            continue
        skin_path = result.parent / f"skin_{data.get('primary_skin') or 'c1'}.png"
        if not skin_path.is_file():
            skin_path = result.parent / "skin_c1.png"
        if not skin_path.is_file():
            continue
        observed = data.get("observed", {})
        length = data.get("classification", {}).get("values", {}).get("hair_length", "short")
        try:
            report = analyze(Image.open(skin_path), hair=observed["hair"],
                             skin=observed["skin"], hair_length=length,
                             hair_style=data.get("classification", {}).get("values", {}).get("hair_style", ""),
                             model=data.get("skin_model", "classic"))
        except (KeyError, OSError, TypeError):
            continue
        rows.append({"source": data["source"], "skin": str(skin_path), **report})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skinmaker.hairreport")
    parser.add_argument("skin", nargs="?", help="64x64 skin PNG")
    parser.add_argument("--hair", help="hair hex")
    parser.add_argument("--skin-color", dest="skin_color", help="skin hex")
    parser.add_argument("--length", default="short", choices=tuple(REAR_ROWS))
    parser.add_argument("--batch", help="batch root with result.json + skin_c1.png")
    parser.add_argument("--out", default="out/hair_report.json")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args(argv)
    if args.batch:
        rows = _batch(Path(args.batch))
        Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        bad = [r for r in rows if not r["ok"]]
        print(f"{len(rows)} skins, {len(bad)} with problems; wrote {args.out}")
        return 1 if bad else 0
    if not args.skin or not args.hair or not args.skin_color:
        parser.error("skin + --hair + --skin-color are required (or --batch)")
    report = analyze(Image.open(args.skin), hair=args.hair, skin=args.skin_color, hair_length=args.length)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
