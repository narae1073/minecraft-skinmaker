"""S2 속성 스키마: enum, 프롬프트, 스키마, 검증, 불확실성.

전송 계층(VLM)에 독립적이다. 프롬프트와 스키마는 여기 하나뿐이라
Gemini / Ollama / Colab 을 같은 조건으로 비교할 수 있다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

ENUMS: dict[str, tuple[str, ...]] = {
    "top_garment": ("tee", "hoodie", "jacket", "shirt", "sweater", "vest", "uniform", "apron", "overalls", "dress", "none"),
    "bottom_garment": ("jeans", "shorts", "skirt", "pants", "none"),
    "pattern": ("plain", "vertical_stripe", "horizontal_stripe", "check", "plaid", "graphic", "floral"),
    "sleeve_len": ("none", "short", "three_quarter", "long"),
    "hair_length": ("short", "medium", "long", "very_long"),
    "beard": ("none", "stubble", "full"),
    "inner_top": ("none", "shirt", "tee", "knit"),
    "neckwear": ("none", "tie"),
    # 구조 (2026-10-28): 옷의 여밈/칼라/주머니/대칭. 크롭 천 위에 1px 로 얹는다.
    "closure_type": ("none", "zipper", "buttons"),
    "collar_type": ("none", "crew", "v_neck", "shirt", "hood"),
    "pocket_type": ("none", "patch"),
    "symmetry": ("symmetric", "asymmetric"),
}

DEFAULTS: dict[str, str] = {
    "top_garment": "tee",
    "bottom_garment": "none",
    "pattern": "plain",
    "sleeve_len": "none",
    "hair_length": "short",
    "beard": "none",
    "inner_top": "none",
    "neckwear": "none",
    "closure_type": "none",
    "collar_type": "none",
    "pocket_type": "none",
    "symmetry": "symmetric",
}

FIELD_ORDER: tuple[str, ...] = (
    "top_garment", "bottom_garment", "pattern", "sleeve_len", "hair_length", "beard",
    "inner_top", "neckwear", "closure_type", "collar_type", "pocket_type", "symmetry",
)
REVERSED_ORDER: tuple[str, ...] = tuple(reversed(FIELD_ORDER)) + ("hair_bbox",)
NATURAL_ORDER: tuple[str, ...] = FIELD_ORDER + ("hair_bbox",)

BBOX_FIELD = "hair_bbox"
BBOX_SCALE = 1000

_HINTS = {
    "top_garment": "상의 종류 (모자·가방·보 Warm 보온재는 옷이 아님)",
    "bottom_garment": "하의 종류",
    "pattern": "상의 무늬. 무늬 없으면 plain",
    "sleeve_len": "소매 길이. 어깨에서 끝나면 short, 손목이면 long",
    "hair_length": "머리 길이. 모자에 가렸으면 보이는 부분만",
    "beard": "수염. 없으면 none, 짧은 수염·면도 그림자면 stubble, 뚜렷한 수염/콧수염이면 full",
    "inner_top": "안에 껴입은 상의. 목/칼라에 겉옷과 다른 안쪽 옷이 보이면 shirt/tee/knit, 단일 상의·맨목이면 none",
    "neckwear": "넥타이. 칼라 아래 타이가 보이면 tie, 없으면 none",
    "closure_type": "앞여밈. 지퍼가 보이면 zipper, 단추가 보이면 buttons, 없으면 none",
    "collar_type": "칼라. 라운드=crew, 브이넥=v_neck, 셔츠칼라=shirt, 후드=hood, 없으면 none",
    "pocket_type": "주머니. 겉으로 붙은 사각 주머니가 보이면 patch, 없으면 none",
    "symmetry": "옷/무늬가 좌우 대칭으로 보이면 symmetric, 한쪽만 다르면 asymmetric",
    "hair_bbox": "머리카락만 있는 영역. 모자·헬멧·안경은 제외. HEAD 영역 관측용",
}

_RULES = (
    "확실하지 않으면 가장 가까운 것을 고른다. 설명하지 않는다.",
    "옷이 보이지 않으면 해당 항목은 none.",
    "민소매·끈나시·탱크톱·캐미솔도 상의다 — 가장 가까운 종류(예: tee)로 고르고 sleeve_len은 none. 맨몸일 때만 top_garment는 none.",
    "이미지 전체에서 보이는 머리카락만 찾는다. 얼굴 상자가 아니라 머리카락 영역.",
    "모자·헬멧은 머리카락이 아니므로 hair_bbox에 포함하지 않는다.",
    "closure/collar/pocket 은 실제로 보일 때만 고른다. 확실하지 않으면 none.",
    "대칭은 옷과 무늬의 좌우 차이를 본다. 판단이 어려우면 symmetric.",
    "JSON 객체 하나만 출력한다. 마크다운 코드펜스 없이.",
)


def build_prompt(order: tuple[str, ...] = NATURAL_ORDER) -> str:
    lines = [
        "사진 한 장을 보고 아래 항목만 판단한다.",
        "판단 근거나 확률은 쓰지 않는다. JSON 만 출력한다.",
        "",
        "항목:",
    ]
    for name in order:
        if name == BBOX_FIELD:
            lines.append(f"- {name}: {_HINTS[name]}. [x0,y0,x1,y1] 정수 4개. 0-{BBOX_SCALE} 정규화.")
            continue
        options = ", ".join(ENUMS[name])
        lines.append(f"- {name}: {_HINTS[name]}. 아래 중 정확히 하나: {options}")
    lines.append("")
    lines.append("규칙:")
    for rule in _RULES:
        lines.append(f"- {rule}")
    lines.append("")
    lines.append(f'출력 형식: {{"{FIELD_ORDER[0]}": "...", ..., "{BBOX_FIELD}": [0,0,0,0]}}')
    return "\n".join(lines)


def build_schema(order: tuple[str, ...] = NATURAL_ORDER) -> dict[str, Any]:
    """표준 JSON Schema (RFC draft-07 소문자 타입) 를 정본으로 쓴다.

    전송 계층마다 스키마 方言이 다르다 (Gemini 는 OpenAPI 대문자, Ollama 는 Go 바인딩).
    정본은 표준으로 두고 변환은 각 전송 계층이 한다.
    """
    props: dict[str, Any] = {}
    for name in order:
        if name == BBOX_FIELD:
            props[name] = {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 4,
                "maxItems": 4,
            }
        else:
            props[name] = {"type": "string", "enum": list(ENUMS[name])}
    return {"type": "object", "properties": props, "required": list(props)}


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)
_OBJECT = re.compile(r"\{.*\}", re.S)


def parse_json_object(text: str | None) -> dict | None:
    """모델 출력을 관대하게 파싱한다. 스키마 강제를 못 하는 전송 계층을 위해."""
    if not text:
        return None
    body = text.strip()
    fenced = _FENCE.search(body)
    if fenced:
        body = fenced.group(1).strip()
    try:
        value = json.loads(body)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    obj = _OBJECT.search(body)
    if not obj:
        return None
    try:
        value = json.loads(obj.group(0))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


@dataclass(frozen=True)
class Attributes:
    values: dict[str, str]
    hair_bbox: tuple[int, int, int, int] | None
    coerced: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    raw: dict = field(default_factory=dict, repr=False)
    derived: tuple[str, ...] = ()

    def get(self, name: str) -> str:
        return self.values.get(name, DEFAULTS.get(name, "none"))

    def clean_fields(self) -> tuple[str, ...]:
        return FIELD_ORDER

    def vary_fields(self) -> tuple[str, ...]:
        """후보 변형에 쓸 수 있는 필드. 얼굴 관련은 v1 에서 뺀다."""
        return ("top_garment", "hair_length", "sleeve_len")


EMPTY = Attributes(dict(DEFAULTS), None, tuple(FIELD_ORDER), tuple(FIELD_ORDER))


def _coerce_bbox(value: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        nums = [int(round(float(v))) for v in value]
    except (TypeError, ValueError):
        return None
    x0, y0, x1, y1 = nums
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    x0 = max(0, min(BBOX_SCALE, x0))
    y0 = max(0, min(BBOX_SCALE, y0))
    x1 = max(0, min(BBOX_SCALE, x1))
    y1 = max(0, min(BBOX_SCALE, y1))
    if x1 - x0 < BBOX_SCALE // 20 or y1 - y0 < BBOX_SCALE // 20:
        return None
    return (x0, y0, x1, y1)


def validate(raw: dict | None) -> Attributes:
    raw = raw or {}
    values: dict[str, str] = {}
    coerced: list[str] = []
    missing: list[str] = []
    for name in FIELD_ORDER:
        got = raw.get(name)
        if got is None:
            missing.append(name)
        elif isinstance(got, str) and got in ENUMS[name]:
            values[name] = got
            continue
        else:
            coerced.append(name)
        values[name] = DEFAULTS[name]
    cross = apply_cross_rules(values)
    bbox = _coerce_bbox(raw.get(BBOX_FIELD))
    if BBOX_FIELD not in raw or bbox is None:
        missing.append(BBOX_FIELD)
    return Attributes(cross.values, bbox, tuple(coerced), tuple(missing), dict(raw), cross.applied)


@dataclass(frozen=True)
class Derived:
    values: dict[str, str]
    applied: tuple[str, ...]


CROSS_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("top_garment", "none", "sleeve_len", "none"),
    ("top_garment", "none", "pattern", "plain"),
    ("top_garment", "none", "closure_type", "none"),
    ("top_garment", "none", "collar_type", "none"),
    ("top_garment", "none", "pocket_type", "none"),
)


def apply_cross_rules(values: dict[str, str]) -> Derived:
    """enum 은 서로 독립이 아니다. 스키마로는 강제되지 않는 관계를 코드에서 막는다.

    실제 모델을 돌려보니 top_garment=none 인데 sleeve_len=long 을 내놓는 경우가
    있었다. 모순된 필드가 렌더러로 내려가면 어깨에 소매가 생긴다.
    """
    out = dict(values)
    applied: list[str] = []
    for src, want, dst, forced in CROSS_RULES:
        if out.get(src) == want and out.get(dst) != forced:
            applied.append(f"{dst}:{out.get(dst)}->{forced}")
            out[dst] = forced
    return Derived(out, tuple(applied))


def agreement(a: Attributes, b: Attributes) -> tuple[str, ...]:
    """두 질의가 불일치한 필드 + 강제/누락이 일어난 필드."""
    out: list[str] = []
    for name in FIELD_ORDER:
        if name in a.coerced or name in b.coerced or name in a.missing or name in b.missing:
            out.append(name)
        elif a.get(name) != b.get(name):
            out.append(name)
    return tuple(out)


def is_uncertain(attrs: Attributes) -> tuple[str, ...]:
    return tuple(n for n in FIELD_ORDER if n in attrs.coerced or n in attrs.missing)


def summarize(attrs: Attributes, uncertain: tuple[str, ...]) -> str:
    parts = [f"{n}={attrs.get(n)}" for n in FIELD_ORDER]
    parts.append(f"hair_bbox={attrs.hair_bbox if attrs.hair_bbox else '--'}")
    parts.append(f"uncertain={','.join(uncertain) or 'none'}")
    if attrs.coerced:
        parts.append(f"coerced={','.join(attrs.coerced)}")
    if attrs.derived:
        parts.append(f"derived=[{'; '.join(attrs.derived)}]")
    return "  ".join(parts)
