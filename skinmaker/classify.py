"""S2 오케스트레이션: 사진 준비 → 전송 계층 호출 → 검증 → 불확실성 판정.

전송 계층 이름만 바꾸면 비교 실험이 된다.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from PIL import Image

from .attributes import (
    BBOX_FIELD,
    DEFAULTS,
    FIELD_ORDER,
    NATURAL_ORDER,
    REVERSED_ORDER,
    Attributes,
    agreement,
    apply_cross_rules,
    build_prompt,
    build_schema,
    is_uncertain,
    validate,
)
from .quality import FaceBox, PhotoInput, clip_to
from .vlm import Transport

MODEL_MAX_PX = 768
FULLBODY_MAX_PX = 1536
FRAMING_FULLBODY_MAX_RATIO = 0.12


@dataclass(frozen=True)
class ModelCrop:
    image: Image.Image
    source: FaceBox

    def back_to_original(self, bbox: tuple[int, int, int, int] | None, size: tuple[int, int]) -> FaceBox | None:
        """모델이 준 0-1000 정규화 좌표를 원본 이미지 픽셀로 되돌린다."""
        if bbox is None:
            return None
        img_w, img_h = size
        sx = self.source.w / 1000.0
        sy = self.source.h / 1000.0
        x0 = int(round(self.source.x + bbox[0] * sx))
        y0 = int(round(self.source.y + bbox[1] * sy))
        x1 = int(round(self.source.x + bbox[2] * sx))
        y1 = int(round(self.source.y + bbox[3] * sy))
        return clip_to(FaceBox(x0, y0, max(0, x1 - x0), max(0, y1 - y0)), size)


def model_region(face: FaceBox, size: tuple[int, int], up: float = 1.25, down: float = 4.0, side: float = 1.7) -> FaceBox:
    """얼굴 + 어깨 + 상의 + 하의가 들어가는 세로 크롭.

    하단은 이미지 하단에 닿을 만큼 내린다: 전신(작은 얼굴)에서는 고정
    down=4.0 으로는 다리가 잘린다 (messi5: 크롭 하단 280 < 이미지 342).
    초상화에서는 고정 down 만으로 이미 프레임을 넘기므로 clip_to 가
    잘라 기존과 동일하다.

    side/up 확장 (2026-10-11, B1 실측 — images12 600x400, face(216,148,59,76)):
    옆팔꿈치가 face.x+2.7fw, 올린 손끝이 face.y-1.2fh 지점. 기존 side=0.9·
    up=0.9 는 앉은 구도의 옆옷(하의)과 손을 잘라 VLM 이 bottom=none 을 답했다.
    side=1.7(up=1.25) 로 곱늘어도 768/1536 다운스케일 예산이라 토큰은 그대로,
    소실 대상만 작아진다. 대가: 기존 초상화 크롭 폭 2.8fw → 4.4fw (고정
    테스트는 새 수치로 갱신. 실측 A-B 로 하락 없음을 확인한다).
    """
    img_w, img_h = size
    need = (img_h - face.bottom) / face.h if face.h > 0 else down
    down_eff = max(down, need)
    x = int(face.w * side)
    return FaceBox(
        face.x - x,
        face.y - int(face.h * up),
        face.w + 2 * x,
        int(face.h * (up + 1 + down_eff)),
    )


def framing(photo: PhotoInput) -> str:
    """구도 판정. 얼굴이 작으면 전신으로 보고 고해상도로 전송한다."""
    if photo.face is None:
        return "portrait"
    img_w, img_h = photo.image.size
    if img_h <= 0:
        return "portrait"
    if photo.face.h / img_h < FRAMING_FULLBODY_MAX_RATIO:
        return "fullbody"
    return "portrait"


def prepare(photo: PhotoInput, max_px: int | None = None) -> ModelCrop | None:
    """max_px=None 이면 프레이밍으로 자동 선택 (전신 1536 / 초상 768).

    명시값이 오면 그대로 쓴다. 호출부(backend, s4)는 손대지 않는다.
    """
    if photo.face is None:
        return None
    if max_px is None:
        max_px = FULLBODY_MAX_PX if framing(photo) == "fullbody" else MODEL_MAX_PX
    region = clip_to(model_region(photo.face, photo.image.size), photo.image.size)
    if region is None or region.w < 16 or region.h < 16:
        return None
    cropped = photo.image.convert("RGB").crop((region.x, region.y, region.right, region.bottom))
    scale = min(1.0, max_px / max(cropped.width, cropped.height))
    if scale < 1.0:
        cropped = cropped.resize((max(1, int(cropped.width * scale)), max(1, int(cropped.height * scale))), Image.LANCZOS)
    return ModelCrop(cropped, region)


@dataclass
class Classification:
    attributes: Attributes
    uncertain: tuple[str, ...]
    transport: str
    double_checked: bool
    elapsed: float
    ok: bool
    error: str | None = None
    raw_first: dict | None = field(default=None, repr=False)
    raw_second: dict | None = field(default=None, repr=False)

    @property
    def hair_bbox_px(self) -> FaceBox | None:
        return self._hair_px

    _hair_px: FaceBox | None = field(default=None, repr=False)


def classify(
    photo: PhotoInput,
    transport: Transport,
    double_check: bool = True,
    prepare_max_px: int | None = None,
) -> Classification:
    crop = prepare(photo, prepare_max_px)
    if crop is None:
        return Classification(
            Attributes(dict(), None), tuple(FIELD_ORDER), getattr(transport, "name", "?"), False, 0.0, False,
            error="얼굴이 없어 모델에 보낼 크롭을 만들지 못함",
        )

    started = time.monotonic()
    first_raw = transport.complete(crop.image, build_prompt(NATURAL_ORDER), build_schema(NATURAL_ORDER))
    if first_raw is None:
        err = getattr(transport, "last_error", None) or "모델 응답 파싱 실패"
        return Classification(
            Attributes(dict(), None), tuple(FIELD_ORDER), getattr(transport, "name", "?"), False,
            time.monotonic() - started, False, error=err,
        )
    first = validate(first_raw)

    second_raw = None
    uncertain = is_uncertain(first)
    if double_check:
        second_raw = transport.complete(crop.image, build_prompt(REVERSED_ORDER), build_schema(REVERSED_ORDER))
        if second_raw is not None:
            second = validate(second_raw)
            uncertain = tuple(n for n in agreement(first, second) if n != BBOX_FIELD)

    elapsed = time.monotonic() - started
    merged = first if second_raw is None else _merge(first, validate(second_raw))
    result = Classification(
        merged,
        uncertain,
        getattr(transport, "name", "?"),
        second_raw is not None,
        elapsed,
        True,
        raw_first=first_raw,
        raw_second=second_raw,
    )
    result._hair_px = crop.back_to_original(merged.hair_bbox, photo.image.size)
    return result


def _merge(a: Attributes, b: Attributes) -> Attributes:
    """두 질의에서 모두 유효한 필드는 우선값을 유지하고, 나머지는 둘째로 채운다."""
    values = dict(DEFAULTS)
    coerced: list[str] = []
    missing: list[str] = []
    for name in FIELD_ORDER:
        first_ok = name not in a.coerced and name not in a.missing
        second_ok = name not in b.coerced and name not in b.missing
        if first_ok and second_ok:
            values[name] = a.get(name)
        elif first_ok:
            values[name] = a.get(name)
            coerced.extend(n for n in (a.coerced, b.coerced) if name in n)
        elif second_ok:
            values[name] = b.get(name)
            coerced.extend(n for n in (a.coerced, b.coerced) if name in n)
        else:
            values[name] = a.get(name)
            coerced.extend(n for n in (a.coerced, b.coerced) if name in n)
        if name in a.missing and name in b.missing:
            missing.append(name)
    bbox = a.hair_bbox or b.hair_bbox
    cross = apply_cross_rules(values)
    return Attributes(cross.values, bbox, tuple(sorted(set(coerced))), tuple(sorted(set(missing))), a.raw, cross.applied)
