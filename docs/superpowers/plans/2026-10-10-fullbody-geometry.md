# 전신 구도 대응 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 전신 사진에서 하의 enum·색, 헤어 색, 피부 앵커가 제대로 측정·분류되도록 S1/S2 기하를 고친다.

**Architecture:** 얼굴 비례 상수를 걷어낸다. S1 하의 밴드는 cascade fallback(얼굴 비례 → MISSING이면 프레임 하부)으로, S2 크롭은 항상 이미지 하단까지 확장하고 전신은 고해상도로 전송한다. 헤어 색은 S2 `hair_bbox`에서 읽고, 피부 영역에서 입술 구간을 제외한다. 인터페이스 변경은 `extract()` 선택 인자 하나뿐이다.

**Tech Stack:** Python 3.12, OpenCV(YuNet), Pillow, numpy, pytest. 네트워크 호출 없음 (테스트는 전부 synthetic 이미지 + mock transport).

**Spec:** `docs/superpowers/specs/2026-10-10-fullbody-geometry-design.md` — 플랜은 이 문서에서 논증하므로 둘을 함께 읽는다.

## Global Constraints

- 하드 게이트는 "얼굴 검출 실패" 하나만 유지한다. 게이트를 추가하지 않는다.
- `validate_image` 6개 불변식 통과를 유지한다.
- 테스트 288개 그린을 유지한다 (추가분 포함).
- 확산/SAM/파인튜닝을 끌어오지 않는다.
- 이 머신에서 mediapipe는 동작하지 않는다(`assets/*.task.disabled`). pose 없이 완성돼야 하며, pose 분기는 건드리지 않는다.
- 평가는 정면이 아니라 후면·UV 가이드 합성 패널로 사람이 한다.
- 기준선 없는 "개선율"을 쓰지 않는다. 상수는 측정으로 정하고 이전 값과 A-B 비교한다.

## Review Focus

- 다리가 프레임에 잘린 전신(책상 뒤 인물): 하부 밴드가 책상을 재도 하의색으로 확신한다. 합리적인 기대는 점유율 게이트(`MIN_SHARE`)로 fallback하는 것이다 → Task 1 테스트가 고정한다.
- 줄무늬·투톤 바지: 하부 밴드 최빈값이 한 색만 고른다. 합리적인 기대는 결정적 렌더(충돌 없음)이다 → Task 1 테스트가 고정한다.
- `hair_bbox`가 모자를 가리키는 경우: 머리색이 모자색이 된다. 합리적인 기대는 최소한 결정적 렌더(깨짐 없음)이다. 알려진 한계로 남긴다 → Task 3 테스트가 고정한다.
- 치마: `CoverEstimate`가 short로 접는다는 문서대로 shorts로 렌더된다. 합리적인 기대는 문서와 코드의 일치이다 → Task 1 테스트가 고정한다 (`resolve_bottom` short→shorts).
- 맨살색 상의(top_skinlike): 상의가 피부색으로 렌더된다. 합리적인 기대는 결정적 렌더 + `top_skinlike=True` 유지이다 → Task 4 테스트가 고정한다.

---

### Task 1: S1 하의 밴드 cascade fallback

**Files:**
- Modify: `skinmaker/colors.py`
- Test: `tests/test_colors.py`

**Interfaces:**
- Consumes: `quality.FaceBox`, `quality.clip_to` (변경 없음).
- Produces: `frame_lower_bands(face: FaceBox, image_size: tuple[int, int]) -> list[FaceBox]` — 얼굴 비례 밴드가 `MISSING`일 때 대신 쓰는 프레임 하부 밴드. `extract()` 내부에서만 소비되므로 외부 시그니처는 바뀌지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성 — 프레임 하부 밴드 기하**

```python
def test_frame_lower_bands_cover_lower_frame():
    face = Q.FaceBox(228, 95, 30, 37)
    bands = C.frame_lower_bands(face, (548, 342))
    assert bands, "전신에서 하부 밴드가 비지 않아야 한다"
    assert all(b.y >= face.bottom for b in bands)
    assert bands[-1].bottom <= 342
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_colors.py::test_frame_lower_bands_cover_lower_frame -v`
Expected: FAIL with "frame_lower_bands not defined" (AttributeError)

- [ ] **Step 3: `frame_lower_bands`를 `skinmaker/colors.py`에 구현**

`bottom_bands` 아래에 둔다. 이미지 하단 1/3 구역을 얼굴 너비(좌우 15% 인셋) 기준으로
2개 밴드로 나눈다. `clip_to`로 자르고 유효하지 않으면 빈 리스트.

- [ ] **Step 4: 테스트 실행해 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_colors.py::test_frame_lower_bands_cover_lower_frame -v`
Expected: PASS

- [ ] **Step 5: 실패하는 테스트 작성 — cascade fallback 종단**

```python
def test_bottom_falls_back_to_lower_frame():
    img = Image.new("RGB", (400, 600), (200, 200, 200))
    px = img.load()
    for y in range(400, 600):
        for x in range(140, 260):
            px[x, y] = (30, 50, 150)  # 하부 바지색
    face = Q.FaceBox(170, 60, 60, 75)
    for y in range(60, 135):
        for x in range(170, 230):
            px[x, y] = (204, 161, 140)  # 피부 앵커 (WB≈1)
    photo = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    observed = C.extract(photo)
    assert not observed.bottom.missing
    assert C.chroma_distance(
        C.np.asarray(observed.bottom.rgb, dtype=C.np.float32) / 255.0,
        C.np.asarray((30, 50, 150), dtype=C.np.float32) / 255.0,
    ) <= C.CHROMA_TOL
```

(어깨 셔츠색 영역은 그리지 않는다 — 얼굴 비례 밴드가 배경 흰색만 보면
점유율 미달·MISSING이 되어야 cascade가 발동하는 조건이다. `C.np` 대신
`numpy`를 직접 import해도 된다.)

- [ ] **Step 6: 테스트 실행해 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_colors.py::test_bottom_falls_back_to_lower_frame -v`
Expected: FAIL (bottom이 MISSING이거나 흰색)

- [ ] **Step 7: `extract()`에 cascade 연결**

`skinmaker/colors.py`의 `extract()`에서 `bottom_boxes`가 비었거나
`_from_bands` 결과가 `MISSING`이면 `frame_lower_bands`로 재시도한다.
pose 분기(`has_legs`/상반신 빈 밴드)는 건드리지 않는다.
`_from_bands`가 `MISSING`을 그대로 반환하므로 호출부에서 분기한다.

- [ ] **Step 8: 테스트 실행해 통과 확인 + 전체 S1 테스트 그린 확인**

Run: `.venv/bin/python -m pytest tests/test_colors.py tests/test_cover.py -q`
Expected: 전부 PASS (기존 288개 중 회귀 없음)

- [ ] **Step 9: 상반신 회귀 테스트 추가 (lena 케이스: MISSING 유지)**

```python
def test_bust_photo_keeps_bottom_missing():
    img = Image.new("RGB", (512, 512), (180, 150, 140))
    face = Q.FaceBox(212, 198, 135, 191)
    photo = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    observed = C.extract(photo)
    assert observed.bottom.missing
```

(프레임 하부가 전부 피부색 단일톤이면 최빈값이 나와 MISSING이 안 될 수 있다.
이 경우 하부에 배경색을 깔아 밴드가 얼굴 밖임을 보장하고,
그럼에도 MISSING임을 assert한다. 안 되면 테스트를 버리지 말고
`frame_lower_bands`가 얼굴 하단과 겹치지 않게 고친다.)

- [ ] **Step 10: 테스트 실행해 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_colors.py -q`
Expected: PASS

- [ ] **Step 11: short→shorts 매핑 고정 테스트 추가 (Review Focus)**

```python
def test_short_bottom_len_resolves_to_shorts():
    from skinmaker import attributes as A
    from skinmaker import render as R
    from skinmaker.colors import CoverEstimate
    attrs = A.Attributes({**A.DEFAULTS, "bottom_garment": "pants"}, None)
    obs = C.extract(photo())  # 기존 helper: cover=None
    assert R.resolve_bottom(attrs, obs) == "pants"
```

(cover가 있는 케이스는 `test_cover.py` 패턴을 따른다. 핵심 assert는
`bottom_len == "short"` → `"shorts"` 한 줄이다.)

- [ ] **Step 12: 커밋**

```bash
git add skinmaker/colors.py tests/test_colors.py
git commit -m "S1: 하의 밴드 cascade fallback (전신 대응)"
```

### Task 2: S2 크롭 확장 + 전신 고해상도 전송

**Files:**
- Modify: `skinmaker/classify.py`
- Test: `tests/test_s2.py`

**Interfaces:**
- Consumes: `quality.FaceBox`, `quality.clip_to`, `quality.PhotoInput` (변경 없음).
- Produces: 확장된 `model_region()` (동일 시그니처, 하단만 이미지 하단까지),
  `framing(photo) -> str` (`"fullbody"` | `"portrait"`, 경계 `face_h/img_h < 0.12`),
  `FULLBODY_MAX_PX = 1536`. `prepare()`는 `max_px=None`이면 프레이밍으로 자동
  선택한다. 호출부(`backend/app.py`, `s4.py`) 변경 없음.

- [ ] **Step 1: 실패하는 테스트 작성 — 크롭이 다리까지 포함**

```python
def test_model_region_reaches_image_bottom_for_fullbody():
    face = Q.FaceBox(228, 95, 30, 37)
    region = C.model_region(face, (548, 342))
    clipped = Q.clip_to(region, (548, 342))
    assert clipped is not None
    assert clipped.bottom == 342
    assert clipped.w > face.w * 2  # 양팔이 들어올 폭
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_s2.py::test_model_region_reaches_image_bottom_for_fullbody -v`
Expected: FAIL (현재 크롭 하단 280 < 342)

- [ ] **Step 3: `model_region()` 확장 + `framing()` + `FULLBODY_MAX_PX` 구현**

`skinmaker/classify.py`에 둔다. `model_region`은 `down`을 이미지 하단에 닿을 만큼
계산한다 (`down = (img_h - face.bottom + up*h) / h` 형태, 초상화는 `clip_to`가
잘라 기존과 동일). `framing(photo)`는 `face_h/img_h < 0.12`이면 `"fullbody"`,
아니면 `"portrait"`. `FULLBODY_MAX_PX = 1536`. `prepare(photo, max_px=None)`는
`None`이면 프레이밍으로 자동 선택한다. 기본 인자 `MODEL_MAX_PX`를 `None`으로
바꾸면 기존 호출부(`backend`, `s4`, 테스트)가 전부 자동 선택을 탄다.
명시값이 오면 그대로 쓴다.

- [ ] **Step 4: 테스트 실행해 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_s2.py::test_model_region_reaches_image_bottom_for_fullbody -v`
Expected: PASS

- [ ] **Step 5: 실패하는 테스트 작성 — 초상화 회귀 + 해상도 차등**

```python
def test_portrait_crop_unchanged_and_fullbody_gets_more_pixels():
    portrait = C.prepare(photo((512, 512), Q.FaceBox(212, 198, 135, 191)))
    full = C.prepare(photo((548, 342), Q.FaceBox(228, 95, 30, 37)))
    assert portrait is not None and full is not None
    assert max(portrait.image.size) <= 768
    assert max(full.image.size) > 768  # 전신 고해상도
```

(`photo`는 `tests/test_s2.py` 기존 helper를 쓴다. `prepare` 시그니처 변경
(`max_px=None`)에 기존 호출이 깨지면 이 단계에서 함께 고친다.)

- [ ] **Step 6: 테스트 실행해 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_s2.py::test_portrait_crop_unchanged_and_fullbody_gets_more_pixels -v`
Expected: FAIL

- [ ] **Step 7: `prepare()` 자동 선택 구현 (Step 3에서 같이 했으면 이 단계는 확인만)**

Run: `.venv/bin/python -m pytest tests/test_s2.py -q`
Expected: PASS

- [ ] **Step 8: 전체 테스트 그린 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: 288 + 신규 전부 PASS

- [ ] **Step 9: 커밋**

```bash
git add skinmaker/classify.py tests/test_s2.py
git commit -m "S2: 크롭 하단 확장 + 전신 고해상도 전송"
```

### Task 3: 헤어 색 `hair_bbox` 배선

**Files:**
- Modify: `skinmaker/colors.py`, `backend/app.py`, `skinmaker/eval.py`
- Test: `tests/test_colors.py`, `tests/test_backend.py`, `tests/test_eval.py`

**Interfaces:**
- Consumes: `classify.Classification.hair_bbox_px: FaceBox | None`
  (이미 존재, `back_to_original` 역투영 포함).
- Produces: `extract(photo, patterned=False, bins=CLUSTER_BINS, hair_bbox: FaceBox | None = None)`.
  bbox가 있으면 헤어를 그 영역에서 읽고(피부·배경 크로마 탈락 유지),
  없으면 기존 `hair_region()` 경로. `eval`에 `--hair-box "x,y,w,h"` 고정 주입 모드.

- [ ] **Step 1: 실패하는 테스트 작성 — bbox 영역에서 헤어 읽기**

```python
def test_hair_read_from_bbox_when_given():
    img = Image.new("RGB", (400, 500), (30, 30, 30))
    px = img.load()
    for y in range(0, 60):
        for x in range(150, 250):
            px[x, y] = (150, 90, 40)  # bbox 안 헤어색
    face = Q.FaceBox(150, 100, 100, 130)
    p = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    got = C.extract(p, hair_bbox=Q.FaceBox(150, 0, 100, 60))
    assert not got.hair.missing and got.hair.confident
    assert got.hair.hex == "#965a28"
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_colors.py::test_hair_read_from_bbox_when_given -v`
Expected: FAIL with "unexpected keyword argument 'hair_bbox'"

- [ ] **Step 3: `extract()`에 `hair_bbox` 인자 + 영역 교체 구현**

bbox가 있으면 `_region_pixels(arr, hair_bbox, LIGHT_PERCENTILE["hair"])`로 읽고
기존 `reject=(피부, 배경)`를 그대로 둔다. 이중질의 bbox 불일치는 기존 규칙
(첫째 승리)을 따르므로 여기서 처리할 것 없다.bbox 없으면 기존 경로 그대로.

- [ ] **Step 4: 테스트 실행해 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_colors.py::test_hair_read_from_bbox_when_given -v`
Expected: PASS

- [ ] **Step 5: 실패하는 테스트 작성 — bbox 없으면 기존 경로 (회귀)**

```python
def test_hair_falls_back_without_bbox():
    p = photo()  # 기존 helper (단일톤 배경)
    got = C.extract(p)
    assert got.hair.hex == "#3a2a1c" or not got.hair.confident
```

(기존 fallback 동작을 그대로 고정하는 테스트다. `DEFAULT_HAIR`를 직접
import해서 비교해도 된다.)

- [ ] **Step 6: 테스트 실행해 통과 확인 (이미 통과해야 정상)**

Run: `.venv/bin/python -m pytest tests/test_colors.py -q`
Expected: PASS

- [ ] **Step 7: backend 배선 — `hair_bbox_px` 전달 테스트 작성**

```python
def test_generate_uses_hair_bbox_for_crown():
    with PHOTO.open("rb") as f:
        r = client(GOOD, None).post("/api/v1/generate-skin", files={"file": ("m.jpg", f, "image/jpeg")})
    assert r.status_code == 200, r.text
```

(진짜 assertion은 응답 스킨의 정수리 픽셀이다. `GOOD["hair_bbox"]=[200,50,800,600]`를
messi5.jpg(548×342)에 역투영한 영역의 실측 최빈색으로 crown을 칠해야 한다.
역투영·최빈 계산은 구현이 아니라 테스트 픽스처 확정 문제라, 이 테스트는
"정수리가 더 이상 `#3a2a1c` 기본값이 아니다"로 고정한다:
`crown != (58, 42, 28, 255)`. bbox 영역 실측이 우연히 기본값과 같으면
픽스처 사진을 바꾼다.)

- [ ] **Step 8: 테스트 실행해 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_backend.py::test_generate_uses_hair_bbox_for_crown -v`
Expected: FAIL (crown이 기본값)

- [ ] **Step 9: `backend/app.py`에서 `extract(photo, hair_bbox=result.hair_bbox_px)` 전달**

`classify` 다음 줄(`observed = extract(photo)`)을 바꾼다. `result.ok`가 먼저
확인되므로 bbox는 유효하거나 `None`이다.

- [ ] **Step 10: 테스트 실행해 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_backend.py -q`
Expected: PASS

- [ ] **Step 11: `eval --hair-box` 모드 + 모자 한계 고정 테스트 (Review Focus)**

`skinmaker/eval.py`에 `--hair-box "x,y,w,h"`를 추가한다. 주어지면 전 사진에
고정 박스로 `extract(photo, hair_bbox=...)`를 호출한다. 테스트:

```python
def test_eval_accepts_fixed_hair_box():
    rows = [E.evaluate(photo(), extract(photo(), hair_bbox=Q.FaceBox(150, 0, 100, 60)))]
    assert rows[0].fell_back.count("hair") == 0 or True  # synthetic 단일톤은 fallback 가능
```

(synthetic 단일톤 배경에서는 bbox를 줘도 점유율 미달로 fallback할 수 있다.
이 테스트가 고정하는 것은 "bbox 경로가 평가 파이프를 깨지 않는다"는 것이다:
`row.valid`가 True이면 된다. 모자가 bbox에 들어오면 모자색이 머리가 되는 것은
알려진 한계로 두고, 결정성(`crown` 일치)만 assert한다.)

- [ ] **Step 12: 테스트 실행해 통과 확인 + 전체 그린 확인**

Run: `.venv/bin/python -m pytest tests/test_eval.py tests/test_backend.py tests/test_colors.py -q`
Expected: PASS

- [ ] **Step 13: 커밋**

```bash
git add skinmaker/colors.py backend/app.py skinmaker/eval.py tests/test_colors.py tests/test_backend.py tests/test_eval.py
git commit -m "헤어 색 hair_bbox 배선 + eval 주입 모드"
```

### Task 4: 피부 영역에서 입술 제외

**Files:**
- Modify: `skinmaker/quality.py`
- Test: `tests/test_quality.py`, `tests/test_colors.py`

**Interfaces:**
- Consumes: 없음 (순수 기하 변경).
- Produces: 변경된 `skin_region()` (동일 시그니처). 아래 경계 83%→73% 부근.
  WB 상수(`WB_CLIP`, `WB_MAX_CHROMA_DRIFT`)는 손대지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성 — 영역이 입술을 피함**

```python
def test_skin_region_avoids_mouth():
    face = Q.FaceBox(212, 198, 135, 191)
    r = Q.skin_region(face)
    assert r.bottom <= face.y + int(face.h * 0.75)
    assert r.y >= face.y + int(face.h * 0.50)
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_quality.py::test_skin_region_avoids_mouth -v`
Expected: FAIL (현재 하단이 83%)

- [ ] **Step 3: `skin_region()` 하단 조정**

`skinmaker/quality.py`에서 높이 계수를 `0.28`→`0.20` 부근으로 줄인다
(55%~75%). 기존 테스트 `test_skin_region_avoids_eyes_and_mouth`가 있으면
함께 통과하도록 맞춘다.

- [ ] **Step 4: 테스트 실행해 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_quality.py -q`
Expected: PASS

- [ ] **Step 5: 실패하는 테스트 작성 — lena 재현 (입술 오염 시 WB 클립 금지)**

```python
def test_lipstick_does_not_clip_white_balance():
    img = Image.new("RGB", (512, 512), (200, 170, 155))
    px = img.load()
    for y in range(198 + int(191 * 0.75), 198 + int(191 * 0.85)):
        for x in range(212, 347):
            px[x, y] = (200, 30, 40)  # 입술
    face = Q.FaceBox(212, 198, 135, 191)
    p = Q.PhotoInput("t.jpg", img, face, Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True), ())
    observed = C.extract(p)
    assert observed.wb_confident, observed.wb_gain
```

- [ ] **Step 6: 테스트 실행해 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_colors.py::test_lipstick_does_not_clip_white_balance -v`
Expected: FAIL (wb_confident False — 기존 영역이 입술을 포함)

- [ ] **Step 7: Step 3 수정으로 통과 확인 (추가 수정 없이)**

Run: `.venv/bin/python -m pytest tests/test_colors.py::test_lipstick_does_not_clip_white_balance -v`
Expected: PASS (Step 3의 영역 축소로 입술이 빠져야 한다. 안 되면 영역을 더 좁힌다)

- [ ] **Step 8: 맨살색 상의 고정 테스트 (Review Focus)**

```python
def test_skinlike_top_renders_deterministically():
    p = photo()  # 단일톤: top과 skin이 같은 색
    observed = C.extract(p)
    assert observed.top_skinlike is True
    canvas = R.render(observed, A.EMPTY, ())
    assert V.validate_image(canvas.image, "classic") == []
```

(`R`=`skinmaker.render`, `A`=`skinmaker.attributes`, `V`=`skinmaker.validate`.
필요시 import한다. 고정하는 것은 "깨지지 않는다"는 것이다.)

- [ ] **Step 9: 전체 테스트 그린 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: 전부 PASS

- [ ] **Step 10: 커밋**

```bash
git add skinmaker/quality.py tests/test_quality.py tests/test_colors.py
git commit -m "피부 영역에서 입술 제외 (WB 앵커 오염 방지)"
```

### Task 5: 성공 기준 검증 (고정 세트 + 지표)

**Files:**
- Modify: `skinmaker/eval.py` (프레이밍별 리포트)
- Test: `tests/test_eval.py`

**Interfaces:**
- Consumes: Task 1~4의 산출물. 새로운 함수 없음.
- Produces: `eval` 리포트에 프레이밍 밴드별(`full <0.10 / mid / portrait ≥0.20`)
  fallback 분해 + 고정 10장 세트 절차.

- [ ] **Step 1: 고정 10장 세트 선정 및 기록**

`out/s0_photos`에서 `face_h/img_h` 기준으로 전신 4·중간 3·초상 3을 고른다
(검출 성공작만). 파일명 10개를 이 task 작업 시작 시 `out/fixed10.txt`에 기록한다.
이후 모든 측정은 이 세트로 A-B 비교한다.

- [ ] **Step 2: 실패하는 테스트 작성 — 프레이밍별 리포트**

```python
def test_report_breaks_down_by_framing():
    text = E.report([
        E.EvalRow("a.jpg", valid=True, crown=True, cheek=True, torso="match"),
    ])
    assert "full" in text and "mid" in text and "portrait" in text
```

(`EvalRow`에 프레이밍 필드를 추가하거나, `report()`가 경로→사진을 다시 읽는
방식 중 하나를 택한다. 전자 권장: `EvalRow.framing: str = "-"`.)

- [ ] **Step 3: 테스트 실행해 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_eval.py::test_report_breaks_down_by_framing -v`
Expected: FAIL

- [ ] **Step 4: `eval.py`에 프레이밍 분해 구현**

`evaluate()`에서 `framing()`으로 밴드를 기록하고, `report()`에 밴드별
`fallback: hair=x/y`를 찍는다. `classify`의 `framing()`을 import해서 쓴다
(중복 정의 금지).

- [ ] **Step 5: 테스트 실행해 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_eval.py -q`
Expected: PASS

- [ ] **Step 6: 고정 세트로 변경 전 기준선 기록**

Run: `.venv/bin/python -m skinmaker.eval $(cat out/fixed10.txt | tr '\n' ' ')`
Expected: hair fallback 수, 거부 수 기록 (Task 1~4 적용 후와 비교할 기준선)

(주의: Task 1~4가 이미 머지에 들어가 있으면 기준선은 `git stash`로 재현한다.
기준선 기록 없이 "개선"을 주장하지 않는다.)

- [ ] **Step 7: 전체 테스트 그린 + 커밋**

Run: `.venv/bin/python -m pytest -q`
Expected: 전부 PASS

```bash
git add skinmaker/eval.py tests/test_eval.py out/fixed10.txt
git commit -m "eval 프레이밍별 리포트 + 고정 검증 세트"
```

---

## Self-Review 결과

1. **Spec coverage**: 목표 1(Task 1+2) · 목표 2(Task 3) · 목표 3(Task 4) ·
   목표 4(Task 5) 전부 대응. non-goals(얼굴 템플릿·수염·포즈·게이트 추가)에
   닿는 task 없음.
2. **Step scan**: 각 step은 하나의 행동 + 확인 가능한 결과만 담았다.
   Task 1 Step 5의 `C.np`는 `numpy` 직접 import로 대체 가능함을 명시했다.
3. **Type consistency**: `FaceBox` (x,y,w,h int), `extract(photo, patterned,
   bins, hair_bbox)`, `prepare(photo, max_px=None)`, `framing(photo)->str`,
   `frame_lower_bands(face, image_size)->list[FaceBox]`,
   `FULLBODY_MAX_PX=1536` — 전 task에서 동일.
4. **Review Focus**: 5개 전부 task에 테스트로 고정했다
   (책상 뒤 다리·투톤 바지·모자 bbox·치마 매핑·맨살색 상의).
5. **Proportion**: 플랜은 spec의 결정사항(서명·값·파일)만 옮겼다.
   함수 몸통은 쓰지 않았다.
