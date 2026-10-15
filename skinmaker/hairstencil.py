"""머리 실루엣 스텐실 (Tier 0, 사용자 설계 2026-10-15).

렌더가 머리를 칠하는 판정을 데이터로 분리한 것. 두 근원:
- rule: 오늘의 길이 규칙 (render.render_head의 고정 표). 마스크가 없거나
  사용자가 고른 베이스라인. 픽셀 동일이 오늘 렌더와 같아야 한다.
- mask: seg(원본 크기 SCHP class map)의 머리 픽셀을 8×8 머리 격자로 투영.
  앞면은 사진 대로 (머리선 높이·앞머리·옆머리), 정수리는 상단 띠에서,
  옆/뒷면은 앞 실루엣에서 추론한다 (앞 사진은 뒷머리를 보여주지 않는다).

색은 여기서 정하지 않는다 — 측정값(colors["hair"])이 그대로 칠해진다.
정수리가 피부로 판정되는 대머리도 표현한다 (오늘은 항상 머리색).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .quality import FaceBox, clip_to, hair_region

# ATR-18 클래스 (parsing.py 클래스 표 참조). Hat(1)은 오늘의 '모자=머리색' 동작을
# 유지하기 위해 머리 셀에 합친다 (모자 렌더는 후속 과제).
HAIR_CLASSES = (1, 2)
FACE = 11  # 맨살 두피(대머리) 신호 — 상단 띠가 이 클래스면 정수리 피부

HEAD_GRID = 8  # 머리 각 면 8×8


@dataclass(frozen=True)
class HairStencil:
    front: tuple[tuple[bool, ...], ...]  # 8행(v) × 8열(u). True=머리카락. v0=정수리 쪽.
    top_hair: bool                        # 정수리(top 면) 머리 여부
    side_rows: dict[str, int] = field(default_factory=dict)  # right/left/back → 위에서 몇 행까지


# 오늘의 길이 규칙 (render.render_head 그대로): length → (옆/뒤 행수, 옆열 깊이)
# 옆열은 short/medium에서 2-3행, long/very_long에서 2-7행 — 뒷면 행수와 다른 표다.
_RULE = {"short": (2, 4), "medium": (4, 4), "long": (6, 8), "very_long": (8, 8)}


def rule_stencil(hair_length: str) -> HairStencil:
    """길이 enum → 오늘 렌더와 픽셀 동일인 스텐실. 베이스라인이자 폴백."""
    rows, side_depth = _RULE.get(hair_length, (2, 4))  # 모르는 값 → short 취급
    front = []
    for v in range(HEAD_GRID):
        row = [False] * HEAD_GRID
        if v < 2:
            row = [True] * HEAD_GRID  # 앞머리 2행 전체 폭
        elif v < side_depth:
            row[0] = row[HEAD_GRID - 1] = True  # 옆 2열
        front.append(tuple(row))
    n = {"right": rows, "left": rows, "back": rows}
    return HairStencil(tuple(front), True, n)


def _dominant_class(block: np.ndarray) -> int | None:
    """셀 블록의 배경 제외 다수 클래스. 비배경 픽셀이 없으면 None (배경 셀)."""
    nz = block[block != 0]
    if nz.size == 0:
        return None
    return int(np.bincount(nz).argmax())


def mask_stencil(
    seg,
    face: FaceBox,
    img_size: tuple[int, int],
    symmetry: str = "symmetrized",
) -> HairStencil | None:
    """seg + 얼굴 박스 → 사진 실루엣 스텐실. 근거가 서지 않으면 None (규칙 폴백).

    머리 영역은 quality.hair_region과 같은 확장(위 0.35, 좌우 0.10)을 쓴다 —
    색 추출이 보는 영역과 투영 영역이 같아야 판정이 어긋나지 않는다.
    """
    if seg is None or face is None:
        return None
    full = hair_region(face)
    hb = clip_to(full, img_size)
    if hb is None or hb != full:  # 머리 영역이 프레임에 잘리면 투영 근거가 어긋난다
        return None
    cw, ch = hb.w / HEAD_GRID, hb.h / HEAD_GRID
    vote = np.zeros((HEAD_GRID, HEAD_GRID), dtype=bool)
    for v in range(HEAD_GRID):
        for u in range(HEAD_GRID):
            y0 = int(hb.y + v * ch)
            y1 = int(hb.y + (v + 1) * ch)
            x0 = int(hb.x + u * cw)
            x1 = int(hb.x + (u + 1) * cw)
            block = np.asarray(seg)[y0:max(y1, y0 + 1), x0:max(x1, x0 + 1)]
            cls = _dominant_class(block)
            vote[v, u] = cls is not None and cls in HAIR_CLASSES
    # 눈 템플릿 보호: 얼굴 중앙 열은 3행 이상 머리로 못 덮는다 (앞머리는 0-2행까지만).
    vote[3:, 1:HEAD_GRID - 1] = False
    if symmetry == "symmetrized":
        mirror = vote[:, ::-1]
        vote = vote | mirror
    elif symmetry != "raw":
        raise ValueError(f"symmetry는 symmetrized|raw: {symmetry!r}")

    def col_rows(u: int) -> int:
        idx = np.flatnonzero(vote[:, u])
        return int(idx[-1]) + 1 if idx.size else 0

    left_rows, right_rows = col_rows(0), col_rows(HEAD_GRID - 1)
    if symmetry == "symmetrized":
        left_rows = right_rows = max(left_rows, right_rows)
    # 근거 없음(머리 영역 전부 배경) → None. 맨살뿐(대머리)은 근거다 — 벗은 스텐실.
    if not (np.asarray(seg)[int(hb.y):int(hb.y + hb.h), int(hb.x):int(hb.x + hb.w)] != 0).any():
        return None
    side_rows = {
        "left": left_rows,
        "right": right_rows,
        "back": max(left_rows, right_rows),  # 긴 머리는 뒤까지 흐른다 (앞 실루엣 추론)
    }
    front = tuple(tuple(bool(b) for b in row) for row in vote)
    # 정수리: 상단 띠(격자 0-1행 너비)의 다수 클래스. 맨두피(11) 능선이면 피부,
    # 그 외(머리·배경=정수리 미관측)는 오늘 동작 유지(머리).
    band = np.asarray(seg)[int(hb.y):int(hb.y + hb.h / 4), int(hb.x):int(hb.x + hb.w)]
    dom = _dominant_class(band)
    top_hair = dom != FACE if dom is not None else True
    return HairStencil(front, top_hair, side_rows)
