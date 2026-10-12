"""S4 후보 + 검증: 불확실한 필드를 변형한 후보 N개. AI 없음, 순위 없음.

후보의 원천은 순서 교환 이중 질의의 불일치뿐이다. 첫째 답이 c1, 둘째 답에서
달랐던 vary 필드값이 c2/c3 이다. 둘째 질의가 없거나 일치하면 변형할 근거가
없으므로 후보는 1개다. 근거 없는 변형(임의 enum 순환)은 만들지 않는다.

모든 후보는 validate_image 를 통과해야 저장된다. 렌더러가 대칭으로 그리므로
정상 경로에서는 전부 통과하고, 탈락은 버그 신호로 기록한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from .attributes import Attributes, apply_cross_rules, validate
from .classify import Classification
from .colors import ObservedColors
from .render import derive_noise_seed, render
from .validate import validate_image


@dataclass(frozen=True)
class Candidate:
    index: int
    attributes: Attributes
    image: Image.Image
    varied: str = ""
    problems: tuple[str, ...] = field(default_factory=tuple)
    noise_seed: int = 0
    image_flat: Image.Image | None = None

    @property
    def ok(self) -> bool:
        return not self.problems


def _second_values(classification: Classification) -> dict[str, str]:
    """둘째 질의에서 유효했던 값만. 강제·누락된 필드는 근거가 아니라 제외."""
    if classification.raw_second is None:
        return {}
    second = validate(classification.raw_second)
    bad = set(second.coerced) | set(second.missing)
    return {n: second.get(n) for n in second.clean_fields() if n not in bad}


def build(
    observed: ObservedColors,
    classification: Classification,
    degrade: tuple[str, ...] = (),
    model: str = "classic",
) -> list[Candidate]:
    """후보 리스트. c1 = 첫째 답 그대로, c2/c3 = 불일치 필드 변형. 무순위."""
    merged = classification.attributes
    alts = _second_values(classification)

    variants: list[tuple[dict[str, str], str]] = [(dict(merged.values), "as-answered")]
    for name in merged.vary_fields():
        if name not in classification.uncertain:
            continue
        alt = alts.get(name)
        if alt is None or alt == merged.get(name):
            continue
        values = dict(merged.values)
        values[name] = alt
        cross = apply_cross_rules(values)
        variants.append((cross.values, f"{name}={alt} (2nd query)"))
        if len(variants) >= 3:
            break

    out: list[Candidate] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for values, varied in variants:
        key = tuple(sorted(values.items()))
        if key in seen:
            continue
        seen.add(key)
        attrs = Attributes(dict(values), merged.hair_bbox, merged.coerced, merged.missing, merged.raw, merged.derived)
        # 후보별 결정론 시드 (설계 §8.3): 중복 제거된 실제 순번이 인덱스.
        seed = derive_noise_seed(observed, attrs, tuple(degrade), len(out) + 1)
        # ON/OFF 쌍 (설계 §4): 같은 시드 — 노이즈는 동일, 신발 톤만 다르다.
        canvas = render(observed, attrs, tuple(degrade), model, noise_seed=seed)
        flat_canvas = render(observed, attrs, tuple(degrade), model, noise_seed=seed, shoe_two_tone=False)
        problems = tuple(
            str(p)
            for img in (canvas.image, flat_canvas.image)
            for p in validate_image(img, model)
        )
        out.append(Candidate(len(out) + 1, attrs, canvas.image, varied, problems, seed, flat_canvas.image))
    return out
