"""스킨 텍스처 불변식 검사. 게임에서 깨지는 모든 조건을 여기에 고정한다."""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from .format import MIRRORED_PAIRS, TEXTURE_SIZE, get_layout


@dataclass(frozen=True)
class Problem:
    code: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.detail}"


def _mirror_runs(image: Image.Image, model: str) -> list[Problem]:
    problems: list[Problem] = []
    layout = get_layout(model)
    for right, left in MIRRORED_PAIRS.items():
        for layer in (0, 1):
            for face_name, rface in layout.part(right, layer).faces.items():
                lface = layout.part(left, layer).face(face_name)
                for v in range(rface.h):
                    for u in range(rface.w):
                        if u >= lface.w:
                            continue
                        lu = lface.w - 1 - u
                        rp = image.getpixel((rface.x + u, rface.y + v))
                        lp = image.getpixel((lface.x + lu, lface.y + v))
                        if rp != lp:
                            problems.append(
                                Problem(
                                    "mirror",
                                    f"{right}/{left} layer={layer} 면={face_name} ({u},{v}) 불일치 {rp} != {lp}",
                                )
                            )
                            if len(problems) > 20:
                                return problems
    return problems


def validate_image(image: Image.Image, model: str = "classic") -> list[Problem]:
    problems: list[Problem] = []
    layout = get_layout(model)

    if image.size != (TEXTURE_SIZE, TEXTURE_SIZE):
        problems.append(Problem("size", f"크기가 {image.size}, (64, 64)이어야 합니다"))
    if image.mode != "RGBA":
        problems.append(Problem("mode", f"모드가 {image.mode}, RGBA여야 합니다"))

    if problems:
        return problems

    px = image.load()

    used: dict[tuple[int, int], tuple[str, int, str]] = {}
    for part in layout.parts.values():
        for face in part.faces.values():
            for py in range(face.y, face.y + face.h):
                for pxx in range(face.x, face.x + face.w):
                    key = (pxx, py)
                    if key in used:
                        problems.append(Problem("overlap", f"면 겹침 {key}: {used[key]} vs {(part.name, part.layer, face.name)}"))
                    used[key] = (part.name, part.layer, face.name)

    for py in range(TEXTURE_SIZE):
        for pxx in range(TEXTURE_SIZE):
            if (pxx, py) in used:
                continue
            r, g, b, a = px[pxx, py]
            if a != 0:
                problems.append(Problem("bleed", f"사용하지 않는 픽셀이 불투명 ({pxx},{py}) alpha={a}"))

    for (pxx, py), (_, layer, _) in used.items():
        if layer == 0:
            r, g, b, a = px[pxx, py]
            if a != 255:
                problems.append(Problem("base_alpha", f"내곽 레이어는 완전 불투명이어야 합니다 ({pxx},{py}) alpha={a}"))
                if len(problems) > 40:
                    return problems

    problems.extend(_mirror_runs(image, model))
    return problems


def assert_valid(image: Image.Image, model: str = "classic") -> None:
    problems = validate_image(image, model)
    if problems:
        lines = "\n".join(f"  - {p}" for p in problems[:20])
        raise AssertionError(f"스킨 검증 실패 ({len(problems)}건):\n{lines}")


def report(image: Image.Image, model: str = "classic") -> str:
    problems = validate_image(image, model)
    if not problems:
        return f"OK {model} 64x64 RGBA, {get_layout(model).usable_pixels()} 사용 가능 픽셀"
    return "\n".join(str(p) for p in problems[:40])
