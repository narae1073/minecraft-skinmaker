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
    """seg의 머리 픽셀 → 8×8 격자 투표. 얼굴 박스 위 머리 질량만 앞머리 행이 된다.

    얼굴 박스 안에 머리 픽셀이 없으면(사진 머리선 = 박스 상단) 가운데 열은
    0행까지만 — 이마가 드러난다. 옆열(0,7)은 트림 밖이라 마스크 대로 끝까지.
    """
    face = FaceBox(16, 24, 32, 32)
    seg = np.full((96, 96), 2, np.uint8)  # 전부 머리
    seg[face.y:face.y + face.h, face.x:face.x + face.w] = 11  # 얼굴만 피부
    s = HS.mask_stencil(seg, face, (96, 96))
    assert s is not None
    assert all(s.front[0])  # 0행은 전폭 머리 (위 구멍 금지)
    for v in (1, 2):  # 가운데: 사진 머리선이 박스 위 → 0행까지만; 옆열은 유지
        assert s.front[v][0] and s.front[v][7] and not any(s.front[v][1:7]), (v, s.front[v])
    assert s.top_hair is True
    for v in range(3, 8):  # 얼굴 박스 내부 가운데는 피부 (눈 템플릿 보호 클램프)
        assert not any(s.front[v][1:7]), (v, s.front[v])
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
    assert s.side_profiles["back"] == (0,) * 8  # 대머리: 뒤통수도 피부 (사용자 결정)


def test_mask_stencil_mohawk():
    """모호크: 상단 띠의 중앙 폭 좁은 머리 띠만. 옆은 배경 → 머리 아님.

    오늘 규칙은 옆열을 무조건 머리로 칠했다 — 이 테스트가 그 한계를 깬다.
    옆면 행수 0 (중앙 띠가 옆으로 흐르지 않음 — 사진 그대로), 뒤통수는 머리가
    있으므로 가득 (사용자 결정 2026-10-15: 뒤통수에 피부 구멍 금지).
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
    assert s.side_profiles["back"] == (8,) * 8  # 머리 있음 → 뒤통수 가득


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
    assert raw.side_rows["left"] == 8  # 뒤통수 끝(가득)까지 이어진다
    assert raw.side_rows["right"] == 0
    assert raw.side_rows["back"] == 8  # 뒤통수 가득 (사용자 결정 2026-10-15)
    assert raw.side_profiles["right"] == (0,) * 8

    sym = HS.mask_stencil(seg, face, (96, 96))  # 기본값
    assert sym.front[0][0] is True
    assert sym.front[0][7] is True  # 거울 OR
    assert sym.side_rows["left"] == sym.side_rows["right"] == 8
    assert sym.side_rows["back"] == 8
    assert sym.side_profiles["right"] == (2, 3, 4, 5, 5, 6, 7, 8)

    with pytest.raises(ValueError):
        HS.mask_stencil(seg, face, (96, 96), symmetry="bogus")


def _set_cell(seg, box, v, u, cls):
    """Set a complete projected cell in the synthetic SCHP map."""
    cw, ch = box.w / 8, box.h / 8
    x0, x1 = int(box.x + u * cw), int(box.x + (u + 1) * cw)
    y0, y1 = int(box.y + v * ch), int(box.y + (v + 1) * ch)
    seg[y0:y1, x0:x1] = cls


def test_mask_stencil_covers_arch_corners():
    """∩ 캡 모서리: 배경은 추론으로, 관측 FACE 셀도 위 머리 흐름이 있으면 막는다.

    사용자 결정 2026-10-15: 위 좌우 모서리에 피부가 보이면 안 된다 —
    머리가 있는 열은 0행부터 이어진다 (위 구멍 금지).
    """
    face = FaceBox(16, 24, 32, 32)
    hb = Q.hair_region(face)
    seg = np.zeros((96, 96), np.uint8)
    # Round cap: row 0 center, row 1 wider, row 2 full. Row-0 col 3 is an
    # explicit scalp/part signal — now covered too (hair flows beneath it).
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
    assert s.front[0][3], "관측 FACE 셀도 아래 머리 흐름이 있으면 덮는다 (위 구멍 금지)"


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
    # 옆 경계는 앞 가장자리(관자) 깊이에서 뒤통수 끝(가득)으로 이어진다 — 뒤 모서리 단차 없음.
    assert s.side_profiles["left"] == (5, 5, 6, 6, 7, 7, 8, 8)
    assert s.side_profiles["right"] == (5, 5, 6, 6, 7, 7, 8, 8)
    assert s.side_profiles["back"] == (8,) * 8  # 머리 있음 → 뒤통수 가득


def test_mask_stencil_side_profile_flows_into_full_back():
    """옆 머리선은 관자 깊이에서 뒤통수 끝값까지 단조 증가 — 뒤 모서리에 단차가 없다.

    사용자 지시 2026-10-15: 머리선이 끊김 없이 이어져야 한다. 정면 열 값(관자)과
    옆면 첫 열이 같고, 옆면 끝 열과 뒤통수 가장자리가 같아야 코너에서 안 끊긴다.
    """
    face = FaceBox(16, 24, 32, 32)
    hb = Q.hair_region(face)
    seg = np.zeros((96, 96), np.uint8)
    for u in range(8):  # 남 사진류: 관자 3행 · 가운데 1행 실루엣
        for v in range(3 if u in (0, 7) else 2 if u in (1, 6) else 1):
            _set_cell(seg, hb, v, u, 2)
    s = HS.mask_stencil(seg, face, (96, 96), symmetry="raw")
    assert s is not None
    assert s.side_profiles["left"] == (3, 4, 4, 5, 6, 7, 7, 8)
    assert list(s.side_profiles["left"]) == sorted(s.side_profiles["left"]), "단조 증가"
    assert s.side_profiles["left"][0] == 3  # 앞 모서리 = 정면 가장자리 열
    assert s.side_profiles["left"][-1] == s.side_profiles["back"][0] == 8  # 뒤 모서리 연속


def _paint_band(seg, box, u, y0, y1, cls):
    """얼굴 박스 안 열 밴드에 세로 머리 띠를 칠한다 (머리선 추적 스캔용)."""
    cw = box.w / 8
    x0, x1 = int(box.x + u * cw), int(box.x + (u + 1) * cw)
    seg[y0:y1, x0:x1] = cls


def test_mask_stencil_traces_photo_hairline():
    """정면 머리선 추적: 사진에서 이마가 보이면 가운데 열을 윗행까지 자른다.

    옆머리(1,2·5,6열)는 얼굴 박스 안에 깊은 머리(사진선 t≈0.5)가 있고
    가운데(3,4열)는 없다 → 가운데만 0행까지, 옆은 눈(4-5행) 위 3행까지.
    """
    face = FaceBox(16, 24, 32, 32)
    hb = Q.hair_region(face)
    seg = np.zeros((96, 96), np.uint8)
    for v in range(3):  # 상단 띠: 얼굴 위 머리 질량
        for u in range(8):
            _set_cell(seg, hb, v, u, 2)
    for u in (1, 2, 5, 6):  # 옆머리는 위 머리 질량에서 얼굴 박스 안까지 이어진다
        x0 = int(hb.x + u * hb.w / 8)
        x1 = int(hb.x + (u + 1) * hb.w / 8)
        seg[int(hb.y):face.y + 16, x0:x1] = 2
    s = HS.mask_stencil(seg, face, (96, 96), symmetry="raw")
    assert s is not None
    assert s.front[0][3] and s.front[0][4]
    assert not s.front[1][3] and not s.front[2][3]  # 가운데: 이마 노출
    assert not s.front[1][4] and not s.front[2][4]
    assert s.front[1][1] and s.front[2][1]  # 옆: 사진선 깊이 유지
    assert s.front[1][5] and s.front[2][5]
    # 눈이 4-5행으로 내려가 상한이 열렸다 — 깊은 옆머리는 3행까지 (참조 스킨)
    assert s.front[3][1] and s.front[3][2] and s.front[3][5] and s.front[3][6]
    assert not s.front[4][1]  # 눈 보호는 4행부터


def test_mask_stencil_symmetrizes_traced_hairline():
    """한쪽만 깊은 옆머리: 대칭화(기본)는 반대쪽 머리선도 내리고, raw는 한쪽만."""
    face = FaceBox(16, 24, 32, 32)
    hb = Q.hair_region(face)
    seg = np.zeros((96, 96), np.uint8)
    for v in range(3):
        for u in range(8):
            _set_cell(seg, hb, v, u, 2)
    for u in (1, 2):  # 왼쪽만 깊다
        _paint_band(seg, hb, u, face.y, face.y + 16, 2)
    raw = HS.mask_stencil(seg, face, (96, 96), symmetry="raw")
    assert raw.front[1][1] and raw.front[2][1]
    assert not raw.front[1][6] and not raw.front[2][6]
    sym = HS.mask_stencil(seg, face, (96, 96))  # symmetrized 기본
    assert sym.front[1][6] and sym.front[2][6]  # 거울 최대: 오른쪽도 깊이 유지
    assert not sym.front[1][3]  # 가운데 이마는 그대로 열림


def test_mask_stencil_bang_trace_ignores_beard():
    """턱 수염(hair)은 앞머리선을 늘리지 않는다 — 추적은 얼굴 위쪽 55%만 본다."""
    face = FaceBox(16, 24, 32, 32)
    hb = Q.hair_region(face)
    seg = np.zeros((96, 96), np.uint8)
    for v in (0, 1):  # 머리 질량은 얼굴 박스 위쪽에만
        for u in range(8):
            _set_cell(seg, hb, v, u, 2)
    seg[face.y + int(0.75 * face.h):face.bottom, face.x:face.right] = 2  # 수염
    s = HS.mask_stencil(seg, face, (96, 96), symmetry="raw")
    assert s is not None
    for u in range(1, 7):  # 가운데 머리선은 0행까지 — 수염이 끌어내리지 않는다
        assert not s.front[1][u] and not s.front[2][u], (u, s.front[1][u])


def test_mask_stencil_covers_skin_above_hair():
    """머리 위에 뚫린 피부(모서리·가르마 셀)는 덮는다 — 위에 머리가 흐르면 구멍 금지.

    왼쪽 끝·가운데의 관측 FACE 셀도 아래에 머리가 있으면 머리로 막힌다
    (사용자 지시 2026-10-15). 머리가 전혀 없는 오른쪽 끝 열은 근거가 없어
    그대로 피부.
    """
    face = FaceBox(16, 24, 32, 32)
    hb = Q.hair_region(face)
    seg = np.zeros((96, 96), np.uint8)
    for v in (1, 2):
        for u in range(7):  # 0-6열: 1-2행 머리
            _set_cell(seg, hb, v, u, 2)
    for u in range(7):  # 얼굴 박스 안 깊이 (추적선이 행을 자르지 않게)
        _paint_band(seg, hb, u, face.y, face.y + 16, 2)
    for u in (0, 3, 7):  # 0행: 왼끝·가르마·오른끝 = 관측 피부
        _set_cell(seg, hb, 0, u, 11)
    for u in range(7):
        if u not in (0, 3):
            _set_cell(seg, hb, 0, u, 2)
    _set_cell(seg, hb, 1, 7, 11)  # 오른쪽 끝 열은 전부 피부
    _set_cell(seg, hb, 2, 7, 11)
    s = HS.mask_stencil(seg, face, (96, 96), symmetry="raw")
    assert s is not None
    assert s.front[0][0], "왼쪽 끝: 위가 관측 피부여도 아래 머리 흐름 → 덮는다"
    assert s.front[0][3], "가르마 셀도 머리 위 구멍이면 덮는다"
    assert not s.front[0][7] and not s.front[1][7], "머리 없는 열은 그대로 피부"


def test_mask_stencil_back_full_when_hair_detected():
    """머리가 있으면 뒤통수는 가득 — 정면 사진은 뒤통수를 안 보여준다 (사용자 결정 2026-10-15)."""
    face = FaceBox(16, 24, 32, 32)
    hb = Q.hair_region(face)
    seg = np.zeros((96, 96), np.uint8)
    for v in (0, 1):  # 짧은 머리: 앞 실루엣은 2행뿐
        for u in range(8):
            _set_cell(seg, hb, v, u, 2)
    s = HS.mask_stencil(seg, face, (96, 96), symmetry="raw")
    assert s is not None
    assert s.side_profiles["back"] == (8,) * 8


def test_mask_stencil_measures_contiguous_shoulder_hair():
    """Hair continuing below the jaw maps to torso rows; a gap ends the measured run."""
    face = FaceBox(16, 24, 32, 32)
    hb = Q.hair_region(face)
    seg = np.zeros((96, 96), np.uint8)
    for u in range(8):
        _set_cell(seg, hb, 0, u, 2)
    # One side lock reaches 8 pixels below the chin, then stops: ceil(8/32*12)=3 torso rows.
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


def test_mask_stencil_body_extent_caps_at_twelve_rows():
    """Even hair seen a full face-height below the jaw caps at the 12-row torso."""
    face = FaceBox(16, 24, 32, 32)
    hb = Q.hair_region(face)
    seg = np.zeros((96, 96), np.uint8)
    for u in range(8):
        _set_cell(seg, hb, 0, u, 2)
    seg[face.bottom:face.bottom + face.h, face.x + 24:face.x + 31] = 2
    assert HS.mask_stencil(seg, face, (96, 96), symmetry="raw").body_rows == 12


def test_effective_length_uses_vlm_floor_and_mask_evidence():
    short = HS.rule_stencil("short")
    assert HS.effective_hair_length("long", short) == "long"
    assert HS.target_body_rows("long", short) == 6
    assert HS.target_body_rows("very_long", short) == 10
    assert HS.target_body_rows("short", short) == 0

    st = HS.rule_stencil("short")
    st = HS.HairStencil(st.front, st.top_hair, st.side_profiles, body_rows=8, bottom=st.bottom)
    assert HS.effective_hair_length("short", st) == "very_long"
    assert HS.effective_hair_length("medium", st) == "very_long"


def test_bottom_coverage_is_rear_only_and_length_aware():
    short = HS.rule_stencil("short")
    long = HS.rule_stencil("long")
    very = HS.rule_stencil("very_long")
    for st, rear in ((short, 1), (long, 3), (very, 4)):
        # v0=front(턱) .. v7=back. 마지막 rear 행만 머리, 앞쪽은 피부.
        for v in range(8):
            expect = v >= 8 - rear
            for u in (3, 4):
                assert st.bottom[v][u] is expect, (rear, v, u)
        assert all(st.bottom[v][0] and st.bottom[v][7] for v in range(8 - rear, 8))
    assert not any(any(row) for row in HS.HairStencil(short.front, False, {}, 0).bottom)


def test_bald_never_paints_bottom_or_body():
    face = FaceBox(16, 24, 32, 32)
    seg = np.full((96, 96), 11, np.uint8)
    st = HS.mask_stencil(seg, face, (96, 96))
    assert st is not None and st.top_hair is False
    assert not any(any(row) for row in st.bottom)
    assert st.body_rows == 0


def test_style_targets_and_fallbacks():
    st = HS.rule_stencil("long")
    assert HS.effective_hair_style("", "long", st) == "long_straight"
    assert HS.effective_hair_style("bun", "long", st) == "bun"
    assert HS.style_body_rows("bob", "long", st) == 0
    assert HS.style_body_rows("ponytail", "long", st) == 0
    assert HS.style_body_rows("bun", "long", st) == 0
    assert HS.style_body_rows("long_straight", "long", st) == 6
    assert HS.style_body_rows("long_wavy", "long", st) == 8
    assert HS.style_body_rows("curly", "long", st) == 5
    assert HS.style_bangs("bob") == 3
    assert HS.style_bangs("short") == 2
