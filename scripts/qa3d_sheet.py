#!/usr/bin/env python3
"""Render a QA asset's cases as a real three.js 3D contact sheet.

Writes out/qa3d/cases_<name>.js and out/qa3d/<name>.png via headless Chrome.
"""
from __future__ import annotations
import argparse, base64, io, json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from skinmaker import attribute_masks as AM
from skinmaker.production_qa import run_matrix, _case_canvas

def build(asset: Path | None, name: str, only_fail: bool, limit: int) -> Path:
    if asset:
        AM.ASSET_PATH = asset
    report = run_matrix()
    cases = report["cases"]
    if only_fail:
        cases = [c for c in cases if c["problems"]]
    cases = cases[:limit]
    out = []
    for c in cases:
        canvas = _case_canvas(c)
        buf = io.BytesIO(); canvas.image.save(buf, format="PNG")
        skin = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        bits = [c["style"] + "/" + c["length"], c["hood"], "n" + str(c.get("noise", 0))]
        if c.get("model"): bits.append(c["model"])
        if c.get("beard"): bits.append("beard:" + c["beard"])
        out.append({"label": " · ".join(bits), "skin": skin, "problems": c["problems"]})
    data = {"title": f"skinmaker QA 3D · {name} · {len(cases)} cases",
            "cases": out}
    target = ROOT / "tools" / "mask_editor" / f"qa3d_cases_{name}.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("window.QA3D = " + json.dumps(data) + ";\n", encoding="utf-8")
    print(f"cases: {target} ({len(cases)})")
    return target

def shot(name: str, width: int, height: int) -> Path:
    png = ROOT / "out" / "qa3d" / f"{name}.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:10483/static/qa3d.html?data=/static/qa3d_cases_{name}.js"
    subprocess.run(["google-chrome", "--headless", "--no-sandbox",
                    "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                    f"--window-size={width},{height}",
                    "--virtual-time-budget=15000", f"--screenshot={png}", url],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"image: {png}")
    return png

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", type=Path)
    ap.add_argument("--name", required=True)
    ap.add_argument("--only-fail", action="store_true")
    ap.add_argument("--limit", type=int, default=18)
    ap.add_argument("--width", type=int, default=1810)
    ap.add_argument("--height", type=int, default=1220)
    args = ap.parse_args()
    build(args.asset, args.name, args.only_fail, args.limit)
    shot(args.name, args.width, args.height)

if __name__ == "__main__":
    main()
