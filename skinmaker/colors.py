"""S1 관측 추출: 사진에서 색을 읽는다. AI 없음.

분담은 이렇다. 코드는 "정밀한 측정"을 하고, VLM(S2)은 "분류"를 한다.
색을 VLM 에 물으면 회색 셔츠를 네이비로 부르므로 색 필드는 스키마에 두지 않는다.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

import cv2
import numpy as np
from PIL import Image

from .quality import FaceBox, PhotoInput, clip_to, hair_region, skin_region, shirt_bands
from . import hairstencil as HS
from . import parsing

LUMA = (0.2126, 0.7152, 0.0722)

SKIN_REF = (0.80, 0.63, 0.55)
WB_CLIP = 1.25
WB_MAX_CHROMA_DRIFT = 0.20
BACKGROUND_FRAME = 4
CLUSTER_BINS = 6
MIN_SHARE = 0.18
SAT_FLOOR = 0.28
CHROMA_TOL = 0.11
BG_LUMA_TOL = 25.0
LOWER_BODY_WINDOW = (0.75, 0.85)  # 이미지 높이 비율. 무릎~발목 (신발 위, 상의 아래)
LOWER_BODY_HALF_W = 1.5  # 얼굴 폭 배수. 두 다리 + 틈을 덮는다
LOWER_BODY_FG_MIN = 0.20  # 전경 픽셀이 이보다 적으면 측정 포기
WB_APPLY_CLIPPED = False  # 평가 하네스 A/B 토글. True 면 클립된 WB 게인도 적용 (F1 이전 동작)
LOWER_BODY_MASK_ENABLED = True  # 평가 하네스의 A/B 토글. 운영 경로는 항상 True
LIGHT_PERCENTILE = {"skin": 40.0, "hair": 30.0, "top": 20.0, "bottom": 20.0}


def luma(rgb: np.ndarray) -> float:
    return float(rgb[0] * LUMA[0] + rgb[1] * LUMA[1] + rgb[2] * LUMA[2])


def chromaticity(rgb) -> tuple[float, float, float]:
    total = float(rgb[0] + rgb[1] + rgb[2])
    if total <= 0:
        return (0.0, 0.0, 0.0)
    return (float(rgb[0]) / total, float(rgb[1]) / total, float(rgb[2]) / total)


def chroma_distance(a, b) -> float:
    ca, cb = chromaticity(a), chromaticity(b)
    return max(abs(ca[i] - cb[i]) for i in range(3))


def bottom_bands(face: FaceBox, image_size: tuple[int, int], expand: float = 1.5) -> list[FaceBox]:
    """상의 밴드보다 아래에서 하의 후보를 찾는다."""
    img_w, img_h = image_size
    top = face.bottom + int(face.h * 0.9)
    band_h = max(4, int(face.h * expand / 2))
    inset = int(face.w * 0.15)
    left = min(max(0, face.x + inset), img_w - 1)
    usable_w = min(face.w - 2 * inset, img_w - left)
    out = []
    for i in range(2):
        y = top + i * band_h
        height = min(band_h, img_h - y)
        if height < 4 or usable_w < 4:
            break
        out.append(FaceBox(left, y, usable_w, height))
    return out


def frame_lower_bands(face: FaceBox, image_size: tuple[int, int]) -> list[FaceBox]:
    """프레임 하부 1/3의 하의 후보. 하의 cascade 재시도용.

    발동 조건 3가지: 얼굴 비례 밴드가 (a) MISSING이거나, (b) 배경만
    재측정했거나, (c) 상의를 그대로 재측정했을 때(bottom ≈ top).
    전신에서 얼굴 비례 밴드는 바지가 아니라 셔츠를 보기 때문이다.
    얼굴이 하부 1/3까지 내려오면(상반신·클로즈업)
    보이는 하의가 없으므로 빈 리스트를 돌려줘 MISSING을 유지한다.
    """
    img_w, img_h = image_size
    lower_top = img_h * 2 // 3
    if face.bottom >= lower_top:
        return []
    region_h = img_h - lower_top
    band_h = region_h // 2
    if band_h < 4:
        return []
    inset = int(face.w * 0.15)
    left = min(max(0, face.x + inset), img_w - 1)
    usable_w = min(face.w - 2 * inset, img_w - left)
    if usable_w < 4:
        return []
    out = []
    for i in range(2):
        box = clip_to(FaceBox(left, lower_top + i * band_h, usable_w, band_h), (img_w, img_h))
        if box is not None:
            out.append(box)
    return out


def white_balance_gain(region_rgb, ref=SKIN_REF) -> tuple[tuple[float, float, float], bool]:
    """피부 크로마를 기준 앵커로 삼는 색온도 보정.

    gray-world 는 "평균이 회색" 이라 가정하지만 얼굴은 회색이 아니다.
    피부는 알려진 크로마를 가지므로 그 크로마를 기준으로 게인을 구한다.
    크로마만 바꾸고 휘도는 보존한다. 이미 올바르게 조명된 사진이면 게인이 1 이다.

    두 가지 방어를 둔다. 평균 대신 중앙값을 써서 그림자나 배경을 덜 끌려오게 하고,
    측정 크로마가 기준에서 멀면 "피부가 아니다" 로 보고 보정을 아예 하지 않는다.
    """
    med = np.median(region_rgb, axis=0)
    med_l = float(np.median(med))
    ref_l = float(np.median(np.asarray(ref, dtype=np.float64)))
    if med_l <= 1e-6 or ref_l <= 1e-6:
        return (1.0, 1.0, 1.0), False
    if chroma_distance(med, np.asarray(ref, dtype=np.float32)) > WB_MAX_CHROMA_DRIFT:
        return (1.0, 1.0, 1.0), False
    raw = [((ref[i] / ref_l) / (float(med[i]) / med_l)) for i in range(3)]
    clipped = tuple(min(max(g, 1.0 / WB_CLIP), WB_CLIP) for g in raw)
    ok = all(abs(g - c) < 1e-6 for g, c in zip(raw, clipped))
    return clipped, ok


def apply_gain(arr: np.ndarray, gain) -> np.ndarray:
    return np.clip(arr * np.asarray(gain, dtype=np.float32), 0.0, 1.0)


@dataclass(frozen=True)
class ColorSample:
    hex: str
    share: float
    confident: bool
    rgb: tuple[int, int, int]
    pixels: int = 0

    @property
    def missing(self) -> bool:
        return self.pixels == 0


MISSING = ColorSample("#000000", 0.0, False, (0, 0, 0), 0)


def _to_hex(rgb: np.ndarray) -> tuple[str, tuple[int, int, int]]:
    ints = tuple(int(round(float(c) * 255)) for c in rgb[:3])
    return "#%02x%02x%02x" % ints, ints  # type: ignore[return-value]


def dominant_color(
    pixels: np.ndarray,
    bins: int = CLUSTER_BINS,
    pick: str = "mode",
    reject: Sequence[tuple[float, float, float]] = (),
    min_share: float = MIN_SHARE,
) -> ColorSample:
    """양자화 후 최빈 군집의 중앙값.

    pick="saturated" 는 무늬 있는 천의 기본색을 찾을 때 쓴다.
    reject 는 크로마 튜플의 시퀀스다 (단일 크로마를 넣으면 안 된다).
    거리 가까운 군집을 건너뛴다.
    """
    if pixels.shape[0] == 0:
        return MISSING
    idx = np.clip((pixels[:, :3] * bins).astype(np.int32), 0, bins - 1)
    codes = idx[:, 0] * bins * bins + idx[:, 1] * bins + idx[:, 2]
    counts = np.bincount(codes, minlength=bins**3)
    order = np.argsort(-counts)
    total = int(counts.sum())
    for code in order:
        count = int(counts[code])
        if count == 0:
            continue
        i = (code // (bins * bins)) % bins
        j = (code // bins) % bins
        k = code % bins
        center = np.array([(i + 0.5) / bins, (j + 0.5) / bins, (k + 0.5) / bins])
        if any(chroma_distance(center, r) <= CHROMA_TOL for r in reject):
            continue
        members = pixels[codes == code]
        median = np.median(members[:, :3], axis=0)
        if pick == "saturated":
            hsv = cv2.cvtColor(
                (np.clip(median, 0, 1) * 255).astype(np.uint8).reshape(1, 1, 3),
                cv2.COLOR_RGB2HSV,
            )
            sat = float(hsv[0, 0, 1])
            if sat < SAT_FLOOR * 255:
                continue
        hex_str, ints = _to_hex(median)
        share = count / total
        return ColorSample(hex_str, share, share >= min_share, ints, int(members.shape[0]))
    return MISSING


def _region_pixels(arr: np.ndarray, box: FaceBox, light: float) -> np.ndarray:
    clipped = clip_to(box, (arr.shape[1], arr.shape[0]))
    if clipped is None:
        return np.zeros((0, 3), dtype=np.float32)
    patch = arr[clipped.y : clipped.y + clipped.h, clipped.x : clipped.x + clipped.w]
    flat = patch.reshape(-1, 3).astype(np.float32)
    lum = flat @ np.asarray(LUMA, dtype=np.float32)
    cutoff = float(np.percentile(lum, light))
    bright = flat[lum >= cutoff]
    return bright if bright.shape[0] >= 32 else flat


@dataclass(frozen=True)
class ObservedColors:
    skin: ColorSample
    hair: ColorSample
    top: ColorSample
    bottom: ColorSample
    wb_gain: tuple[float, float, float]
    wb_confident: bool
    skin_chroma: tuple[float, float, float]
    top_alt: ColorSample = MISSING
    stripe: str = "plain"
    cover: CoverEstimate | None = None
    bottom_plausible: bool = True  # 하의 측정이 피부도 배경도 아니다 (렌더 폴백 정책 입력)
    shoe: ColorSample = MISSING
    lower_body_seen: bool | None = None  # 파서가 하의/맨다리 픽셀을 봤는가 (None=판단 불가)
    hair_stencil: "HairStencil | None" = None  # 사진 실루엣 스텐실 (None=규칙 폴백)

    @property
    def top_confident(self) -> bool:
        return self.top.confident

    @property
    def top_skinlike(self) -> bool:
        """상의 색이 피부와 구분되지 않는다.

        맨살 어깨나 살구색 셔츠는 크로마가 같아 색만으로 못 구별한다.
        이 경우 S2 의 top_garment 판정 없이는 신뢰할 수 없다.
        """
        if self.top.missing or self.skin.missing:
            return False
        return chroma_distance(np.asarray(self.top.rgb, dtype=np.float32), np.asarray(self.skin.rgb, dtype=np.float32)) <= CHROMA_TOL

    @property
    def hair_confident(self) -> bool:
        return self.hair.confident

    def all_confident(self) -> bool:
        return all(c.confident for c in (self.skin, self.hair, self.top))


def background_chroma(arr: np.ndarray, frame: int = BACKGROUND_FRAME) -> tuple[float, float, float] | None:
    """테두리 프레임의 최빈 색 크로마. 헤어 영역에서 배경을 탈락시키는 데 쓴다."""
    h, w = arr.shape[:2]
    if h < frame * 2 + 4 or w < frame * 2 + 4:
        return None
    border = np.concatenate(
        [
            arr[:frame].reshape(-1, 3),
            arr[h - frame :].reshape(-1, 3),
            arr[:, :frame].reshape(-1, 3),
            arr[:, w - frame :].reshape(-1, 3),
        ]
    )
    sample = dominant_color(border.astype(np.float32), min_share=0.0)
    if sample.missing:
        return None
    return chromaticity(np.asarray(sample.rgb, dtype=np.float32) / 255.0)


def _crop_pixels(arr: np.ndarray, box: FaceBox) -> np.ndarray | None:
    clipped = clip_to(box, (arr.shape[1], arr.shape[0]))
    if clipped is None:
        return None
    patch = arr[clipped.y : clipped.y + clipped.h, clipped.x : clipped.x + clipped.w]
    if patch.size == 0:
        return None
    return patch.reshape(-1, 3).astype(np.float32)


def extract(
    photo: PhotoInput,
    patterned: bool = False,
    bins: int = CLUSTER_BINS,
    hair_bbox: FaceBox | None = None,
    seg=None,
    hair_source: str = "mask",
    hair_symmetry: str = "symmetrized",
) -> ObservedColors:
    """사진 한 장에서 색 4개를 읽는다.

    patterned=True 는 상이가 줄무늬/체크임을 S2 에서 확인됐을 때만 쓴다.
    seg (원본 크기 SCHP class map) 를 제공하면 파서를 다시 부르지 않는다
    (웹 경로에서 마스크 패널과 색 추출이 같은 세그먼트를 공유한다).
    hair_bbox 가 있으면 헤어를 얼굴 기하 대신 그 영역에서 읽는다 (S2 VLM grounding).
    hair_source="mask" (기본) 이고 seg 가 있으면 머리 실루엣 스텐실도 같은
    세그먼트에서 투영해 observed.hair_stencil 에 실는다 (hairstencil.py).
    근거가 서지 않으면 None — 렌더가 오늘의 길이 규칙으로 폴백한다.
    """
    if photo.face is None:
        return _empty()

    rgb = np.asarray(photo.image.convert("RGB"), dtype=np.float32) / 255.0

    face_pixels = _crop_pixels(rgb, skin_region(photo.face))
    if face_pixels is None or face_pixels.shape[0] == 0:
        return _empty()

    gain, wb_ok = white_balance_gain(face_pixels)
    # 클립된 게인(wb_ok=False)은 적용하지 않는다. 앵커가 작거나 붉게 치우치면
    # 과도한 게인이 중립색까지 밀어 흰 셔츠를 민트로 만든다 (images10). 확신
    # 없는 게인은 identity 로 두고 raw 를 유지한다.
    applied = gain if (wb_ok or WB_APPLY_CLIPPED) else (1.0, 1.0, 1.0)
    arr = apply_gain(rgb, applied)

    skin = dominant_color(_region_pixels(arr, skin_region(photo.face), LIGHT_PERCENTILE["skin"]), bins=bins)
    skin_chroma = chromaticity(np.asarray(skin.rgb, dtype=np.float32) / 255.0) if not skin.missing else (0.0, 0.0, 0.0)

    tiny = "small" in photo.degrade

    # 크로마 탈락은 헤어에만 쓴다. 갈색/베이지 셔츠는 피부와 크로마가 닮아 있어
    # 탈락시키면 옷 색을 못 얻는다. 의상 쪽은 공간 인셋과 최빈 점유율로 대신한다.
    hair_reject: list = []
    if not skin.missing:
        hair_reject.append(skin_chroma)
    bg = background_chroma(arr)
    bg_luma = background_luma(arr)
    if bg is not None:
        hair_reject.append(bg)

    # small이면 헤어만 블랭크한다. 얼굴이 작으면 헤어 영역도 작아 답이 없다.
    # 상/하의 밴드는 몸통 면적이라 픽셀 수가 충분하면 측정을 시도한다.
    # 전신샷(얼굴 30px + 유니폼 수백 px)에서 신호를 버리지 않기 위함.
    # 픽셀 부족이면 _from_bands가 MISSING을, 점유율 미달이면 render가 기본값을 쓴다.
    # 단, S2 hair_bbox가 있으면 블랭크를 우회한다. 블랭크 이유는 "작은 얼굴의
    # hair_region이 배경이라 답이 없다"인데, 명시 bbox는 별개 영역이라 이유가
    # 안 통한다 (전신샷이 정작 이 경로의 주 고객이다). reject·점유율 판정은
    # 그대로라 쓰레기 bbox는 MISSING/저점유율로 가서 render 기본값이 받는다.
    if hair_bbox is not None:
        hair = dominant_color(
            _region_pixels(arr, hair_bbox, LIGHT_PERCENTILE["hair"]), bins=bins, reject=tuple(hair_reject)
        )
    else:
        hair = MISSING if tiny else dominant_color(
            _region_pixels(arr, hair_region(photo.face), LIGHT_PERCENTILE["hair"]), bins=bins, reject=tuple(hair_reject)
        )

    top_pick = "saturated" if patterned else "mode"
    pose = getattr(photo, "pose", None)
    if pose is not None and pose.has_torso:
        from .pose import torso_bands

        shirt_boxes = torso_bands(pose, photo.image.size) or shirt_bands(photo.face, photo.image.size)
    else:
        shirt_boxes = shirt_bands(photo.face, photo.image.size)
    if pose is not None and pose.has_legs:
        from .pose import leg_bands

        bottom_boxes = leg_bands(pose, photo.image.size) or bottom_bands(photo.face, photo.image.size)
    elif pose is not None:
        # 상반신: 골반이 프레임 밖이라 하의가 안 보인다. 빈 밴드 → MISSING →
        # S3 기본값 + S2 none 규칙이 하의를 추론한다.
        bottom_boxes = []
    else:
        bottom_boxes = bottom_bands(photo.face, photo.image.size)
    top = _from_bands(arr, shirt_boxes, top_pick, (), bins)
    bottom = _from_bands(arr, bottom_boxes, "mode", (), bins)
    if pose is None and _bottom_needs_fallback(bottom, top, bg, bg_luma):
        # cascade: 얼굴 비례 밴드가 옷을 못 잡으면 프레임 하부를 본다.
        # pose 경로는 건드리지 않는다 (mediapipe 격리 중이라 항상 None).
        lower = frame_lower_bands(photo.face, photo.image.size)
        retry = _from_bands(arr, lower, "mode", (), bins)
        if not retry.missing and not _matches_background(retry, bg, bg_luma):
            bottom = retry
        elif lower:
            # 띠가 다리 사이 틈이나 바닥만 봤다. 다리 영역의 전경(배경과 휘도가 다른
            # 픽셀)에서 다시 잡는다. 마지막 수단이라 띠 결과가 있으면 건드리지 않는다.
            masked = (
                lower_body_sample(arr, photo.face, photo.image.size, bg_luma)
                if LOWER_BODY_MASK_ENABLED
                else MISSING
            )
            if not masked.missing:
                bottom = masked

    # L2: SCHP 마스크 국소화 (옵션, SKINMAKER_PARSING=1). 마스크가 하의
    # (Pants/Skirt) 픽셀을 주고 커버리지가 있으면 그 영역의 지배색이
    # 밴드/캐스케이드 결과를 대신한다 — L1 실측(0.644→0.746)에서 국소화
    # 실패가 전부 나아진 경로다. 불가/실패/빈 마스크는 현행 결과를 유지하고,
    # bottom_plausible은 아래 공통 경로로 일관 재계산된다.
    shoe = MISSING
    lower_body_seen = None  # 파서 꺼짐/실패 → 판단 불가 (jeans 기본 미적용)
    if parsing.parsing_on():
        seg = seg if seg is not None else parsing.bottom_mask(photo.image)
        if seg is not None:
            # 하체 관측 신호 (사용자 룰 2026-10-13): 하의(Pants/Skirt)나 맨다리
            # 피부 픽셀이 하나라도 있으면 하체가 프레임에 있다.
            lower_body_seen = bool(
                np.isin(seg, parsing.BOTTOM_CLASSES).any()
                or np.isin(seg, parsing.BARE_LEGS).any()
            )
            cls_mask = np.isin(seg, parsing.BOTTOM_CLASSES)
            if cls_mask.any():
                # SKIN_REF 앵커 WB는 따뜻한 피부를 중립으로 밀며 옅은 노랑까지
                # 회녹색으로 눌렀다 (fitting 59: mask+WB 0.746 → raw 0.797).
                # 마스크 자체가 옷을 고르므로 색은 WB 이전 원본으로 쟀고,
                # plausible 도 같은 원본 공간의 배경과 비교한다.
                bottom = dominant_color(rgb[cls_mask], bins=bins)
                raw_bg = background_chroma(rgb)
                raw_bg_luma = background_luma(rgb)
                parsing_bg, parsing_bg_luma = raw_bg, raw_bg_luma
            else:
                parsing_bg, parsing_bg_luma = bg, bg_luma
            # L2c: 머리도 마스크로 — eval hair fallback 10/10 문제를 직격한다.
            # hair_bbox·small 블랭크보다 마스크가 우선 (실측 영역이 진실이다);
            # 마스크에 머리 픽셀이 없으면 기존 bbox/기하 경로 결과를 유지한다.
            hair_mask = seg == parsing.HAIR
            if hair_mask.any():
                hair = dominant_color(rgb[hair_mask], bins=bins)
            # 신발도 마스크로 (검정 상수 대신 실측 색). 없으면 render가 SHOE 상수 폴백.
            shoe_mask = np.isin(seg, parsing.SHOES)
            if shoe_mask.any():
                shoe = dominant_color(rgb[shoe_mask], bins=bins)
        else:
            parsing_bg, parsing_bg_luma = bg, bg_luma
    else:
        parsing_bg, parsing_bg_luma = bg, bg_luma

    def _chroma_of(sample: ColorSample):
        if sample.missing:
            return None
        return chromaticity(np.asarray(sample.rgb, dtype=np.float32) / 255.0)

    # 줄무늬 2색 측정 (VLM 없이 코드로). 두 번째 색이 점유율·크로마를
    # 만족하고 방향까지 나오면 top_alt + stripe에 담는다.
    top_alt = MISSING
    stripe = "plain"
    if not top.missing:
        torso_px = [p for b in shirt_boxes for p in [_region_pixels(arr, b, LIGHT_PERCENTILE["top"])] if p.shape[0]]
        if torso_px:
            all_px = np.concatenate(torso_px)
            top_alt = runner_up(all_px, top, bins)
            if not top_alt.missing and shirt_boxes:
                biggest = max(shirt_boxes, key=lambda b: b.area)
                stripe = stripe_orientation(arr, biggest, top, top_alt)
                if stripe == "plain":
                    top_alt = MISSING

    # 소매/하의 커버 측정. 줄무늬면 보조색도 fabric 후보에 넣는다.
    cover = measure_cover(
        arr,
        getattr(photo, "pose", None),
        [c for c in (_chroma_of(top), _chroma_of(top_alt)) if c is not None] or None,
        None if skin.missing else skin_chroma,
        _chroma_of(bottom),
    )

    return ObservedColors(
        skin, hair, top, bottom, applied, wb_ok, skin_chroma, top_alt, stripe, cover,
        bottom_plausible=_bottom_plausible(bottom, parsing_bg, parsing_bg_luma),
        shoe=shoe,
        lower_body_seen=lower_body_seen,
        hair_stencil=(
            HS.mask_stencil(seg, photo.face, photo.image.size, symmetry=hair_symmetry)
            if seg is not None and hair_source == "mask" else None
        ),
    )


def _bottom_plausible(bottom: ColorSample, bg, bg_luma: float | None) -> bool:
    """하의 측정이 하의 색일 수 있는가. 배경이면 옷이 아니라 배경을 잰 것이다.

    피부색 판정은 넣지 않는다. 맨다리를 잰 값을 기본 청회색으로 바꾸면 오히려 틀린다
    (맨다리는 피부색이 맞다). 베이지·카키 바지도 피부와 크로마가 같아 탈락시키면
    정답을 잃는다 (라벨 59장에서 3건 손실, 이득 0).
    """
    if bottom.missing:
        return False
    return not _matches_background(bottom, bg, bg_luma)


def _empty() -> "ObservedColors":
    return ObservedColors(MISSING, MISSING, MISSING, MISSING, (1.0, 1.0, 1.0), False, (0.0, 0.0, 0.0))


STRIPE_SECOND_SHARE = 0.15
STRIPE_STRIP_RANGE = 0.35
STRIPE_STRIPS = 8


@dataclass(frozen=True)
class CoverEstimate:
    """관절 주변 커버 측정. 색 절대값 없이 상대 비교만 한다.

    소매: 어깨→팔꿈치→손목이 셔츠색인가 피부색인가.
    하의: 허벅지·종아리가 하의색인가 피부색인가. long=바지류, short=반바지류.
    치마는 따로 못 가린다 (무릎 사이 원단 필요) → short로 접고 문서에 남긴다.
    확신 없으면 None (기권). VLM 확신값이 있으면 VLM이 이긴다.
    """

    sleeve_len: str | None = None
    bottom_len: str | None = None
    arms_known: int = 0
    legs_known: int = 0


COVER_FAR = 0.20
COVER_AMBIGUOUS = 0.03
COVER_BOX_R = 3


def runner_up(
    pixels: np.ndarray,
    primary: ColorSample,
    bins: int = CLUSTER_BINS,
    min_share: float = STRIPE_SECOND_SHARE,
) -> ColorSample:
    """최빈 다음가는 색. 같은 계열로 흩어진 빈을 합쳐서 본다.

    조명 음영 때문에 빨강이 진빨강 11% + 연빨강 7%로 나뉘는 경우가 있다.
    단일 빈으로 보면 탈락하지만 계열 합계 18%면 줄무늬 두 번째 색이다.
    """
    if pixels.shape[0] == 0 or primary.missing:
        return MISSING
    idx = np.clip((pixels[:, :3] * bins).astype(np.int32), 0, bins - 1)
    codes = idx[:, 0] * bins * bins + idx[:, 1] * bins + idx[:, 2]
    counts = np.bincount(codes, minlength=bins**3)
    total = int(counts.sum())
    if total == 0:
        return MISSING
    pc = chromaticity(np.asarray(primary.rgb, dtype=np.float32) / 255.0)

    def center(code: int) -> np.ndarray:
        i = (code // (bins * bins)) % bins
        j = (code // bins) % bins
        k = code % bins
        return np.array([(i + 0.5) / bins, (j + 0.5) / bins, (k + 0.5) / bins])

    order = np.argsort(-counts)
    seed = None
    for code in order:
        if int(counts[code]) == 0:
            continue
        if chroma_distance(center(int(code)), pc) <= CHROMA_TOL:
            continue
        seed = int(code)
        break
    if seed is None:
        return MISSING
    seed_c = center(seed)
    family = {int(c) for c in range(bins**3) if int(counts[c]) > 0 and chroma_distance(center(int(c)), seed_c) <= CHROMA_TOL}
    fam_count = sum(int(counts[c]) for c in family)
    if fam_count / total < min_share:
        return MISSING
    members = pixels[np.isin(codes, list(family))]
    median = np.median(members[:, :3], axis=0)
    if chroma_distance(median, np.asarray(primary.rgb, dtype=np.float32) / 255.0) <= CHROMA_TOL:
        return MISSING
    hex_str, ints = _to_hex(median)
    return ColorSample(hex_str, fam_count / total, True, ints, int(members.shape[0]))


def _joint_median(arr: np.ndarray, x: int, y: int, r: int = COVER_BOX_R) -> np.ndarray | None:
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = max(0, x - r), max(0, y - r), min(w, x + r + 1), min(h, y + r + 1)
    if x1 - x0 < 3 or y1 - y0 < 3:
        return None
    return np.median(arr[y0:y1, x0:x1].reshape(-1, 3)[:, :3], axis=0)


def _nearer(sample: np.ndarray, fabric_refs: list, skin_ref) -> str | None:
    """fabric 후보들 vs 피부 중 가까운 쪽. 멀거나 애매하면 기권(None).

    fabric은 여러 개일 수 있다 (줄무늬 상의 top + top_alt). 그 중 가장
    가까운 거리로 본다. 색 절대값 없이 상대 비교만 한다.
    """
    da = min(chroma_distance(sample, np.asarray(r, dtype=np.float32)) for r in fabric_refs)
    db = chroma_distance(sample, np.asarray(skin_ref, dtype=np.float32))
    if min(da, db) > COVER_FAR:
        return None
    if abs(da - db) < COVER_AMBIGUOUS:
        return None
    return "a" if da < db else "b"


def _sleeve_of_arm(upper, elbow, wrist) -> str | None:
    if wrist == "a":
        return "long"
    if elbow == "a":
        return "three_quarter"
    if upper == "a":
        return "short"
    if upper == "b":
        return "none"
    return None


SLEEVE_COVER_ORDER = ("none", "short", "three_quarter", "long")


def measure_cover(arr: np.ndarray, pose, top_refs: list | None, skin_ref, bottom_ref) -> CoverEstimate:
    """소매 길이 + 하의 길이를 관절 샘플로 잰다. 전부 상대 비교. 기권 가능.

    팔 충돌(가림) 시 긴 쪽을 믿는다: 원단 검출이 positive evidence고,
    맨살은 배경(관중 피부)일 수 있다. 반대 오류(원단색 배경)보다 드물다.
    """
    if pose is None:
        return CoverEstimate()
    sleeves: list[str] = []
    if top_refs and skin_ref is not None:
        for sh, el, wr in pose.arm_points():
            upper_pt = ((sh.x + el.x) // 2, (sh.y + el.y) // 2)
            verdicts = {}
            for key, (jx, jy) in (("upper", upper_pt), ("elbow", (el.x, el.y)), ("wrist", (wr.x, wr.y))):
                med = _joint_median(arr, jx, jy)
                verdicts[key] = _nearer(med, top_refs, skin_ref) if med is not None else None
            got = _sleeve_of_arm(verdicts["upper"], verdicts["elbow"], verdicts["wrist"])
            if got is not None:
                sleeves.append(got)
    legs: list[str] = []
    if bottom_ref is not None and skin_ref is not None:
        for h, k, a in pose.leg_points():
            thigh = ((h.x + k.x) // 2, (h.y + k.y) // 2)
            if a is not None:
                calf = ((k.x + a.x) // 2, (k.y + a.y) // 2)
            else:
                calf = (k.x, min(arr.shape[0] - 1, k.y + (k.y - h.y) // 2))
            tm = _joint_median(arr, *thigh)
            cm = _joint_median(arr, *calf)
            tv = _nearer(tm, [bottom_ref], skin_ref) if tm is not None else None
            cv = _nearer(cm, [bottom_ref], skin_ref) if cm is not None else None
            if tv == "a" and cv == "a":
                legs.append("long")
            elif tv == "a" or tv == "b":
                legs.append("short")
    sleeve = max(sleeves, key=SLEEVE_COVER_ORDER.index) if sleeves else None
    bottom = "long" if legs and all(v == "long" for v in legs) else ("short" if legs else None)
    return CoverEstimate(sleeve, bottom, len(sleeves), len(legs))


def stripe_orientation(
    arr: np.ndarray,
    box: FaceBox,
    primary: ColorSample,
    secondary: ColorSample,
    strips: int = STRIPE_STRIPS,
) -> str:
    """두 색 마스크의 열/행 분포로 줄무늬 방향을 잰다. 둘 다 아니면 plain."""
    if primary.missing or secondary.missing:
        return "plain"
    clipped = clip_to(box, (arr.shape[1], arr.shape[0]))
    if clipped is None or clipped.w < strips or clipped.h < strips:
        return "plain"
    patch = arr[clipped.y : clipped.y + clipped.h, clipped.x : clipped.x + clipped.w, :3]
    flat = patch.reshape(-1, 3)
    pc = np.asarray(primary.rgb, dtype=np.float32) / 255.0
    sc = np.asarray(secondary.rgb, dtype=np.float32) / 255.0
    dp = np.abs(flat - pc).max(axis=1)
    ds = np.abs(flat - sc).max(axis=1)
    mask = (ds < dp).reshape(clipped.h, clipped.w).astype(np.float32)

    def strip_range(fracs: np.ndarray) -> float:
        return float(fracs.max() - fracs.min())

    col_frac = mask.mean(axis=0)
    row_frac = mask.mean(axis=1)
    n = strips
    col_split = np.array_split(col_frac, n)
    row_split = np.array_split(row_frac, n)
    range_v = strip_range(np.array([c.mean() for c in col_split]))
    range_h = strip_range(np.array([r.mean() for r in row_split]))
    if range_v >= STRIPE_STRIP_RANGE and range_v >= range_h:
        return "vertical_stripe"
    if range_h >= STRIPE_STRIP_RANGE and range_h > range_v:
        return "horizontal_stripe"
    return "plain"


def _from_bands(
    arr: np.ndarray,
    bands: list[FaceBox],
    pick: str,
    reject: tuple[tuple[float, float, float], ...],
    bins: int,
) -> ColorSample:
    """밴드별 최빈값을 모아 그 색 계열의 최빈값을 고른다 (최빈값의 최빈값)."""
    samples = []
    for i, band in enumerate(bands):
        pixels = _region_pixels(arr, band, LIGHT_PERCENTILE["top" if i == 0 else "bottom"])
        samples.append(dominant_color(pixels, bins=bins, pick=pick, reject=reject))
    samples = [s for s in samples if not s.missing]
    if not samples:
        return MISSING
    return max(samples, key=lambda s: s.share * (s.pixels**0.5))


def background_luma(arr: np.ndarray, frame: int = BACKGROUND_FRAME) -> float | None:
    """테두리 프레임의 중앙값 휘도 (0-255). 배경 판정의 휘도 축."""
    h, w = arr.shape[:2]
    if h < frame * 2 + 4 or w < frame * 2 + 4:
        return None
    border = np.concatenate(
        [
            arr[:frame].reshape(-1, 3),
            arr[h - frame :].reshape(-1, 3),
            arr[:, :frame].reshape(-1, 3),
            arr[:, w - frame :].reshape(-1, 3),
        ]
    ).astype(np.float32)
    return float(np.median(border @ np.asarray(LUMA, dtype=np.float32))) * 255.0


def lower_body_sample(arr: np.ndarray, face: FaceBox, image_size: tuple[int, int], bg_luma: float | None) -> ColorSample:
    """다리 영역 전경 마스크의 최빈색. 배경과 휘도가 다른 픽셀만 본다.

    얼굴 중심 열을 가운데 두고 무릎~발목 높이만 자른다. 상의 아래쪽 경계를
    넘지 않으므로 상의 색이 섞이지 않는다 (상의가 같은 열에 있어도 창 밖이다).
    """
    if bg_luma is None:
        return MISSING
    img_w, img_h = image_size
    lo, hi = LOWER_BODY_WINDOW
    cx = face.x + face.w // 2
    hw = int(face.w * LOWER_BODY_HALF_W)
    box = clip_to(FaceBox(cx - hw, int(img_h * lo), 2 * hw, int(img_h * (hi - lo))), (img_w, img_h))
    if box is None:
        return MISSING
    sub = arr[box.y : box.bottom, box.x : box.right].reshape(-1, 3).astype(np.float32)
    lum = sub @ np.asarray(LUMA, dtype=np.float32) * 255.0
    fg = sub[np.abs(lum - bg_luma) > BG_LUMA_TOL]
    if fg.shape[0] < LOWER_BODY_FG_MIN * sub.shape[0]:
        return MISSING
    # 마지막 수단의 추정. 점유율이 높아도 확신값으로 내보내지 않는다 (downstream 이 안다).
    return replace(dominant_color(fg, bins=CLUSTER_BINS), confident=False)


def _matches_background(sample: ColorSample, bg, bg_luma: float | None = None) -> bool:
    """밴드 측정값이 배경이면 옷을 못 잡은 것이다 (배경만 봄).

    크로마만 보면 짙은 무채색 옷(청바지·슬랙스)이 회색 배경과 구별되지 않는다.
    bg_luma 가 주어지면 휘도도 맞아야 배경으로 본다.
    """
    if sample.missing or bg is None:
        return False
    if (
        chroma_distance(
            np.asarray(sample.rgb, dtype=np.float32) / 255.0,
            np.asarray(bg, dtype=np.float32),
        )
        > CHROMA_TOL
    ):
        return False
    if bg_luma is not None and abs(luma(np.asarray(sample.rgb, dtype=np.float32)) - bg_luma) > BG_LUMA_TOL:
        return False
    return True


def _bottom_needs_fallback(bottom: ColorSample, top: ColorSample, bg, bg_luma: float | None = None) -> bool:
    """하의 cascade 발동 조건 3가지. (a) 밴드가 비어 `_from_bands`가
    MISSING을 돌려줬거나, (b) 배경만 재측정했거나, (c) 상의를 그대로
    재측정했을 때(bottom ≈ top, 전신의 primary 케이스).
    의상 측정에 크로마 탈락을 넣지 않으므로(갈색 셔츠 회귀 금지)
    호출부에서 비교한다."""
    if bottom.missing or _matches_background(bottom, bg, bg_luma):
        return True
    if top.missing:
        return False
    return (
        chroma_distance(
            np.asarray(bottom.rgb, dtype=np.float32),
            np.asarray(top.rgb, dtype=np.float32),
        )
        <= CHROMA_TOL
    )
