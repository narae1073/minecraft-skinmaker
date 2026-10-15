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

from .attributes import Attributes
from .canvas import Color, SkinCanvas, rgba, shade
from .colors import MISSING, ObservedColors
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
    "none": (-1, 9),
}

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
    """VLM 확신값 > S1 측정(길이만) > 기본값. 측정은 스타일이 아니라 길이만 본다.

    반환: (bottom_garment, 하체미관측_기본_발동여부). 발동 시 렌더가 jeans 기본색
    (#3b5a86)을 쓴다 — 상반신 사진의 관측 '하의' 샘플은 셔츠 꼬리 같은 오탐이다.
    """
    seen = observed.lower_body_seen
    def _default(v: str) -> tuple[str, bool]:
        # 맨다리가 보이는 전신 사진은 none 유지 (D3); 드레스는 밑단 가림 (가드).
        if v == "none" and seen is False and attrs.get("top_garment") != "dress":
            return "jeans", True
        return v, False
    if "bottom_garment" not in attrs.coerced and "bottom_garment" not in attrs.missing:
        return _default(attrs.get("bottom_garment"))
    cover = observed.cover
    if cover is not None and cover.bottom_len == "long":
        return "jeans" if denim_like(observed.bottom.rgb) else "pants", False
    if cover is not None and cover.bottom_len == "short":
        return "shorts", False
    return _default(attrs.get("bottom_garment"))


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


def _shaded_face(canvas: SkinCanvas, part: str, face_name: str, base: Color, layer: int = 0) -> None:
    canvas.fill_face(part, face_name, shade(base, FACE_SHADE[face_name]), layer)


def render_head(canvas: SkinCanvas, colors: dict[str, Color], attrs: Attributes, stencil=None) -> None:
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

    # 얼굴 특징 (고정 템플릿, v1 enum 없음): 눈 2×2, 입 4×1
    sclera = rgba("#f2f2f2")
    iris = rgba("#3b2a1a")
    for base_u in (1, 5):
        canvas.put("head", "front", base_u, 3, sclera, 0)
        canvas.put("head", "front", base_u + 1, 3, iris, 0)
        canvas.put("head", "front", base_u, 4, iris, 0)
        canvas.put("head", "front", base_u + 1, 4, iris, 0)
    for u in range(2, 6):
        canvas.put("head", "front", u, 6, shade(skin_c, 0.72), 0)

    # HEAD ACC.(layer=1)는 손대지 않는다. 기본 투명 유지.


def _pattern_color(base: Color, alt: Color | None, u: int, v: int, w: int, h: int, pattern: str, face_name: str) -> Color:
    shaded = shade(base, FACE_SHADE[face_name])
    if pattern == "plain":
        return shaded
    secondary = shade(alt, FACE_SHADE[face_name]) if alt is not None else shade(base, 0.72)
    if pattern == "vertical_stripe":
        return secondary if (u // 2) % 2 == 1 else shaded
    if pattern == "horizontal_stripe":
        return secondary if (v // 2) % 2 == 1 else shaded
    if pattern == "check":
        return secondary if ((u // 2) + (v // 2)) % 2 == 1 else shaded
    if pattern == "plaid":
        if ((u // 2) + (v // 2)) % 2 == 1:
            return secondary
        return shade(base, 1.08) if u % 4 == 0 else shaded
    if pattern == "graphic":
        # 앞면 가슴 프린트만. 뒷면은 호출자가 plain으로 넘긴다.
        if 2 <= u < w - 2 and 4 <= v < 8:
            return shade(rgba("#f2f2f2"), FACE_SHADE[face_name])
        return shaded
    return shaded


def render_body(
    canvas: SkinCanvas,
    colors: dict[str, Color],
    attrs: Attributes,
    pattern: str,
    alt: Color | None = None,
    hair_stencil=None,
) -> None:
    top_garment = attrs.get("top_garment")
    base = colors["skin"] if top_garment == "none" else colors["top"]
    # dress는 상의색 그대로. overalls/uniform/apron도 v1은 단색 베이스.
    for face_name in canvas.layout.part("body", 0).faces:
        f = canvas.layout.face("body", face_name, 0)
        # 75% 규칙: graphic은 앞면만, 뒷면·측면은 plain.
        p = pattern if not (pattern == "graphic" and face_name in ("back", "right", "left", "top", "bottom")) else "plain"
        for v in range(f.h):
            for u in range(f.w):
                canvas.put("body", face_name, u, v, _pattern_color(base, alt, u, v, f.w, f.h, p, face_name), 0)
    if top_garment != "none":
        # 목 (앞 상단 중앙 2px) — 셔츠 위 맨살.
        for u in (3, 4):
            for v in (0, 1):
                try:
                    canvas.put("body", "front", u, v, shade(colors["skin"], 0.86), 0)
                except ValueError:
                    continue

    # 관측된 긴 머리만 몸통으로 연장한다. 뒷면/옆면은 턱 아래 마스크 길이,
    # 앞면은 셔츠 중앙을 가리지 않도록 양쪽 바깥 2열에 어깨 가닥만 그린다.
    body_rows = min(12, max(0, getattr(hair_stencil, "body_rows", 0)))
    if body_rows:
        hair_c = colors["hair"]
        for face_name in ("back", "right", "left"):
            f = canvas.layout.face("body", face_name, 0)
            for v in range(min(body_rows, f.h)):
                for u in range(f.w):
                    canvas.put("body", face_name, u, v, shade(hair_c, FACE_SHADE[face_name]), 0)

        front = canvas.layout.face("body", "front", 0)
        for v in range(min(2, body_rows, front.h)):
            for u in (0, 1, front.w - 2, front.w - 1):
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


def render_legs(canvas: SkinCanvas, colors: dict[str, Color], attrs: Attributes, bottom_garment: str | None = None, *, shoe_two_tone: bool = True) -> None:
    bottom_garment = bottom_garment or attrs.get("bottom_garment")
    pants_end, shoe_start = BOTTOM_ROWS.get(bottom_garment, (11, 9))
    pants_c = colors["bottom"]
    for part in ("r_leg", "l_leg"):
        for face_name in canvas.layout.part(part, 0).faces:
            f = canvas.layout.face(part, face_name, 0)
            if f.h < 12:
                _shaded_face(canvas, part, face_name, pants_c if pants_end >= 0 else colors["skin"], 0)
                continue
            for v in range(f.h):
                if v >= shoe_start:
                    if shoe_two_tone:
                        # 2톤 신발 (폴리시 C): 바닥 행은 어둡게, 나머지는 밝게.
                        c = shade(colors["shoe"], FACE_SHADE[face_name])
                        c = shade(c, 0.62) if v == f.h - 1 else shade(c, 1.35)
                    else:
                        c = shade(colors["shoe"], FACE_SHADE[face_name])
                elif v <= pants_end:
                    c = shade(pants_c, FACE_SHADE[face_name])
                else:
                    c = shade(colors["skin"], FACE_SHADE[face_name])
                if v == pants_end and 0 <= pants_end < shoe_start - 1:
                    c = shade(pants_c, 0.66)
                for u in range(f.w):
                    canvas.put(part, face_name, u, v, c, 0)


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
    resolved_bottom, bottom_is_default = resolve_bottom_ex(attrs, observed)
    if bottom_is_default:
        # 하체 미관측 jeans 기본: 관측 '하의' 샘플은 오탐(셔츠 꼬리 등)이므로
        # 측정색 대신 클래식 데님 청색을 쓴다 (사용자 결정 2026-10-13).
        colors["bottom"] = rgba(DEFAULT_JEANS)
    pattern = effective_pattern(attrs.get("pattern"), observed, attrs, tuple(degrade))
    # 측정 2색(줄무늬)이 있을 때만 실측 보조색. 없으면 합성 음영.
    alt = colors["top_alt"] if not observed.top_alt.missing and pattern in ("vertical_stripe", "horizontal_stripe") else None
    render_head(canvas, colors, attrs, observed.hair_stencil)
    render_body(canvas, colors, attrs, pattern, alt, observed.hair_stencil)
    render_arms(canvas, colors, attrs, pattern, resolve_sleeve(attrs, observed))
    render_legs(canvas, colors, attrs, resolved_bottom, shoe_two_tone=shoe_two_tone)
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
