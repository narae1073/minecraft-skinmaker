"""Near-orthographic QA renders of a skin, via headless Chrome + three.js.

Reusable visual-QA tool ("plugin") for skin/rendering changes. It renders the
same three.js model as the web viewer (shared ``frontend/src/skinModel.js``),
so what you see in the screenshots is what the app shows.

Camera contract
---------------
- weak perspective: default fov 12 deg at distance 24 (near-orthographic)
- front shot: yaw +24 deg, pitch +30 deg (front-right, tilted down)
- back shot:  yaw +204 deg, pitch +30 deg (back-right, tilted down)
- both shots share fov/distance/target/up, so the pair stays parallel-consistent

Outputs (``out_dir``)
---------------------
- ``front_right.png`` / ``back_right.png``: the two QA views
- ``contact_sheet.png``: both views side by side for human review
- ``render.json``: camera metadata, skin hash, texture layer pixel counts

Usage
-----
    .venv/bin/python -m skinmaker.qarender out/qa/skin.png
    .venv/bin/python -m skinmaker.qarender skin.png --out out/qa_render \\
        --model classic --yaw 24 --pitch 30 --width 512 --height 768

    from skinmaker.qarender import render_views
    result = render_views("skin.png", "out/qa_render")

The browser is auto-detected (``SKINMAKER_CHROME`` overrides). Requires Chrome
or Chromium; the page imports ``three`` from ``frontend/node_modules`` and the
model from ``frontend/src/skinModel.js``, both served from this repository.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .format import get_layout

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKGROUND = (226, 232, 240)
DEFAULT_WIDTH = 512
DEFAULT_HEIGHT = 768
DEFAULT_YAW = 24.0
DEFAULT_PITCH = 30.0
DEFAULT_FOV = 12.0
DEFAULT_DISTANCE = 24.0
BROWSER_CANDIDATES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "chrome",
)


def find_browser() -> str | None:
    """Chrome/Chromium path. ``SKINMAKER_CHROME`` wins when it points at a file."""
    override = os.environ.get("SKINMAKER_CHROME")
    if override:
        path = Path(override)
        if path.is_file():
            return str(path)
        found = shutil.which(override)
        return found
    for name in BROWSER_CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    return None


def camera_position(yaw: float, pitch: float, distance: float) -> tuple[float, float, float]:
    """Camera position for a turntable orbit around the origin (matches render.js)."""
    from math import cos, radians, sin

    y = radians(yaw)
    p = radians(pitch)
    return (
        distance * sin(y) * cos(p),
        distance * sin(p),
        distance * cos(y) * cos(p),
    )


def view_specs(yaw: float = DEFAULT_YAW, pitch: float = DEFAULT_PITCH, views: str = "default") -> list[dict]:
    """QA views. default = front/back pair; hair adds bottom and right-side."""
    if views not in ("default", "hair"):
        raise ValueError(f"views must be default|hair: {views!r}")
    specs = [
        {"name": "front_right", "yaw": float(yaw), "pitch": float(pitch)},
        {"name": "back_right", "yaw": float(yaw) + 180.0, "pitch": float(pitch)},
    ]
    if views == "hair":
        specs.append({"name": "bottom", "yaw": float(yaw) + 180.0, "pitch": -60.0})
        specs.append({"name": "right_side", "yaw": 90.0, "pitch": 0.0})
    return specs


def _layer_pixels(image: Image.Image, model: str) -> dict[str, int]:
    """Opaque pixels in the head+body L1/L2 rects (texture-level QA signal)."""
    layout = get_layout(model)
    counts = {}
    for layer in (0, 1):
        total = 0
        for part in ("head", "body"):
            for face in layout.part(part, layer).faces.values():
                for y in range(face.y, face.y + face.h):
                    for x in range(face.x, face.x + face.w):
                        if image.getpixel((x, y))[3] > 0:
                            total += 1
        counts[f"l{layer + 1}_opaque"] = total
    return counts


def _handler(skin_path: Path):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(REPO_ROOT), **kwargs)

        def do_GET(self):  # noqa: N802 (http.server API)
            if urlsplit(self.path).path == "/__skin__.png":
                data = skin_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            super().do_GET()

        def log_message(self, *args):
            pass

    return Handler


@contextlib.contextmanager
def _static_server(skin_path: Path):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _handler(skin_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _chrome(browser: str, url: str, target: Path, width: int, height: int, timeout: float) -> None:
    command = [
        browser,
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--enable-unsafe-swiftshader",
        "--use-gl=angle",
        "--use-angle=swiftshader",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        f"--window-size={width},{height}",
        "--virtual-time-budget=10000",
        f"--screenshot={target}",
        url,
    ]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"QA render timed out after {timeout}s: {url}") from exc
    if proc.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-800:]
        raise RuntimeError(f"Chrome failed to render {url}\n{detail}")
    with Image.open(target) as shot:
        if shot.size != (width, height):
            raise RuntimeError(f"unexpected screenshot size {shot.size} != {(width, height)}")
        pixels = np.asarray(shot.convert("RGB"))
    if float(pixels.std()) < 1.0:
        raise RuntimeError(
            f"blank QA render ({target}); WebGL likely failed. Try another Chrome build "
            "or set SKINMAKER_CHROME."
        )


def _contact_sheet(paths: list[Path], labels: list[str], dest: Path) -> Path:
    images = [Image.open(path).convert("RGB") for path in paths]
    label_height = 28
    gap = 8
    width = sum(img.width for img in images) + gap * (len(images) - 1)
    height = max(img.height for img in images) + label_height
    sheet = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=15)
    except TypeError:  # Pillow < 10.1
        font = ImageFont.load_default()
    x = 0
    for image, label in zip(images, labels):
        sheet.paste(image, (x, label_height))
        draw.text((x + 6, 6), label, fill=(38, 44, 52), font=font)
        x += image.width + gap
    sheet.save(dest)
    return dest


def render_views(
    skin: str | Path,
    out_dir: str | Path = "out/qa_render",
    *,
    model: str = "classic",
    yaw: float = DEFAULT_YAW,
    pitch: float = DEFAULT_PITCH,
    fov: float = DEFAULT_FOV,
    distance: float = DEFAULT_DISTANCE,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    browser: str | None = None,
    timeout: float = 90.0,
    views: str = "default",
) -> dict:
    """Render the QA views. Returns paths + metadata."""
    skin_path = Path(skin).resolve()
    if not skin_path.is_file():
        raise FileNotFoundError(f"skin not found: {skin_path}")
    if model not in ("classic", "slim"):
        raise ValueError(f"model must be classic|slim: {model!r}")
    if width < 32 or height < 32:
        raise ValueError("width/height must be >= 32")
    with Image.open(skin_path) as probe:
        if probe.size != (64, 64):
            raise ValueError(f"skin must be 64x64, got {probe.size}")
        texture = probe.convert("RGBA")

    binary = browser or find_browser()
    if not binary:
        raise RuntimeError(
            "Chrome/Chromium not found. Install Chrome or set SKINMAKER_CHROME."
        )

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    specs = view_specs(yaw, pitch, views)
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with _static_server(skin_path) as base:
        for view in specs:
            query = urlencode(
                {
                    "skin": "/__skin__.png",
                    "model": model,
                    "yaw": view["yaw"],
                    "pitch": view["pitch"],
                    "fov": fov,
                    "distance": distance,
                    "width": width,
                    "height": height,
                }
            )
            target = out / f"{view['name']}.png"
            _chrome(
                binary,
                f"{base}/frontend/qa/render.html?{query}",
                target,
                width,
                height,
                timeout,
            )
            view["path"] = target.name
            view["camera_position"] = list(camera_position(view["yaw"], view["pitch"], distance))

    paths = [out / f"{view['name']}.png" for view in specs]
    labels = [f"{view['name'].upper().replace('_', ' ')}  yaw {view['yaw']:+.0f}  pitch {view['pitch']:+.0f}" for view in specs]
    contact = _contact_sheet(paths, labels, out / "contact_sheet.png")
    metadata = {
        "generated_at": generated,
        "skin": {
            "path": str(skin_path),
            "sha256": hashlib.sha256(skin_path.read_bytes()).hexdigest(),
            "size": [64, 64],
            "texture": _layer_pixels(texture, model),
        },
        "model": model,
        "projection": {
            "type": "perspective",
            "fov_deg": float(fov),
            "distance": float(distance),
            "target": [0.0, 0.0, 0.0],
            "up": [0.0, 1.0, 0.0],
            "notes": "weak perspective: near-orthographic, identical parameters for both views",
        },
        "canvas": {"width": int(width), "height": int(height)},
        "views": specs,
        "contact_sheet": contact.name,
    }
    (out / "render.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {"out_dir": str(out), "views": specs, "contact_sheet": str(contact), "metadata": metadata}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skinmaker.qarender",
        description="Near-orthographic front/back QA renders of a 64x64 Minecraft skin.",
    )
    parser.add_argument("skin", help="path to the 64x64 RGBA skin PNG")
    parser.add_argument("--out", default="out/qa_render", help="output directory")
    parser.add_argument("--model", choices=("classic", "slim"), default="classic")
    parser.add_argument("--yaw", type=float, default=DEFAULT_YAW, help="front shot yaw (deg); back = +180")
    parser.add_argument("--pitch", type=float, default=DEFAULT_PITCH, help="downward tilt (deg)")
    parser.add_argument("--fov", type=float, default=DEFAULT_FOV, help="vertical FOV (deg)")
    parser.add_argument("--distance", type=float, default=DEFAULT_DISTANCE)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--browser", default=None, help="Chrome/Chromium binary (default: auto)")
    parser.add_argument("--timeout", type=float, default=90.0, help="per-view Chrome timeout (s)")
    parser.add_argument("--views", choices=("default", "hair"), default="default",
                        help="default=front/back; hair=front/back/bottom/right-side")
    args = parser.parse_args(argv)

    try:
        result = render_views(
            args.skin,
            args.out,
            model=args.model,
            yaw=args.yaw,
            pitch=args.pitch,
            fov=args.fov,
            distance=args.distance,
            width=args.width,
            height=args.height,
            browser=args.browser,
            timeout=args.timeout,
            views=args.views,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"qa render failed: {exc}")
        return 1

    for view in result["views"]:
        print(f"{view['name']:12s} yaw={view['yaw']:6.1f} pitch={view['pitch']:5.1f}  {view['path']}")
    print(f"contact      {result['contact_sheet']}")
    print(f"metadata     {Path(result['out_dir']) / 'render.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
