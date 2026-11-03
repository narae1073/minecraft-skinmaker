"""YOLOv8n person detector for full-body auto-crop (CPU, ONNX)."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ASSET = Path(__file__).resolve().parent.parent / "assets" / "yolov8n.onnx"
_NET = None
_INPUT = 640
CONF = 0.25
NMS = 0.45
MARGIN = 0.10


def _net():
    global _NET
    if _NET is None:
        if not ASSET.exists():
            return None
        _NET = cv2.dnn.readNetFromONNX(str(ASSET))
    return _NET


def _with_margin(size: tuple[int, int], box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    iw, ih = size
    x, y, w, h = box
    mx, my = int(round(w * MARGIN)), int(round(h * MARGIN))
    x0, y0 = max(0, x - mx), max(0, y - my)
    x1, y1 = min(iw, x + w + mx), min(ih, y + h + my)
    return x0, y0, max(1, x1 - x0), max(1, y1 - y0)


def detect_person(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Largest person bbox + 10% margin, in image pixels. None if unavailable."""
    net = _net()
    if net is None:
        return None
    rgb = np.asarray(image.convert("RGB"))
    h, w = rgb.shape[:2]
    if w <= 0 or h <= 0:
        return None
    scale = min(_INPUT / w, _INPUT / h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    canvas = np.full((_INPUT, _INPUT, 3), 114, np.uint8)
    canvas[:nh, :nw] = cv2.resize(rgb, (nw, nh))
    net.setInput(cv2.dnn.blobFromImage(canvas, 1 / 255.0, (_INPUT, _INPUT), swapRB=True, crop=False))
    out = net.forward()[0].T
    scores = out[:, 4:]
    confs = scores.max(axis=1)
    classes = scores.argmax(axis=1)
    mask = (confs > CONF) & (classes == 0)
    if not mask.any():
        return None
    boxes, weights = [], []
    for row, c in zip(out[mask], confs[mask]):
        cx, cy, bw, bh = (float(v) for v in row[:4])
        x = (cx - bw / 2) / scale
        y = (cy - bh / 2) / scale
        boxes.append([int(round(x)), int(round(y)), int(round(bw / scale)), int(round(bh / scale))])
        weights.append(float(c))
    keep = cv2.dnn.NMSBoxes(boxes, weights, CONF, NMS)
    if len(keep) == 0:
        return None
    best = max((int(i) for i in np.array(keep).reshape(-1)), key=lambda i: boxes[i][2] * boxes[i][3])
    return _with_margin((w, h), tuple(boxes[best]))
