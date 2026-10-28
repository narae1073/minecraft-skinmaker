"""SCHP 인간 파싱으로 부위별 샘플 영역을 국소화한다. 기본 on (2026-10-12).

onnxruntime·모델이 모두 있을 때만 동작하고, 어느 쪽이 없으면 bottom_mask가
None을 돌려주고 호출부는 밴드/캐스케이드 경로로 폴백한다 (조용한 폴백).
SKINMAKER_PARSING=0/false/off/no 로 명시적으로 끌 수 있다.
절대 예외를 밖으로 던지지 않는다.

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
DRESS = 7  # ATR dress class — 하체 덮음 증거 + 밑단 측정 보조 (2026-10-28 실사진 프로브)
CLOTHED_CLASSES = (SKIRT, PANTS, DRESS)
HAIR = 2
BARE_LEGS = (12, 13)  # Left/Right-leg 맨다리 피부 — 하체 관측 신호 (jeans 기본 룰)
SHOES = (9, 10)  # Left-shoe, Right-shoe
LOWER_CLASSES = (SKIRT, PANTS, DRESS) + SHOES + BARE_LEGS

MEAN = np.array([0.406, 0.456, 0.485], np.float32)  # RGB 순서, BGR 인덱스 관례 (repo 문서)
STD = np.array([0.225, 0.224, 0.229], np.float32)

_SESSION = None


def parsing_on() -> bool:
    """기본 on. SKINMAKER_PARSING=0/false/off/no (또는 빈값) 로만 끈다."""
    return os.environ.get(PARSING_ENV, "1").strip().lower() not in ("0", "false", "off", "no", "")


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


def skirt_hem_rows(seg: np.ndarray | None, face, min_pixels: int = 40) -> int | None:
    """사진 속 치마 밑단을 다리 텍스처 행(0-8, 신발 위)으로 환산한다 (2026-10-28).

    치마는 드레스처럼 늘리지 않는다 — 사진의 밑단 길이를 따라가고 그 아래는
    맨다리로 남긴다. VLM이 skirt 라고 한 사진에만 렌더가 이 값을 쓴다.

    - 얼굴 아래 Skirt(5) 픽셀이 충분하고 옷 픽셀의 20% 이상이면 그 밑단을 쓴다.
    - Skirt 픽셀이 적으면(파서가 긴 치마를 Pants/Dress 로 오분류) 옷 클래스
      전체(5/6/7)의 가장 낮은 행을 쓴다 — 미니로 잘못 자르지 않는다.
    - 하체 옷 픽셀 자체가 없으면 None (호출부 기본값).
    - 하체 클래스(치마·바지·드레스·신발·맨다리)의 세로 범위로 정규화하고
      0-8 행으로 ceil 매핑. 발이 잘린 사진은 이미지 하단이 끝이다.
    """
    if seg is None or face is None:
        return None
    arr = np.asarray(seg)
    if arr.ndim != 2 or arr.size == 0:
        return None
    y0 = max(0, min(arr.shape[0] - 1, int(face.bottom)))
    sub = arr[y0:]
    skirt = sub == SKIRT
    clothed = np.isin(sub, CLOTHED_CLASSES)
    skirt_count = int(skirt.sum())
    clothed_count = int(clothed.sum())
    if clothed_count < min_pixels:
        return None
    # VLM 은 skirt 인데 파서가 Skirt 를 못 봤다. Dress 클래스가 하체 옷의
    # 절반 이상이면 긴 원피스로 보고 그 범위를 쓰고, 아니면(베스트/맨다리가
    # Pants/Dress 로 섞인 경우) 바지 끝까지 늘리지 않고 무릎 기본값을 쓴다
    # (image315: pants 3856 + dress 672 → 6, image409: dress 지배 → 9).
    if skirt_count < min_pixels:
        dress_count = int(np.isin(sub, (DRESS,)).sum())
        if dress_count < 0.5 * clothed_count:
            return 6
    if skirt_count >= min_pixels and skirt_count / clothed_count >= 0.2:
        hem_mask = skirt
    else:
        hem_mask = clothed  # 치마가 Pants/Dress 로 보인 경우 — 옷 전체 밑단
    rows = np.flatnonzero(np.isin(sub, LOWER_CLASSES).any(axis=1))
    if rows.size < 2:
        return None
    top, bottom = int(rows[0]), int(rows[-1])
    if bottom - top < 2:
        return None
    hem_rows = np.flatnonzero(hem_mask.any(axis=1))
    if hem_rows.size == 0:
        return None
    # 다리 텍스처의 0-8행은 신발(9행) 위다. 정규화 하한을 '발끝'이 아니라
    # '신발 시작'으로 잡아야 미디/롱 치마가 짧게(허벅지) 그려지지 않는다.
    # QA 재검(2026-10-28): 401/404/419/422/424 hems PASS with this mapping.
    leg_bottom = bottom
    shoes = np.flatnonzero(np.isin(sub, SHOES).any(axis=1))
    if shoes.size and int(shoes[0]) - top >= 3:
        leg_bottom = int(shoes[0])
    fraction = (int(hem_rows[-1]) - top) / float(leg_bottom - top)
    rows_above_shoes = int(np.ceil(min(1.0, max(0.0, fraction)) * 9))
    return max(1, min(9, rows_above_shoes))
