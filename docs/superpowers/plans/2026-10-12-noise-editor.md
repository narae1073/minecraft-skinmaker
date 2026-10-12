# 스킨 노이즈 + 에디터 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (native — 세션 관행).
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** 후보별 이산 톤 노이즈(거울 대칭·결정론)와 웹 "Edit Skin" 에디터(신발 2톤 토글, 기본 ON).

**Architecture:** render.py에 노이즈 패스 + `derive_noise_seed` 공유 파생 함수; candidates.build가 ON/OFF 둘 다 렌더; app.py는 파일 저장만; 프론트 `SkinEditor` 모달이 토글에 따라 두 PNG를 교차 표시.

**Tech Stack:** Python/PIL/numpy, FastAPI TestClient, React 19 + react-three-fiber.

**Spec:** `docs/superpowers/specs/2026-10-12-skin-noise-editor-design.md` (§8 결정 포함)

## Global Constraints

- `validate_image` 불변식 유지: 거울 좌우 동일 픽셀, binary alpha, base 레이어 완전 불투명.
- 노이즈 계수 `NOISE_STEPS = (0.92, 0.96, 1.0, 1.08)`; 1 픽셀 static 기각 — 2×2 블록 밴딩.
- ON/OFF 변형 쌍은 **같은 시드**; 시드 파생은 `render.derive_noise_seed` 단일 함수 (사본 금지).
- 기존 인터페이스 불변: `render` 기본 인자는 노이즈 없음(`noise_seed=None`), `skins` 응답 불변.
- 커밋 전 `pytest -q` 전체 그린; 한국어 커밋 메시지; master.

## Review Focus

- 거울 flip `lu = w-1-u` (validate.py:31) — u 안 정규화하면 mirror 탈락. → Task 1 `test_noise_passes_validate`.
- 2×2 블록이 거울 u' 정규화에서 어긋나면 패널 경계 톤이 좌우 달라짐 — 같은 테스트가 나포.
- eval 프로브 톨러런스에서 wire-swap 결함이 톨러런스 안에 숨으면 나포 실패 → Task 4 스왑 탐지 테스트.
- flat 파일 저장 누락/이름 불일치 → Task 5 계약 테스트(응답 URL↔디스크 파일 존재).
- 프론트 history 인덱스 로직 (삭제/선택) 객체화 시 꼬임 → 수동 e2e 확인 항목.

---

### Task 1: render 노이즈 패스 + `derive_noise_seed`

**Files:** Modify `skinmaker/render.py`; Test `tests/test_render.py`

**Interfaces:**
- Produces: `NOISE_STEPS: tuple[float,...]`, `NOISE_TOL: int = 32`,
  `derive_noise_seed(observed: ObservedColors, attrs: Attributes, degrade: tuple, index: int) -> int`,
  `render(observed, attrs, degrade, model="classic", *, noise_seed: int | None = None)`.

- [ ] RED `test_noise_same_seed_same_texture`: `render(observed(), attrs(), (), "classic", noise_seed=7)` 두 번 → 완전 동일.
- [ ] RED `test_noise_changes_pixels`: seed=7 vs seed=None → body front 면에서 다른 픽셀 존재.
- [ ] RED `test_noise_seed_varies`: seed=7 vs seed=8 → 다른 픽셀 존재.
- [ ] RED `test_noise_passes_validate`: noise on으로 `validate_image(canvas.image) == []` (garment 조합 3종 스냅).
- [ ] 구현: `derive_noise_seed` = sha256(resolve_colors(observed) hexes + sorted(attrs.values.items()) + degrade + index). 렌더 마지막 패스: layout 전 part/face 순회, `u' = min(u, w-1-u)`, 블록 `(u'//2, v//2)`, 키 `(seed, role, face_name, bu, bv)` → md5 바이트 → `NOISE_STEPS` 선택 → `shade` 곱해 `canvas.put` (put이 shade를 또 곱하지 않게 직접 px 쓰기 — 구현 자유, 불변식만 지켜짐). face_name과 role(좌우 접두어 제거)만 키 사용 → 거울 대칭.
- [ ] GREEN 확인 → commit `노이즈: 이산 톤 밴딩 패스 + 결정론 시드 (거울 대칭)`.

### Task 2: `shoe_two_tone` 플래그

**Files:** Modify `skinmaker/render.py:render/render_legs`; Test `tests/test_render.py`

- [ ] RED `test_shoe_two_tone_off_is_flat`: `shoe_two_tone=False` → r_leg front 9·10·11행 전부 `shade(shoe, 1.0)`.
- [ ] 구현: `render(..., *, shoe_two_tone: bool = True, ...)` → `render_legs(...)` 인자 전달; False이면 기존 단색 경로.
- [ ] GREEN → Task 1 커밋에 포함(같은 파일·같은 계약) — 별도 커밋 없음.

### Task 3: candidates.build — 시드 + ON/OFF 쌍

**Files:** Modify `skinmaker/candidates.py`; Test `tests/test_candidates.py`

**Interfaces:**
- Produces: `Candidate.noise_seed: int = 0`, `Candidate.image_flat: Image | None = None`;
  `build(...)`가 각 후보마다 ON(`image`)·OFF(`image_flat`) 렌더, `problems`는 둘 다 검증 병합.

- [ ] RED `test_candidates_have_seeds`: 분류 fixture로 build → 후보 2개 이상이면 `c1.noise_seed != c2.noise_seed`.
- [ ] RED `test_candidate_flat_pair_contract`: 각 후보에서 `image != image_flat` (신발 행), 신발 행 **밖** 완전 동일, 둘 다 `validate_image` 통과.
- [ ] RED `test_candidate_reproducible`: 같은 입력 재build → image 동일.
- [ ] 구현: `derive_noise_seed(observed, attrs.values(정렬 반영은 함수에 위임), degrade, idx)` (index는 merge된 실제 후보 순번), render 2회.
- [ ] GREEN → commit `후보: ON/OFF 렌더 쌍 + 후보별 결정론 시드`.

### Task 4: eval 프로브 톨러런스 + 시드

**Files:** Modify `skinmaker/eval.py`; Test `tests/test_eval.py` (없으면 생성)

- [ ] RED `test_evaluate_passes_with_noise`: 파이프라인 시드(derive_noise_seed)로 렌더한 canvas에서 crown/cheek/torso 프로브는 `NOISE_TOL` 톨러런스로 비교 → 통과.
- [ ] RED `test_probe_still_catches_swap`: hair와 top을 바꾼 관측값 → 프로브 실패 (톨러런스가 결함을 못 감춘 증거).
- [ ] 구현: eval이 `derive_noise_seed` (index=1) 렌더하고 예상색 비교를 채널별 |Δ|≤`NOISE_TOL` 로 교체.
- [ ] GREEN + `python -m skinmaker.eval out/fixed10` valid 10/10 재확인 → commit `eval: 노이즈 시드 경로 + 프로브 톨러런스(의미 변경 ledger 기록)`.

### Task 5: 백엔드 skins_flat

**Files:** Modify `backend/app.py`; Test 기존 backend 테스트 파일에 추가

- [ ] RED: TestClient 업로드 → 응답 `skins_flat` 길이==skins, URL 순서 동일; 각 URL의 디스크 파일 존재; ON 파일 vs flat 파일 픽셀 비교 — 신발 행 밖 동일.
- [ ] 구현: 各 candidate 저장 시 `{token}_c{n}_flat.png` 추가 저장 + 응답 배열.
- [ ] GREEN → commit `웹: skins_flat 변형 저장·응답 (Edit Skin 토글 재료)`.

### Task 6: 프론트 SkinEditor 모달 + 토글

**Files:** Create `frontend/src/components/SkinEditor.jsx`; Modify `frontend/src/App.jsx` (+`App.css`)

- [ ] `Skin3DViewer`에 `width/height` prop 추가(기본값=기존 200×300 — 기존 카드 무변).
- [ ] `SkinEditor` 모달: 큰 3D 뷰 + `{"two_tone": true}` 옵션 상태(기본 ON) + 토글 스위치 → 표시 텍스처 ON/OFF url 스왑 + 닫기. 다운로드 링크는 토글 따름.
- [ ] App.jsx: 스킨 상태를 `{url, flatUrl, summary}`로 보관(사이드바 선택/삭제 로직 이식); 결과 카드·사이드바에 "Edit Skin" 버튼 → 모달.
- [ ] `npm run build` 성공; uvicorn + 업로드 1장 e2e (사람 확인 — 브라우저).

### Task 7: 시각 A/B + ledger

- [ ] fixed-10 보드(노이즈 off/on, 다른 후보간 차이) 사람 판정 요청.
- [ ] ledger에 eval 의미 변경 기록; 계획 체크 최종화.

## Self-Review

- 스펙 §2~§5·§8 전 항목 → Task 1~6에 매핑 완료. §6 비목표 구현 금지.
- 인터페이스 일관: `derive_noise_seed(observed, attrs, degrade, index)` (Task 1 정의 = 3·4에서 동일 서명 사용).
- Review Focus 각 줄 → Task 1/4/5 테스트로 고정됨.
