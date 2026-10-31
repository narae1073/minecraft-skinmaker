"""S3 파라메트릭 렌더: 관측(S1) + 분류(S2) → 64×64 픽셀. AI 없음.

규칙:
- HEAD(layer=0)에 얼굴 + 기본 머리카락만. HEAD ACC.(layer=1)는 기본 투명,
  모자/헬멧/안경/3D 오버레이 전용이라 v1에서는 비워둔다.
- 뒤 75%(미관측 10면)는 앞 관측에서 결정적으로 파생한다. LLM이 뒤 픽셀을
  직접 그리지 않는다. graphic 앞면 → 뒷면은 plain이 안전하다.
- 품질 저하(degrade)나 불확실하면 같은 그림을 더 보수적으로 그린다
  (무늬 → plain 강제). 거부하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import replace

from PIL import Image

from .attributes import Attributes
from .canvas import Color, SkinCanvas, rgba, shade
from .colors import MISSING, ObservedColors
from .texture import COMPLEX_PATTERNS, FabricTexture
from . import hairstencil as HS
from .structure import apply_structure
from .format import HEAD_ACCESSORY_LAYER  # noqa: F401  (규칙 문서화용: ACC.는 손대지 않는다)

FACE_SHADE = {
    "top": 1.12,
    "front": 1.0,
    "back": 0.90,
    "left": 0.84,
    "right": 0.84,
    "bottom": 0.72,
}

DEFAULT_SKIN = "#e0ac69"
DEFAULT_HAIR = "#3a2a1c"
DEFAULT_IRIS = "#3b2a1a"
DEFAULT_INNER = "#e9eef3"  # 안쪽 옷 측정 실패 시 밝은 셔츠 (사용자 결정 2026-10-21)
DEFAULT_TIE = "#3a3f4a"
JACKET_LIKE = ("jacket", "uniform", "overalls", "apron")
DEFAULT_TOP = "#5a5a5a"
DEFAULT_BOTTOM = "#3c4450"
DEFAULT_JEANS = "#3b5a86"  # 하체 미관측 jeans 기본 — 클래식 데님 청색 (사용자 결정)
SHOE = "#2b2b2b"

# 소매 길이 → 셔츠가 덮는 행(0-based, 끝 포함). 나머지는 피부+손.
# long도 손 2행은 남긴다(손목까지 소매 + 손).
SLEEVE_ROWS = {
    "none": -1,
    "short": 3,
    "three_quarter": 7,
    "long": 9,
}

# 하의 → 다리 구성 (바지 끝행, 신발 시작행). 신발은 항상 SHOE 단색.
BOTTOM_ROWS = {
    "jeans": (11, 9),
    "pants": (11, 9),
    "shorts": (5, 9),
    "skirt": (1, 9),
    "dress": (11, 9),
    "none": (-1, 9),
}

# 치마 밑단 측정(parsing.skirt_hem_rows)이 없을 때의 기본 행 수 (0-8 중).
# 예전 고정 1행(매우 짧은 치마)은 사진과 무관해 2026-10-28 중간값으로 교체.
DEFAULT_SKIRT_ROWS = 3

CONSERVATIVE_DEGRADE = ("blur", "dark", "bright", "small", "flat")


def _hex_or(hex_value: str, fallback: str) -> Color:
    try:
        return rgba(hex_value)
    except ValueError:
        return rgba(fallback)


def bottom_usable(sample, plausible: bool) -> bool:
    """하의 측정을 렌더에 쓸지. 폴백 정책:

    - 결측이면 기본값 (쓸 것이 없다).
    - 확신이 있으면 측정값 (기존 규칙).
    - 확신이 없어도 그럴듯하면(피부·배경이 아니면) 측정값을 쓴다.
      기본값 #3c4450 은 청색 계열 고정값이라 측정이 없을 때 편향이 크다.
      측정이 피부·배경이 아니면 그 측정이 기본값보다 나을 가능성이 높다.
    - 확신도 없고 그럴듯하지도 않으면 (피부·배경을 잰 것이면) 기본값.
    """
    if sample.missing:
        return False
    return sample.confident or plausible


def _pick_color_sample(samples, plausible: bool):
    """마스크 전용 색(치마/드레스) 우선, 없으면 하의 측정색. 사용 불가면 None."""
    for sample in samples:
        if sample is None or sample.missing:
            continue
        if sample.confident or plausible:
            return sample
    return None


def resolve_colors(observed: ObservedColors) -> dict[str, Color]:
    # 점유율 낮으면(점유율 미달) 측정값이 아니라 기본값으로. 2%짜리 배경색을
    # 머리카락으로 칠하는 일을 막는다. 같은 그림을 보수적으로 그리는 원칙.
    def pick(sample, fallback: str) -> Color:
        if sample.missing or not sample.confident:
            return rgba(fallback)
        return _hex_or(sample.hex, fallback)

    top = pick(observed.top, DEFAULT_TOP)
    return {
        "skin": pick(observed.skin, DEFAULT_SKIN),
        "hair": pick(observed.hair, DEFAULT_HAIR),
        "iris": pick(observed.iris, DEFAULT_IRIS),
        "inner": pick(observed.inner, DEFAULT_INNER),
        "tie": pick(observed.tie, DEFAULT_TIE),
        "shoe": pick(observed.shoe, SHOE),
        "top": top,
        "top_alt": _hex_or(observed.top_alt.hex, DEFAULT_TOP) if not observed.top_alt.missing else shade(top, 0.72),
        "bottom": _hex_or(observed.bottom.hex, DEFAULT_BOTTOM) if bottom_usable(observed.bottom, observed.bottom_plausible) else rgba(DEFAULT_BOTTOM),
    }


def denim_like(rgb: tuple[int, int, int]) -> bool:
    """데님 판정. 소재 속성(파랑)이라 색 절대값을 쓴다. stakes 낮음(렌더 동일)."""
    total = rgb[0] + rgb[1] + rgb[2]
    if total <= 0:
        return False
    r, g, b = (c / total for c in rgb)
    return b - r > 0.06 and b - g > 0.02


def resolve_sleeve(attrs: Attributes, observed: ObservedColors) -> str:
    """VLM 확신값 > S1 측정 > 기본값."""
    if "sleeve_len" not in attrs.coerced and "sleeve_len" not in attrs.missing:
        return attrs.get("sleeve_len")
    cover = observed.cover
    if cover is not None and cover.sleeve_len is not None:
        return cover.sleeve_len
    return attrs.get("sleeve_len")


def resolve_bottom_ex(attrs: Attributes, observed: ObservedColors) -> tuple[str, bool]:
    """VLM 확신값 > S1 증거 > 기본값 (2026-10-28 개정).

    반환: (bottom_garment, 기본값_발동여부). "dress"/"skirt" 는 다리 렌더가
    각각 전체 덮음/측정 밑단으로 처리한다. jeans 기본은 2번째 값이 True.
    """
    def _fallback() -> tuple[str, bool]:
        """쓸 만한 VLM 하의가 없을 때 마스크 증거로 결정한다."""
        if observed.lower_body_clothed:
            # 파서가 바지/치마/드레스를 봤다 → 맨다리로 그리지 않는다.
            if observed.bottom_plausible and not observed.bottom.missing:
                return "pants", False
            return "jeans", True
        if observed.lower_body_bare:
            return "none", False  # 진짜 맨다리 (설계 D3)
        if observed.fullbody:
            return "none", False  # 전신인데 증거 없음 — 보수적으로 피부 유지
        return "jeans", True      # 상반신/판단 불가 — 기본 청바지

    if attrs.get("top_garment") == "dress":
        return "dress", False

    if "bottom_garment" in attrs.coerced or "bottom_garment" in attrs.missing:
        cover = observed.cover
        if cover is not None and cover.bottom_len == "long":
            return "jeans" if denim_like(observed.bottom.rgb) else "pants", False
        if cover is not None and cover.bottom_len == "short":
            return "shorts", False
        return _fallback()

    value = attrs.get("bottom_garment")
    if value == "none":
        return _fallback()
    if value == "skirt":
        return "skirt", False
    return value, False


def resolve_bottom(attrs: Attributes, observed: ObservedColors) -> str:
    return resolve_bottom_ex(attrs, observed)[0]


def effective_pattern(pattern: str, observed: ObservedColors, attrs: Attributes, degrade: tuple[str, ...]) -> str:
    """보수화: 확신 없거나 화질 저하이면 무늬를 plain으로 접는다.

    우선순위: VLM 확신값 > S1 측정 줄무늬 > plain. VLM이 답을 안 했고
    측정 줄무늬가 있으면 그걸 쓴다 (VLM 미연결 시 resemblance 직결).
    측정은 degrade를 안 본다: 방향 테스트·점유율이 자체 신뢰도라서
    얼굴이 작아도 몸통 픽셀이 충분하면(메시 7056px) 통과한다.

    VLM 확신 plain 은 측정 줄무늬를 끈다. 측정은 "두 색+방향"만 보므로
    겹쳐 입은 두 벌(자켓+원피스)을 줄무늬로 착각한다. 크롭 전체를 본
    VLM 의 plain 확신이 있으면 그쪽이 맞다.
    """
    vlm_says_plain = (
        pattern == "plain"
        and "pattern" not in attrs.coerced
        and "pattern" not in attrs.missing
        and observed.top_confident
        and not any(d in degrade for d in CONSERVATIVE_DEGRADE)
    )
    if vlm_says_plain:
        return "plain"
    vlm_confident = (
        pattern != "plain"
        and "pattern" not in attrs.coerced
        and "pattern" not in attrs.missing
        and observed.top_confident
        and not any(d in degrade for d in CONSERVATIVE_DEGRADE)
    )
    if vlm_confident:
        return pattern
    measured = (
        observed.stripe != "plain"
        and not observed.top_alt.missing
        and observed.top_confident
    )
    if measured:
        return observed.stripe
    return "plain"


def _mix(a: Color, b: Color, t: float) -> Color:
    """두 색을 t:(1-t)로 섞는다 (수염 stubble — 머리색과 피부의 중간)."""
    return (
        int(round(a[0] * t + b[0] * (1 - t))),
        int(round(a[1] * t + b[1] * (1 - t))),
        int(round(a[2] * t + b[2] * (1 - t))),
        a[3],
    )


def _shaded_face(canvas: SkinCanvas, part: str, face_name: str, base: Color, layer: int = 0) -> None:
    canvas.fill_face(part, face_name, shade(base, FACE_SHADE[face_name]), layer)


def render_head(canvas: SkinCanvas, colors: dict[str, Color], attrs: Attributes, stencil=None, style: str = "short") -> None:
    skin_c, hair_c = colors["skin"], colors["hair"]
    if stencil is None:
        from .hairstencil import rule_stencil

        stencil = rule_stencil(attrs.get("hair_length"))  # 오늘의 길이 규칙 (골든 해시와 픽셀 동일)

    # 베이스는 피부로 전부 채운 뒤 머리카락을 덮는다 (HEAD layer=0만).
    for face_name in canvas.layout.part("head", 0).faces:
        _shaded_face(canvas, "head", face_name, skin_c, 0)

    # 정수리: rule은 항상 머리(가마), mask 스텐신은 대머리에서 피부.
    if stencil.top_hair:
        canvas.fill_face("head", "top", shade(hair_c, FACE_SHADE["top"]), 0)

    front = canvas.layout.face("head", "front", 0)
    for v, row in enumerate(stencil.front):
        for u, is_hair in enumerate(row):
            if is_hair:
                canvas.put("head", "front", u, v, shade(hair_c, FACE_SHADE["front"]), 0)

    # 옆/뒤 커버리지: rule은 길이 표, mask는 앞 실루엣 추론 (긴 머리는 뒤까지).
    for face_name in ("right", "left", "back"):
        profile = stencil.side_profiles.get(face_name, ())
        f = canvas.layout.face("head", face_name, 0)
        for u, rows in enumerate(profile[:f.w]):
            for v in range(min(rows, f.h)):
                canvas.put("head", face_name, u, v, shade(hair_c, FACE_SHADE[face_name]), 0)

    # 머리 아래(bottom): 뒤통수/옆머리 footprint. v0=앞(턱)은 피부 유지.
    rear = HS.bottom_rear_rows(attrs.get("hair_length"), stencil)
    for v in range(HEAD_GRID := 8):
        if v < HEAD_GRID - rear:
            continue
        for u in range(HEAD_GRID):
            if stencil.bottom[v][u]:
                canvas.put("head", "bottom", u, v, shade(hair_c, FACE_SHADE["bottom"]), 0)

    # 스타일 앞머리: full-fringe 는 3-4행 전체를 채워 마스크 구멍/피부선을 막는다.
    # ponytail/bun(2행)은 이마를 드러내는 스타일이라 강제로 덮지 않는다.
    bangs = HS.style_bangs(style)
    if bangs >= 3:
        cols = range(0, 8) if bangs >= 4 else range(1, 7)
        for v in range(min(bangs, 4)):
            for u in cols:
                canvas.put("head", "front", u, v, shade(hair_c, FACE_SHADE["front"]), 0)

    # 얼굴 특징 (사용자 결정 2026-10-20): 눈 4-5행, 입 없음, 수염은 턱 6-7행.
    # 홍채색은 사진 측정값 (없으면 템플릿 갈색).
    sclera = rgba("#f2f2f2")
    iris_c = colors["iris"]
    for base_u in (1, 5):
        canvas.put("head", "front", base_u, 4, sclera, 0)
        canvas.put("head", "front", base_u + 1, 4, iris_c, 0)
        canvas.put("head", "front", base_u, 5, iris_c, 0)
        canvas.put("head", "front", base_u + 1, 5, iris_c, 0)
    beard = attrs.get("beard")
    if beard == "full":
        beard_c = shade(hair_c, FACE_SHADE["front"])
        for v in (6, 7):
            for u in range(8):
                canvas.put("head", "front", u, v, beard_c, 0)
    elif beard == "stubble":
        beard_c = _mix(shade(hair_c, FACE_SHADE["front"]), shade(skin_c, FACE_SHADE["front"]), 0.55)
        for u in (0, 1, 6, 7):
            canvas.put("head", "front", u, 6, beard_c, 0)
        for u in range(8):
            canvas.put("head", "front", u, 7, beard_c, 0)

    # HEAD ACC.(layer=1)는 손대지 않는다. 기본 투명 유지.


def _pattern_color(base: Color, alt: Color | None, u: int, v: int, w: int, h: int, pattern: str, face_name: str,
                   thickness: int = 1) -> Color:
    """패턴 픽셀. thickness 는 줄/격자 두께(px) — 기본 1px, 측정값 1-3 (2026-10-28).

    graphic 은 세부 정보가 없으므로 여기서 아무것도 그리지 않는다. 실제 무늬는
    크롭 텍스처(Phase 3)가 공급하고, 없으면 측정 상의색 단색으로 접힌다.
    """
    shaded = shade(base, FACE_SHADE[face_name])
    if pattern == "plain":
        return shaded
    t = max(1, int(thickness))
    secondary = shade(alt, FACE_SHADE[face_name]) if alt is not None else shade(base, 0.72)
    if pattern == "vertical_stripe":
        return secondary if (u // t) % 2 == 1 else shaded
    if pattern == "horizontal_stripe":
        return secondary if (v // t) % 2 == 1 else shaded
    if pattern == "check":
        return secondary if ((u // t) + (v // t)) % 2 == 1 else shaded
    if pattern == "plaid":
        if ((u // t) + (v // t)) % 2 == 1:
            return secondary
        return shade(base, 1.08) if u % (2 * t) == 0 else shaded
    if pattern == "graphic":
        return shaded
    return shaded


def render_body(
    canvas: SkinCanvas,
    colors: dict[str, Color],
    attrs: Attributes,
    pattern: str,
    alt: Color | None = None,
    hair_stencil=None,
    thickness: int = 1,
    texture: FabricTexture | None = None,
) -> None:
    top_garment = attrs.get("top_garment")
    base = colors["skin"] if top_garment == "none" else colors["top"]
    # 상의 크롭은 VLM pattern 이 복잡할 때만 — 흰 셔츠 주름(HF 10.2)이
    # plain 인데도 크롭되던 오탐을 막는다. 하의는 pattern 필드가 없어 HF 게이트.
    use_texture = texture is not None and pattern in COMPLEX_PATTERNS
    # dress는 상의색 그대로. overalls/uniform/apron도 v1은 단색 베이스.
    for face_name in canvas.layout.part("body", 0).faces:
        f = canvas.layout.face("body", face_name, 0)
        # 75% 규칙: graphic은 앞면만, 뒷면·측면은 plain.
        front_only = pattern == "graphic" and face_name != "front"
        p = pattern if not front_only else "plain"
        if use_texture and not front_only:
            tile = texture.body.resize((f.w, f.h), Image.NEAREST)
            for v in range(f.h):
                for u in range(f.w):
                    c = shade(tile.getpixel((u, v)) + (255,), FACE_SHADE[face_name])
                    canvas.put("body", face_name, u, v, c, 0)
        else:
            for v in range(f.h):
                for u in range(f.w):
                    canvas.put("body", face_name, u, v, _pattern_color(base, alt, u, v, f.w, f.h, p, face_name, thickness), 0)
    if top_garment != "none":
        if attrs.get("inner_top") != "none":
            # 겹쳐 입은 상의 (2026-10-21): 목 V·라펠에 안쪽 옷, 타이 1px.
            inner_c = colors["inner"]
            tie_c = colors["tie"] if attrs.get("neckwear") == "tie" else None
            for u in (3, 4):
                for v in (0, 1):
                    try:
                        canvas.put("body", "front", u, v, inner_c, 0)
                    except ValueError:
                        continue
            for u, c in ((3, inner_c), (4, tie_c or inner_c)):
                try:
                    canvas.put("body", "front", u, 2, c, 0)
                except ValueError:
                    continue
            if tie_c is not None:
                try:
                    canvas.put("body", "front", 4, 1, tie_c, 0)  # 매듭
                except ValueError:
                    pass
        else:
            # 목 (앞 상단 중앙 2px) — 셔츠 위 맨살.
            for u in (3, 4):
                for v in (0, 1):
                    try:
                        canvas.put("body", "front", u, v, shade(colors["skin"], 0.86), 0)
                    except ValueError:
                        continue

    apply_structure(canvas, attrs, colors)

    # 관측된 긴 머리만 몸통으로 연장한다. 뒷면/옆면은 턱 아래 마스크 길이,
    # 앞면은 셔츠 중앙을 가리지 않도록 양쪽 바깥 2열에 어깨 가닥만 그린다.
    back_rows = min(12, max(0, getattr(hair_stencil, "back_body_rows", 0)))
    front_rows = min(12, max(0, getattr(hair_stencil, "front_body_rows", 0)))
    if back_rows or front_rows:
        hair_c = colors["hair"]
        for face_name in ("back", "right", "left"):
            f = canvas.layout.face("body", face_name, 0)
            for v in range(min(back_rows, f.h)):
                for u in range(f.w):
                    canvas.put("body", face_name, u, v, shade(hair_c, FACE_SHADE[face_name]), 0)

        front = canvas.layout.face("body", "front", 0)
        for v, cols in enumerate(HS.front_lock_profile(front_rows)):
            for u in cols:
                if v < front.h:
                    canvas.put("body", "front", u, v, shade(hair_c, FACE_SHADE["front"]), 0)


def render_arms(canvas: SkinCanvas, colors: dict[str, Color], attrs: Attributes, pattern: str, sleeve: str | None = None) -> None:
    top_garment = attrs.get("top_garment")
    sleeve = sleeve or attrs.get("sleeve_len")
    shirt_end = SLEEVE_ROWS.get(sleeve, 3)
    shirt_base = colors["top"] if top_garment != "none" else None
    for part in ("r_arm", "l_arm"):
        for face_name in canvas.layout.part(part, 0).faces:
            f = canvas.layout.face(part, face_name, 0)
            if f.h < 12:
                # top/bottom 면(4×4): 셔츠 있으면 셔츠, 없으면 피부.
                _shaded_face(canvas, part, face_name, shirt_base if shirt_base else colors["skin"], 0)
                continue
            for v in range(f.h):
                is_shirt = shirt_base is not None and v <= shirt_end
                # 무늬는 소매에 넣지 않는다 (4px 폭에 깨진다). 단색 + 구분선.
                if is_shirt and v == shirt_end and shirt_end < f.h - 1 and sleeve not in ("long", "none"):
                    c = shade(shirt_base, 0.66)
                elif is_shirt:
                    c = shade(shirt_base, FACE_SHADE[face_name])
                else:
                    c = shade(colors["skin"], FACE_SHADE[face_name])
                for u in range(f.w):
                    canvas.put(part, face_name, u, v, c, 0)
    _render_cuffs(canvas, colors, attrs, sleeve)


def _render_cuffs(canvas: SkinCanvas, colors: dict[str, Color], attrs: Attributes, sleeve: str) -> None:
    """겹쳐 입은 상의: 긴/3-4 소매 끝행에 안쪽 옷(셔츠 커프스)이 보인다 (2026-10-21)."""
    if attrs.get("inner_top") == "none" or sleeve not in ("long", "three_quarter"):
        return
    row = SLEEVE_ROWS.get(sleeve, -1)
    if row < 0:
        return
    for part in ("r_arm", "l_arm"):
        for face_name in ("front", "back", "right", "left"):
            f = canvas.layout.face(part, face_name, 0)
            for u in range(f.w):
                canvas.put(part, face_name, u, min(row, f.h - 1), shade(colors["inner"], FACE_SHADE[face_name]), 0)


def render_legs(canvas: SkinCanvas, colors: dict[str, Color], attrs: Attributes, bottom_garment: str | None = None, *, shoe_two_tone: bool = True,
                skirt_rows: int | None = None, pattern: str | None = None, alt: Color | None = None,
                texture: FabricTexture | None = None) -> None:
    """다리 레이어. jeans/pants/shorts/none 은 기존 경로 그대로 (2026-10-28).

    - dress: 0-8행을 드레스 천으로 연속 채움 (패턴은 몸통에서 이어짐).
    - skirt: 측정된 밑단(skirt_rows)까지만 치마색, 그 아래는 맨다리.
    - complex texture (Phase 3): 크롭 천이 있으면 옷 행을 그 픽셀로 채운다.
    """
    bottom_garment = bottom_garment or attrs.get("bottom_garment")
    pants_c = colors["bottom"]
    use_texture = texture is not None and texture.usable

    def shoe_color(face_name: str, v: int, fh: int) -> Color:
        c = shade(colors["shoe"], FACE_SHADE[face_name])
        if shoe_two_tone:
            # 2톤 신발 (폴리시 C): 바닥 행은 어둡게, 나머지는 밝게.
            return shade(c, 0.62) if v == fh - 1 else shade(c, 1.35)
        return c

    def fabric_color(part: str, face_name: str, u: int, v: int, f) -> Color:
        if use_texture:
            tile = texture.leg.resize((f.w, f.h), Image.NEAREST)
            return shade(tile.getpixel((u, v)) + (255,), FACE_SHADE[face_name])
        return shade(pants_c, FACE_SHADE[face_name])

    if bottom_garment == "dress":
        for part in ("r_leg", "l_leg"):
            for face_name in canvas.layout.part(part, 0).faces:
                f = canvas.layout.face(part, face_name, 0)
                if f.h < 12:
                    if use_texture:
                        tile = texture.leg.resize((f.w, f.h), Image.NEAREST)
                        for v in range(f.h):
                            for u in range(f.w):
                                canvas.put(part, face_name, u, v, shade(tile.getpixel((u, v)) + (255,), FACE_SHADE[face_name]), 0)
                    else:
                        _shaded_face(canvas, part, face_name, pants_c, 0)
                    continue
                for v in range(f.h):
                    if v >= 9:
                        for u in range(f.w):
                            canvas.put(part, face_name, u, v, shoe_color(face_name, v, f.h), 0)
                        continue
                    for u in range(f.w):
                        if use_texture:
                            c = fabric_color(part, face_name, u, v, f)
                        else:
                            c = _pattern_color(pants_c, alt, u, v + 12, f.w, f.h, pattern or "plain", face_name)
                        if v == 8:  # 밑단 그림자
                            c = shade(c, 0.82)
                        canvas.put(part, face_name, u, v, c, 0)
        return

    if bottom_garment == "skirt":
        rows = max(1, min(9, skirt_rows if skirt_rows is not None else DEFAULT_SKIRT_ROWS))
        for part in ("r_leg", "l_leg"):
            for face_name in canvas.layout.part(part, 0).faces:
                f = canvas.layout.face(part, face_name, 0)
                if f.h < 12:
                    if use_texture:
                        tile = texture.leg.resize((f.w, f.h), Image.NEAREST)
                        for v in range(f.h):
                            for u in range(f.w):
                                canvas.put(part, face_name, u, v, shade(tile.getpixel((u, v)) + (255,), FACE_SHADE[face_name]), 0)
                    else:
                        _shaded_face(canvas, part, face_name, pants_c, 0)
                    continue
                for v in range(f.h):
                    if v >= 9:
                        c = shoe_color(face_name, v, f.h)
                    elif v < rows:
                        c = fabric_color(part, face_name, 0, v, f) if use_texture else shade(pants_c, FACE_SHADE[face_name])
                        if use_texture:
                            # fabric_color is per-column; compute per u below
                            pass
                        if v == rows - 1:  # 밑단 그림자
                            c = shade(c, 0.82)
                    else:
                        c = shade(colors["skin"], FACE_SHADE[face_name])
                    for u in range(f.w):
                        if use_texture and v < rows and v < 9:
                            cu = fabric_color(part, face_name, u, v, f)
                            if v == rows - 1:
                                cu = shade(cu, 0.82)
                            canvas.put(part, face_name, u, v, cu, 0)
                        else:
                            canvas.put(part, face_name, u, v, c, 0)
        return

    pants_end, shoe_start = BOTTOM_ROWS.get(bottom_garment, (11, 9))
    for part in ("r_leg", "l_leg"):
        for face_name in canvas.layout.part(part, 0).faces:
            f = canvas.layout.face(part, face_name, 0)
            if f.h < 12:
                if use_texture and pants_end >= 0:
                    tile = texture.leg.resize((f.w, f.h), Image.NEAREST)
                    for v in range(f.h):
                        for u in range(f.w):
                            canvas.put(part, face_name, u, v, shade(tile.getpixel((u, v)) + (255,), FACE_SHADE[face_name]), 0)
                else:
                    _shaded_face(canvas, part, face_name, pants_c if pants_end >= 0 else colors["skin"], 0)
                continue
            for v in range(f.h):
                if v >= shoe_start:
                    c = shoe_color(face_name, v, f.h)
                elif v <= pants_end:
                    c = fabric_color(part, face_name, 0, v, f) if use_texture else shade(pants_c, FACE_SHADE[face_name])
                else:
                    c = shade(colors["skin"], FACE_SHADE[face_name])
                if v == pants_end and 0 <= pants_end < shoe_start - 1 and not use_texture:
                    c = shade(pants_c, 0.66)
                for u in range(f.w):
                    if use_texture and pants_end >= 0 and pants_end >= v and v < shoe_start:
                        cu = fabric_color(part, face_name, u, v, f)
                        canvas.put(part, face_name, u, v, cu, 0)
                    else:
                        canvas.put(part, face_name, u, v, c, 0)


# L2 는 L1 위의 하이라이트 셸이다 (2026-10-27 개정). 실루엣 전체를 복제하면
# 머리가 불투명 블록으로 보인다. 색은 한 톤만 쓴다 — 열마다 밝기를 바꾸면
# 머리에 규칙적인 세로 줄무늬가 생긴다 (2026-10-31 제거).
L2_LIFT = 1.05


def _l2_color(hair_c: Color, face_name: str) -> Color:
    """L2 셸 색: L1 음영을 5%만 들어올린 균일 톤 (열 stripes 없음)."""
    return shade(shade(hair_c, FACE_SHADE[face_name]), L2_LIFT)


def render_hair_overlay(canvas: SkinCanvas, colors: dict[str, Color], stencil, hair_length: str = "short", style: str = "short") -> None:
    """L2(오버레이) 헤어 (2026-10-29 개정: solid shell, no alpha holes).

    L1 실루엣과 같은 셀을 모두 채운다. 틈(1px hole)을 두지 않고 균일한 5%
    리프트만 준다. 열별 2톤은 규칙적인 세로 줄무늬를 만들어 제거했다.
    """
    hair_c = colors["hair"]
    length = HS.effective_hair_length(hair_length, stencil)

    def put(part: str, face_name: str, u: int, v: int) -> None:
        canvas.put(part, face_name, u, v, _l2_color(hair_c, face_name), 1)

    if stencil.top_hair:
        top = canvas.layout.face("head", "top", 1)
        for v in range(top.h):
            for u in range(top.w):
                put("head", "top", u, v)

    # 앞면: L1 앞머리 셀 전체 + 긴 머리 프린지. 눈(4-5행)은 stencil 이 막는다.
    front = canvas.layout.face("head", "front", 1)
    for v, row in enumerate(stencil.front):
        for u, is_hair in enumerate(row[: front.w]):
            if is_hair:
                put("head", "front", u, v)
    bangs = HS.style_bangs(style)
    if bangs >= 3:
        cols = range(0, 8) if bangs >= 4 else range(1, 7)
        for v in range(min(bangs, 4)):
            for u in cols:
                put("head", "front", u, v)

    # 옆/뒤: 실루엣의 모든 열을 채운다 (구멍 없음).
    for face_name in ("right", "back", "left"):
        profile = stencil.side_profiles.get(face_name, ())
        f = canvas.layout.face("head", face_name, 1)
        for u, rows in enumerate(profile[: f.w]):
            for v in range(min(f.h, rows)):
                put("head", face_name, u, v)

    # 머리 아래: L1 과 같은 footprint, 뒤쪽 행만.
    bottom = canvas.layout.face("head", "bottom", 1)
    rear = HS.bottom_rear_rows(hair_length, stencil)
    for v in range(bottom.h):
        if v < bottom.h - rear:
            continue
        for u in range(bottom.w):
            if stencil.bottom[v][u]:
                put("head", "bottom", u, v)

    # 몸통 드레이프: solid rows (checker 금지). 스타일별 강조를 덧칠한다.
    body_rows = min(12, max(0, getattr(stencil, "back_body_rows", 0)))
    front_rows = min(12, max(0, getattr(stencil, "front_body_rows", 0)))
    if body_rows:
        for face_name in ("back", "right", "left"):
            f = canvas.layout.face("body", face_name, 1)
            for v in range(min(body_rows, f.h)):
                for u in range(f.w):
                    put("body", face_name, u, v)
    if front_rows:
        f = canvas.layout.face("body", "front", 1)
        for v, cols in enumerate(HS.front_lock_profile(front_rows)):
            for u in cols:
                if v < f.h:
                    put("body", "front", u, v)

    # 롱 웨이브: 몸통 끝단을 열마다 1행씩 더 내려 물결 실루엣 (L1 위 추가 셸).
    if style == "long_wavy":
        back = canvas.layout.face("body", "back", 1)
        extra = min(6, body_rows + 1)
        for u in range(back.w):
            if body_rows < 6 and u % 3 == 0:
                for v in range(body_rows, extra):
                    put("body", "back", u, v)

    # 포니테일: 몸통 뒤 중앙 2열에 꼬리 strip. L1 드레이프는 0.
    if style == "ponytail":
        back = canvas.layout.face("body", "back", 1)
        for v in range(min(5, back.h)):
            for u in (3, 4):
                put("body", "back", u, v)

    # 번: 뒤통수 상단 4×3 밝은 덩어리. L1/실루엣은 그대로, L2 음영으로 묶음 표현.
    if style == "bun":
        back = canvas.layout.face("head", "back", 1)
        bun_c = shade(hair_c, FACE_SHADE["back"] * 1.35)
        for v in range(3):
            for u in range(2, 6):
                canvas.put("head", "back", u, v, bun_c, 1)


def render(
    observed: ObservedColors,
    attrs: Attributes,
    degrade: tuple[str, ...] = (),
    model: str = "classic",
    *,
    noise_seed: int | None = None,
    noise_level: float = 1.0,
    shoe_two_tone: bool = True,
) -> SkinCanvas:
    """S3 진입점. 입력 3개 → 검증 통과하는 캔버스 1개.

    noise_seed가 주어지면 마지막에 이산 톤 밴딩 패스 (설계 §2: 거울 대칭·결정론).
    noise_level은 세기 배율 (§9): 0=무노이즈와 바이트 동일, 1=현행. 시드에 안 들어간다
    (패턴 불변). shoe_two_tone=False는 Edit Skin 토글 OFF 변형 (구 단색 신발 블록).
    """
    canvas = SkinCanvas(model)
    colors = resolve_colors(observed)
    # 겉옷색 구조: 재킷류/레이어드는 배경 제거 겉옷 표본 우선 (정장의 흰 셔츠 오염 대응).
    if (
        (attrs.get("inner_top") != "none" or attrs.get("top_garment") in JACKET_LIKE)
        and not observed.outer.missing
    ):
        colors["top"] = _hex_or(observed.outer.hex, DEFAULT_TOP)
    # 승인 규칙: 타이는 색이 실제로 측정된 경우에만 그린다 — 아니면 셔츠로 채운다.
    if attrs.get("neckwear") == "tie" and (observed.tie.missing or not observed.tie.confident):
        colors["tie"] = colors["inner"]
    resolved_bottom, bottom_is_default = resolve_bottom_ex(attrs, observed)
    if bottom_is_default:
        # 하체 미관측 jeans 기본: 관측 '하의' 샘플은 오탐(셔츠 꼬리 등)이므로
        # 측정색 대신 클래식 데님 청색을 쓴다 (사용자 결정 2026-10-13).
        colors["bottom"] = rgba(DEFAULT_JEANS)
    elif resolved_bottom == "dress":
        # 원피스: Dress(7) 마스크 색 > 하의 측정색 > 상의(드레스) 색.
        sample = _pick_color_sample(
            (observed.dress_sample, observed.bottom), observed.bottom_plausible
        )
        colors["bottom"] = _hex_or(sample.hex, DEFAULT_BOTTOM) if sample is not None else colors["top"]
    elif resolved_bottom == "skirt":
        # 치마: Skirt(5) 마스크 색 우선 — 바지 클래스가 맨다리를 덮어도
        # 하의색이 피부색으로 오염되지 않는다 (image405 2026-10-28).
        sample = _pick_color_sample(
            (observed.skirt_sample, observed.dress_sample, observed.bottom),
            observed.bottom_plausible,
        )
        if sample is not None:
            colors["bottom"] = _hex_or(sample.hex, DEFAULT_BOTTOM)
    pattern = effective_pattern(attrs.get("pattern"), observed, attrs, tuple(degrade))
    # 측정 2색(줄무늬)이 있을 때만 실측 보조색. 없으면 합성 음영.
    alt = colors["top_alt"] if not observed.top_alt.missing and pattern in ("vertical_stripe", "horizontal_stripe") else None
    observed_stencil = observed.hair_stencil
    hair_stencil = observed_stencil
    if hair_stencil is None:
        hair_stencil = HS.rule_stencil(attrs.get("hair_length"))
    style_value = attrs.get("hair_style")
    if "hair_style" in attrs.missing or "hair_style" in attrs.coerced:
        style_value = ""
    style = HS.effective_hair_style(style_value, attrs.get("hair_length"), hair_stencil)
    front_rows, back_rows = HS.style_drape(style)
    # rule stencil 의 body_rows 는 길이 규칙이지 관측 증거가 아니다.
    evidence = min(12, max(0, hair_stencil.body_rows)) if observed_stencil is not None else 0
    # 마스크 증거는 뒤 드레이프를 최대 1행만 늘린다. 12행 전체를 덮지 않는다.
    back_rows = min(6, max(back_rows, min(evidence, back_rows + 1))) if back_rows else 0
    hair_stencil = replace(hair_stencil, body_rows=back_rows,
                           front_body_rows=front_rows, back_body_rows=back_rows)
    render_head(canvas, colors, attrs, hair_stencil, style=style)
    thickness = observed.stripe_px if pattern in ("vertical_stripe", "horizontal_stripe", "check", "plaid") else 1
    render_body(canvas, colors, attrs, pattern, alt, hair_stencil, thickness,
                texture=observed.top_texture)
    render_arms(canvas, colors, attrs, pattern, resolve_sleeve(attrs, observed))
    render_legs(
        canvas, colors, attrs, resolved_bottom, shoe_two_tone=shoe_two_tone,
        skirt_rows=observed.skirt_hem_rows, pattern=pattern, alt=alt,
        texture=observed.bottom_texture,
    )
    if observed.hair_overlay:
        render_hair_overlay(canvas, colors, hair_stencil, attrs.get("hair_length"), style)
    if noise_seed is not None:
        _apply_noise(canvas, noise_seed, noise_level)
    return canvas


# --- 텍스처 노이즈 (스티브류 밴딩; docs/specs/2026-10-12-skin-noise-editor-design.md) ---

NOISE_STEPS: tuple[float, ...] = (0.92, 0.96, 1.0, 1.08)
# eval 프로브 톨러런스: |NOISE_STEPS - 1.0| 최대 0.08 → 채널 최대 드리프트
# round((1 - 0.92) * 255) ≈ 20, 밝기 끝 round((255-255*(1-1.08)*... 상향 여유 → 32 고정.
NOISE_TOL = 32
# 개정 (2026-10-12 사용자 피드백): 노이즈 적용은 좌우 비대칭·불규칙이다.
# 단일 전면 계수 대신 면(face)별 rng 시드로 가변 pitch(1~3px) 파절 + 단계 무작위.
NOISE_CELL_WEIGHTS = ((1.0, 6.0), (0.96, 2.0), (0.92, 1.5), (1.08, 1.5))  # 합계 11


def derive_noise_seed(
    observed: ObservedColors,
    attrs: Attributes,
    degrade: tuple[str, ...] = (),
    index: int = 0,
) -> int:
    """저장 후보 내용에서 결정론 시드. 같은 후보는 언제나 같은 텍스처 (설계 §8.3)."""
    colors = resolve_colors(observed)
    payload = json.dumps({
        "colors": sorted([k, list(v)] for k, v in colors.items()),
        "attrs": sorted(attrs.values.items()),
        "degrade": list(degrade),
        "index": index,
    }, sort_keys=True, default=str)
    return int(hashlib.sha256(payload.encode()).hexdigest()[:16], 16)


def _noise_step(rng: random.Random) -> float:
    x = rng.random() * sum(w for _, w in NOISE_CELL_WEIGHTS)
    cum = 0.0
    for k, w in NOISE_CELL_WEIGHTS:
        cum += w
        if x < cum:
            return k
    return 1.0


def _scaled_step(step: float, level: float) -> float:
    """세기 배율 (설계 §9): s → 1 + (s-1)·level. 0=무노이즈, 1=현행, 패턴 불변."""
    return 1.0 + (step - 1.0) * level


def _apply_noise(canvas: SkinCanvas, seed: int, level: float = 1.0) -> None:
    """면 단위 rng로 불규칙 파절(1~3px) 밴딩. 계수 추출 시 u를 거울 정규화하지
    않으므로 좌우 팔다리는 독립적인 무늬를 얻는다 (기저색은 여전히 대칭, 노이즈만
    비대칭 — validate mirror는 NOISE_TOL 톨러런스로 판정한다).
    level은 계수 크기만 배율한다 (0=무노이즈, 1=현행) — 패턴은 시드에만 의존."""
    px = canvas.image.load()
    for part in canvas.layout.parts.values():
        role = part.name[2:] if part.name.startswith(("l_", "r_")) else part.name
        for fname, face in part.faces.items():
            key = hashlib.md5(f"{seed}|{part.name}|{fname}".encode()).digest()
            rng = random.Random(int.from_bytes(key[:8], "little"))
            assigned: set[tuple[int, int]] = set()
            grid: dict[tuple[int, int], float] = {}
            for v in range(face.h):
                for u in range(face.w):
                    if (v, u) in assigned:
                        continue
                    value = _noise_step(rng)
                    r = rng.random()
                    pitch = 1 if r < 0.35 else (2 if r < 0.85 else 3)
                    for vv in range(v, min(face.h, v + pitch)):
                        for uu in range(u, min(face.w, u + pitch)):
                            grid[(vv, uu)] = value
                            assigned.add((vv, uu))
            for v in range(face.h):
                for u in range(face.w):
                    k = _scaled_step(grid[(v, u)], level)
                    if k == 1.0:
                        continue
                    x, y = face.x + u, face.y + v
                    r, g, b, a = px[x, y]
                    if a == 0:
                        continue
                    px[x, y] = shade((r, g, b, a), k)
    return
