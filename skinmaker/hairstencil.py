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
    side_profiles: dict[str, tuple[int, ...]] = field(default_factory=dict)
    # face author-u 열마다 위에서부터 칠할 행 수. head cuboid의 모든 면은 8열.

    @property
    def side_rows(self) -> dict[str, int]:
        """기존 진단/계약 호환: 각 면 프로파일의 최장 길이."""
        return {face: max(profile, default=0) for face, profile in self.side_profiles.items()}


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
    profiles = {
        "right": (rows,) * 8,
        "left": (rows,) * 8,
        "back": (rows,) * 8,
    }
    return HairStencil(tuple(front), True, profiles)


def _dominant_class(block: np.ndarray) -> int | None:
    """셀 블록의 실제 다수 클래스. 모두 비어 있으면 None."""
    if block.size == 0:
        return None
    return int(np.bincount(block.reshape(-1)).argmax())


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
    classes = np.zeros((HEAD_GRID, HEAD_GRID), dtype=np.uint8)
    for v in range(HEAD_GRID):
        for u in range(HEAD_GRID):
            y0 = int(hb.y + v * ch)
            y1 = int(hb.y + (v + 1) * ch)
            x0 = int(hb.x + u * cw)
            x1 = int(hb.x + (u + 1) * cw)
            block = np.asarray(seg)[y0:max(y1, y0 + 1), x0:max(x1, x0 + 1)]
            cls = _dominant_class(block)
            classes[v, u] = 0 if cls is None else cls
    vote = np.isin(classes, HAIR_CLASSES)
    # 머리의 둥근 ∩ 캡은 사진에서 보이지 않는 배경과 겹친다. 위 3행 안에서
    # 아래 행의 양옆 hair가 지지하는 배경 셀만 hair로 추론한다. FACE/의상 등
    # 명시된 클래스는 절대로 덮지 않아 가르마/이마를 보존한다.
    for v in range(min(3, HEAD_GRID - 1)):
        for u in range(HEAD_GRID):
            if classes[v, u] != 0 or vote[v, u]:
                continue
            lo, hi = max(0, u - 1), min(HEAD_GRID, u + 2)
            support = int(vote[v + 1, lo:hi].sum())
            needed = 1 if u in (0, HEAD_GRID - 1) else 2
            if support >= needed:
                vote[v, u] = True
    if symmetry == "symmetrized":
        mirror = vote[:, ::-1]
        # 반대편을 채우는 건 관측되지 않은 배경 셀만 허용한다.
        vote |= mirror & (classes == 0)
    elif symmetry != "raw":
        raise ValueError(f"symmetry는 symmetrized|raw: {symmetry!r}")

    # 옆/뒤 프로파일은 눈 템플릿 클램프와 별개인 기하 근거를 쓴다. 앞면만
    # clamp하여 눈 위 이마를 보호하되, 그 제한이 옆/뒤 머리 길이를 자르지 않게 한다.
    profile_vote = vote.copy()
    # 눈 템플릿 보호: 얼굴 중앙 열은 3행 이상 머리로 못 덮는다 (앞머리는 0-2행까지만).
    vote[3:, 1:HEAD_GRID - 1] = False
    # 근거 없음(머리 영역 전부 배경) → None. 맨살뿐(대머리)은 근거다 — 벗은 스텐실.
    if not (np.asarray(seg)[int(hb.y):int(hb.y + hb.h), int(hb.x):int(hb.x + hb.w)] != 0).any():
        return None
    heights = tuple(
        int(np.flatnonzero(profile_vote[:, u])[-1]) + 1 if profile_vote[:, u].any() else 0
        for u in range(HEAD_GRID)
    )
    # 가장자리 실루엣을 옆면 8열에 보간하고, 뒷면에는 전체 프로파일을 이어 붙인다.
    # 바깥 가장자리에 hair가 없으면 side face도 비운다 (중앙 모호크가 옆면으로
    # 번지지 않게). side face 각 열은 앞 가장자리에서 안쪽 head profile로 곡선을 만든다.
    def interpolate(a: int, b: int) -> tuple[int, ...]:
        return tuple(round(a + (b - a) * i / 7) for i in range(8))

    left_profile = interpolate(heights[0], heights[3]) if heights[0] else (0,) * 8
    right_profile = interpolate(heights[7], heights[4]) if heights[7] else (0,) * 8
    side_profiles = {
        "left": left_profile,
        "right": right_profile,
        "back": heights,
    }
    front = tuple(tuple(bool(b) for b in row) for row in vote)
    # 정수리: 상단 띠(격자 0-1행 너비)의 다수 클래스. 맨두피(11) 능선이면 피부,
    # 그 외(머리·배경=정수리 미관측)는 오늘 동작 유지(머리).
    band = np.asarray(seg)[int(hb.y):int(hb.y + hb.h / 4), int(hb.x):int(hb.x + hb.w)]
    dom = _dominant_class(band)
    top_hair = dom != FACE if dom is not None else True
    return HairStencil(front, top_hair, side_profiles)
