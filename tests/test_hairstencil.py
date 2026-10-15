"""마스크 기반 머리 실루엣 스텐실 (Tier 0, 사용자 설계 2026-10-15).

rule 스텐실은 오늘의 길이 규칙과 픽셀 동일이어야 한다 — 디버그 베이스라인이자
회귀 방어선. mask 스텐실은 seg(원본 크기 SCHP class map)의 머리 픽셀을
8×8 머리 격자로 투영한다: 앞면은 사진 대로, 뒷면은 앞 실루엣에서 추론.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest

from skinmaker import hairstencil as HS
from skinmaker import quality as Q
from skinmaker.quality import FaceBox


def test_rule_stencil_matches_current_pattern():
    """rule 스텐실 = render.render_head의 오늘 고정 표 그대로.

    오늘: 앞머리 상단 2행 전체 폭 + 옆 2열(2-3행 short/medium, 2-7행 long/very_long)
    + 옆/뒤 행수 short 2 / medium 4 / long 6 / very_long 8 + 정수리 항상 머리.
    """
    s = HS.rule_stencil("short")
    for v in (0, 1):
        assert all(s.front[v]), (v, s.front[v])
    assert s.front[2][0] and s.front[2][7]
    assert s.front[3][0] and s.front[3][7]
    assert not any(s.front[4]), s.front[4]
    assert s.top_hair is True
    assert s.side_rows == {"right": 2, "left": 2, "back": 2}

    s = HS.rule_stencil("medium")
    assert s.side_rows == {"right": 4, "left": 4, "back": 4}
    assert not any(s.front[4])

    s = HS.rule_stencil("long")
    for v in range(2, 8):
        assert s.front[v][0] and s.front[v][7], v  # 오늘 코드: long도 옆열 2-7행
    assert s.side_rows == {"right": 6, "left": 6, "back": 6}  # 뒷면만 6행으로 다르다

    s = HS.rule_stencil("very_long")
    for v in range(2, 8):
        assert s.front[v][0] and s.front[v][7], v
    assert s.side_rows == {"right": 8, "left": 8, "back": 8}

    # 모르는 값 → short 취급 (오늘의 back_rows.get 기본 (0,1)과 동일)
    s = HS.rule_stencil("bogus")
    assert s.side_rows == {"right": 2, "left": 2, "back": 2}


def test_mask_stencil_projects_photo_hair():
    """seg의 머리 픽셀 → 8×8 격자 투표. 가득 찬 머리: 0-1행 전체 폭 + 옆열 끝까지."""
    face = FaceBox(16, 24, 32, 32)
    seg = np.full((96, 96), 2, np.uint8)  # 전부 머리
    seg[face.y:face.y + face.h, face.x:face.x + face.w] = 11  # 얼굴만 피부
    s = HS.mask_stencil(seg, face, (96, 96))
    assert s is not None
    for v in (0, 1):
        assert all(s.front[v]), (v, s.front[v])  # 상단 띠 = 머리
    assert s.top_hair is True
    for v in range(3, 8):  # 얼굴 박스 내부 가운데는 피부 (눈 템플릿 보호 클램프)
        assert not any(s.front[v][1:7]), (v, s.front[v])
    assert s.front[2][0] and s.front[2][7]  # 옆열은 마스크 대로
    assert s.front[7][0] and s.front[7][7]
    assert s.side_rows == {"left": 8, "right": 8, "back": 8}


def test_mask_stencil_no_hair_returns_none():
    """배경뿐(근거 없음) → None — 호출부가 규칙 폴백."""
    face = FaceBox(16, 24, 32, 32)
    seg = np.zeros((96, 96), np.uint8)  # 전부 배경
    assert HS.mask_stencil(seg, face, (96, 96)) is None


def test_mask_stencil_bald():
    """대머리: 머리 영역 전부 맨살(11) → 근거 있는 벗은 머리.

    정수리 피부 + 앞 0-2행도 피부 + 옆/뒤 없음. 오늘 렌더는 항상 머리라
    표현 불가였던 케이스 — mask 스텐실의 대표 기능.
    """
    face = FaceBox(16, 24, 32, 32)
    seg = np.full((96, 96), 11, np.uint8)
    s = HS.mask_stencil(seg, face, (96, 96))
    assert s is not None
    assert s.top_hair is False
    assert not any(any(r) for r in s.front)  # 앞면 전부 피부
    assert s.side_rows == {"left": 0, "right": 0, "back": 0}


def test_mask_stencil_mohawk():
    """모호크: 상단 띠의 중앙 폭 좁은 머리 띠만. 옆은 배경 → 머리 아님.

    오늘 규칙은 옆열을 무조건 머리로 칠했다 — 이 테스트가 그 한계를 깬다.
    뒷면/옆면 행수 0 (중앙 띠가 옆으로 흐르지 않음 — 사진 그대로).
    """
    face = FaceBox(16, 24, 32, 32)
    hb = Q.hair_region(face)
    seg = np.zeros((96, 96), np.uint8)
    seg[int(hb.y):int(hb.y + hb.h / 4), int(hb.x + hb.w * 0.4):int(hb.x + hb.w * 0.6)] = 2
    seg[face.y:face.y + face.h, face.x:face.x + face.w] = 11
    s = HS.mask_stencil(seg, face, (96, 96))
    assert s is not None
    assert s.top_hair is True  # 상단 띠 다수(비배경) = 머리
    rows0 = s.front[0]
    assert rows0[3] or rows0[4]  # 중앙 띠 생존
    assert not rows0[0] and not rows0[7]  # 옆은 배경 → 오늘이라면 머리였을 자리
    for v in range(2, 8):
        assert not any(s.front[v]), v
    assert s.side_rows["left"] == s.side_rows["right"] == 0
    assert s.side_profiles["back"] == (0, 0, 0, 2, 2, 0, 0, 0)


def test_mask_stencil_symmetrized_vs_raw():
    """비대칭 앞머리: raw는 사진 그대로, symmetrized(기본)는 거울 OR로 정리."""
    face = FaceBox(16, 24, 32, 32)
    hb = Q.hair_region(face)
    seg = np.zeros((96, 96), np.uint8)
    # 상단 띠의 왼쪽 절반만 머리 (오른쪽 절반은 배경)
    seg[int(hb.y):int(hb.y + hb.h / 4), int(hb.x):int(hb.x + hb.w / 2)] = 2
    seg[face.y:face.y + face.h, face.x:face.x + face.w] = 11

    raw = HS.mask_stencil(seg, face, (96, 96), symmetry="raw")
    assert raw.front[0][0] is True
    assert raw.front[0][7] is False
    assert raw.side_rows["left"] == 2
    assert raw.side_rows["right"] == 0
    assert raw.side_rows["back"] == 2  # 긴 쪽 기준으로 뒤까지
    assert raw.side_profiles["right"] == (0,) * 8

    sym = HS.mask_stencil(seg, face, (96, 96))  # 기본값
    assert sym.front[0][0] is True
    assert sym.front[0][7] is True  # 거울 OR
    assert sym.side_rows["left"] == sym.side_rows["right"] == 2
    assert sym.side_rows["back"] == 2
    assert sym.side_profiles["right"] == (2,) * 8

    with pytest.raises(ValueError):
        HS.mask_stencil(seg, face, (96, 96), symmetry="bogus")


def _set_cell(seg, box, v, u, cls):
    """Set a complete projected cell in the synthetic SCHP map."""
    cw, ch = box.w / 8, box.h / 8
    x0, x1 = int(box.x + u * cw), int(box.x + (u + 1) * cw)
    y0, y1 = int(box.y + v * ch), int(box.y + (v + 1) * ch)
    seg[y0:y1, x0:x1] = cls


def test_mask_stencil_fills_only_unobserved_arch_corners():
    """Background at the ∩ cap corners is inferred; an explicit face-class part remains skin."""
    face = FaceBox(16, 24, 32, 32)
    hb = Q.hair_region(face)
    seg = np.zeros((96, 96), np.uint8)
    # Round cap: row 0 center, row 1 wider, row 2 full. Row-0 col 3 is an
    # explicit scalp/part signal, not an unobserved background corner.
    for u in range(2, 6):
        _set_cell(seg, hb, 0, u, 2)
    _set_cell(seg, hb, 0, 3, 11)
    for u in range(1, 7):
        _set_cell(seg, hb, 1, u, 2)
    for u in range(8):
        _set_cell(seg, hb, 2, u, 2)
    s = HS.mask_stencil(seg, face, (96, 96), symmetry="raw")
    assert s is not None
    assert s.front[0][0] and s.front[0][7], "unknown ∩ corners should be inferred as hair"
    assert not s.front[0][3], "explicit FACE-class part must remain skin"


def test_mask_stencil_head_profiles_follow_curved_mask():
    """Per-column profiles preserve a curved edge rather than filling uniform rectangles."""
    face = FaceBox(16, 24, 32, 32)
    hb = Q.hair_region(face)
    seg = np.zeros((96, 96), np.uint8)
    # Hand-built curved silhouette: long outer locks, short center fringe.
    heights = (5, 4, 3, 2, 2, 3, 4, 5)
    for u, height in enumerate(heights):
        for v in range(height):
            _set_cell(seg, hb, v, u, 2)
    s = HS.mask_stencil(seg, face, (96, 96), symmetry="raw")
    assert s is not None
    assert s.side_profiles["left"] == (5, 5, 4, 4, 3, 3, 2, 2)
    assert s.side_profiles["right"] == (5, 5, 4, 4, 3, 3, 2, 2)
    assert s.side_profiles["back"] == heights


def test_mask_stencil_measures_contiguous_shoulder_hair():
    """Hair continuing below the jaw maps to torso rows; a gap ends the measured run."""
    face = FaceBox(16, 24, 32, 32)
    hb = Q.hair_region(face)
    seg = np.zeros((96, 96), np.uint8)
    for u in range(8):
        _set_cell(seg, hb, 0, u, 2)
    # One side lock reaches 8 pixels below the chin, then stops: ceil(8/32*12)=3 body rows.
    seg[face.bottom:face.bottom + 8, face.x + 26:face.x + 31] = 2
    seg[face.bottom + 10:face.bottom + 18, face.x + 26:face.x + 31] = 2
    s = HS.mask_stencil(seg, face, (96, 96), symmetry="raw")
    assert s is not None
    assert s.body_rows == 3


def test_mask_stencil_short_hair_has_no_body_extent():
    """No Hair(2) pixels below the jaw means no torso hair rows."""
    face = FaceBox(16, 24, 32, 32)
    hb = Q.hair_region(face)
    seg = np.zeros((96, 96), np.uint8)
    for u in range(8):
        _set_cell(seg, hb, 0, u, 2)
    assert HS.mask_stencil(seg, face, (96, 96), symmetry="raw").body_rows == 0
