"""SCHP 인간 파싱으로 부위별 샘플 영역을 국소화한다. 옵션 계층 (기본 off).

SKINMAKER_PARSING=1 이고 onnxruntime·모델이 모두 있을 때만 동작한다.
어느 쪽이 없으면 bottom_mask가 None을 돌려주고 호출부는 밴드/캐스케이드
경로로 폴백한다. 절대 예외를 밖으로 던지지 않는다.

- 모델: pirocheto/schp-atr-18 SCHP INT8 ONNX (69 MB). 기본 경로
  out/models/…, SKINMAKER_PARSER 로 교체 가능. 다운로드:
  https://huggingface.co/pirocheto/schp-atr-18/resolve/main/onnx/schp-atr-18-int8-static.onnx
- 클래스: 0 Background · 2 Hair · 4 Upper-clothes · 5 Skirt · 6 Pants ·
  11 Face · 12/13 Left/Right-leg(맨다리 피부) · 14/15 arm · 9/10 shoe ·
  16 Bag · 17 Scarf. Hair(2)·Shoe(9/10)은 머리색·신발색 국소화에도 쓴다.
- 전처리(heat source: repo image_processing_schp.py 실제 코드): RGB →
  512×512 BILINEAR → /255 → (x−mean)/std, mean=[.406,.456,.485], std=[.225,.224,.229].
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image

PARSING_ENV = "SKINMAKER_PARSING"
PARSER_ENV = "SKINMAKER_PARSER"
DEFAULT_MODEL = Path(__file__).resolve().parent.parent / "out" / "models" / "schp-atr-18-int8-static.onnx"

PANTS, SKIRT = 6, 5
BOTTOM_CLASSES = (PANTS, SKIRT)
HAIR = 2
SHOES = (9, 10)  # Left-shoe, Right-shoe

MEAN = np.array([0.406, 0.456, 0.485], np.float32)  # RGB 순서, BGR 인덱스 관례 (repo 문서)
STD = np.array([0.225, 0.224, 0.229], np.float32)

_SESSION = None


def parsing_on() -> bool:
    return os.environ.get(PARSING_ENV, "").strip().lower() in ("1", "true", "on", "yes")


def parser_path() -> Path:
    return Path(os.environ.get(PARSER_ENV) or DEFAULT_MODEL)


def _runtime():
    try:
        import onnxruntime as ort

        return ort
    except Exception:
        return None


def reset() -> None:
    """세션 싱글턴 해제 (테스트용)."""
    global _SESSION

    _SESSION = None


def available() -> tuple[bool, str]:
    rt = _runtime()
    if rt is None:
        return False, "선택 의존성 없음: onnxruntime (pip install onnxruntime)"
    if not parser_path().exists():
        return False, f"파싱 모델 파일 없음: {parser_path()}"
    return True, str(parser_path())


def _session():
    global _SESSION

    if _SESSION is None:
        rt = _runtime()
        if rt is None:
            return None
        so = rt.SessionOptions()
        so.intra_op_num_threads = 4
        _SESSION = rt.InferenceSession(str(parser_path()), so, providers=["CPUExecutionProvider"])
    return _SESSION


def _preproc(image: Image.Image) -> np.ndarray:
    pil = image.convert("RGB").resize((512, 512), Image.BILINEAR)
    x = np.asarray(pil, np.float32) / 255.0
    x = (x - MEAN) / STD
    return x.transpose(2, 0, 1)[None].astype(np.float32)


def bottom_mask(image: Image.Image) -> np.ndarray | None:
    """원본 크기 class map (uint8). 불가/실패 → None (호출부 폴백)."""
    ok, _ = available()
    if not ok:
        return None
    try:
        sess = _session()
        if sess is None:
            return None
        logits = sess.run(["logits"], {"pixel_values": _preproc(image)})[0]
        seg512 = logits[0].argmax(axis=0).astype(np.uint8)
        w, h = image.size
        return np.asarray(Image.fromarray(seg512).resize((w, h), Image.NEAREST))
    except Exception:
        return None
