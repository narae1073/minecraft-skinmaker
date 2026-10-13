# handover — skinmaker 다음 세션 인수인계 (2026-10-13 작성, HEAD `251bcc6`)

## 1. 프로젝트 한 줄 요약

사진 → 마인크래프트 64×64 스킨 파이프라인. **VLM(Gemini)은 속성 JSON만, 픽셀은 코드 렌더러가 그린다.**
단계: S0 품질·얼굴(YuNet) → S1 색 측정(WB·밴드/캐스케이드) → S2 분류(이중질의, 불확실 표기)
→ SCHP 파싱 마스크(색 국소화: 하의/머리/신발, **기본 on**) → S3 렌더(파라메트릭+노이즈)
→ S4 후보(불일치 필드 변형 1~3개) → 웹(FastAPI + React19/three.js, 3D 뷰어·에디터).

## 2. 현재 상태 (검증된 사실)

- 테스트 **451 passed** · lint 잔여 3건(기각·deferred, `Skin3DViewer` purity 경고뿐).
- 서버: `set -a; source .env; set +a; .venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8001`
  (`--host 0.0.0.0` 없으면 루프백 전용 — 실제로 겪은 함정).
- `python`/`uv` 미설치 — 반드시 `.venv/bin/python`.
- **venv 복구 이력**: 시스템 python3가 3.12→3.14로 바뀌며 venv가 고아된 적 있음
  (`No module named uvicorn`). `python3.12 3.12.3-1ubuntu0.17` deb 재설치 +
  `.venv/bin/python3` → `/usr/bin/python3.12` 재지향으로 복구. deb 캐시:
  `/tmp/opencode/py312/` (지우면 재다운로드 필요). `apt upgrade`에서 3.12가 빠지면
  같은 증상 재발.
- 파서 모델: `out/models/schp-atr-18-int8-static.onnx` (gitignored, 있음).
  `.env`의 `SKINMAKER_PARSING=1`은 **이제 중복**(코드 기본 on)이지만 무해·유지.

## 3. 이번 구간(노이즈+에디터 계획) 결과 — 9e05a1b..251bcc6, 전부 커밋

- **텍스처 노이즈**: 이산 톤 밴딩 `NOISE_STEPS=(0.92,0.96,1.0,1.08)`, 면별 독립 rng
  (가변 pitch 1~3px), **좌우 비대칭**(기저색만 대칭; validate mirror는 |Δ|≤NOISE_TOL=32).
  사용자 변천사: 규칙 격자 → 불규칙+비대칭 요청 → no-2×2 클럼프 요청 → **철회**(현행 유지).
- **결정론 시드**: `derive_noise_seed` = sha256(resolve_colors hexes + 정렬 attrs +
  degrade + 후보 index). `noise_level`은 시드에 **미포함** — 슬라이더가 패턴 불변 노브.
- **noise_level** (설계 §9): 스텝 크기 배율, 0=무노이즈 바이트 동일, 1=현행.
  웹 슬라이더 **기본 50%**. API 폼 필드 `noise_level` (부재=1.0, 가비지=400, 클램프).
- **Edit Skin 에디터** (설계 §5): 결과 카드·사이드바 → `SkinEditor` 모달 (큰 3D 뷰 +
  신발 2톤 토글 **기본 ON** + 처리 과정 섹션). 생성 시 ON(`_c{n}.png`)·OFF
  (`_c{n}_flat.png`) 쌍 선렌더 — 같은 시드, 차이는 신발 행뿐 (계약 테스트 고정).
  **사용자 판정: "editor for later"** — 추가 편집 기능(라이브 재렌더, 옷/피부색)은 보류;
  옵션 상태 자리는 남겨둠.
- **상반신 → jeans 기본** (§10): 파서 마스크에 하의(5/6)·맨다리(12/13) 픽셀 **둘 다 0** +
  S2 확신값 "none" + top != "dress" → `jeans` + `DEFAULT_JEANS #3b5a86`(클래식 데님,
  관측 하의 샘플은 폐기). 맨다리 보이는 전신은 none 유지(D3). summary도 같은 결정 반영.
- **분류 카테고리 표시** (§11): 응답에 `attributes {values,uncertain,derived,coerced}` ·
  `candidates [{index,varied}]` · `noise_level`. 웹: 한글 칩(불확실=호박색, derived='*')
  + 접이식 JSON 표 + 복사 버튼.
- **처리 과정 이미지** (§12): 요청당 `backend/static/steps/{token}_steps.png`(간단 s0→마스크→
  s1→atlas, **2열 격자**)·`_full.png`(QA 6패널). 폼 필드 `steps` — **웹 체크박스 기본 해제**,
  끄면 서버도 미생성(`steps:null`; 진위 규칙 parsing_on 관례, 부재=생성).
  파서 마스크는 요청당 1회(extract `seg=` 공유). 웹: 썸네일(150px 고정)→**라이트박스**
  (자체 스크롤, 간단/QA 토글).
- **레이아웃 D안** (§12 개정): body/#root flex 센터링 완전 제거 → block +
  `.container{margin:24px auto 40px}`. 근거: CDP 헤들리스 재현(scrollY=0에서 container
  top −628px/−1371px = 상단 도달 불가) → 24px. **5b8c7bf(margin-block:auto)는
  잘못된 수정이었음** — fixture에 고정 형제가 없어 오답. 스크롤 앵커링/지연로딩 수정은
  2차 증상 처치. UI 순서: (원본+후보) 행 → (분류+처리과정) 행, steps off 시 분석 행 단일 열.

## 4. 최종 리뷰 (서브에이전트, 2026-10-13) — **ready-to-merge**, Minor 5건 지연

1. **에디터 모달이 항상 '현재 생성' steps를 전달** — 사이드바 옛 스킨 편집 시 타 사진의
   단계 표시. 해결법: history pair에 steps 저장. **다음 세션 첫 수정 후보.**
2. flatUrl 없으면 토글 OFF 표시+2톤 표시 불일치 + 다운로드 파일명이 토큰명
   (`1a2b3c4d_c1_flat.png`) → 토글 비활성 가드 + 사람 이름으로.
3. `Skin3DViewer` immutability 3건 — 이번 범위에서 LARM/LLEG로 파일 변경됨. 다음 편집 시
   `useMemo`/loader callback으로 정리.
4. 백엔드 jeans e2e 픽셀 |Δ|≤8 고정 — `NOISE_TOL`(32) 사용이 정확(현 결정론이라 무난하지만
   프렌차이즈 취성).
5. eval 톨러런스가 유사색 스왑 놓칠 수 있음 — §3 공개 채택. 인접색 쌍 후속 테스트 권고.
- 강점 재확인: 거울 스트레스 60시드 무실 패, 시드/쌍/가드/스킵 계약 전부 테스트 고정.

## 5. 남은 과제 대기열 (우선순위대로)

1. 위 Minor 1·2·4 (작음 — "fix minors" 시 RED→GREEN 각각).
2. **에디터 확장**("later"): 라이브 재렌더 = 토큰별 관측치/attrs 저장 + 재렌더 엔드포인트
   (VLM 비용 없이 슬라이더/토글 실시간) — 설계 §9 비용 유의 문단 참조.
3. 옅은색 크로마 소실 (노란 바지가 흰 배경에서 `#c7cdc1` 회녹색) — **측정 논리 설계
   과제**, 상수 튜닝 금지.
4. plan `2026-10-11-skinmaker-finish-wip.md` 잔여: B1 앉은 구도 하의 크롭(images12류),
   B2 none 환각 게이트.
5. 시각 폴리시 중 미채택: 윤곽선(A)·음영(B) — 사용자가 C(신발 2톤)만 채택. 필요하면 다시 제안.
6. S2 top_garment 약점 (polo/shirt/tank 구분 3/10) — 사람 라벨 확장 또는 크롭 개선.
7. 사용자 결정 대기: master 푸시(origin은 3211cdc; 7커밋 뒤처짐), 전체 리뷰 후 워크스페이스
   정리(`.superpowers/sdd/2026-10-12-noise-editor/`).

## 6. 검증 규범 (어기면 안 되는 것들)

- **TDD**: RED를 눈으로 보고 → 최소 구현 → GREEN. 실패 가능 명령은 **pipe 없이** 독립 실행
  후 커밋 (`pytest | tail && commit`이 RED 커밋을 2회 만들었다 — 교훈 2회).
- **프론트 변경 전 `npm run lint`** (react-hooks 플러그인이 있었다 — 크래시 2건 놓침).
- 상수/정책 변경은 **이전 값과 A-B**로만 주장. 기준선 없는 개선 주장 금지.
- **적합(fitting) 세트 59장(`bottom_labels.json`)만 튜닝/검증**; held-out 49장·45장은
  **소진**됨 — 재사용 금지. 라벨은 사람이 정답(의사결정 (a)).
- 한글 커밋 메시지, master 직접 커밋 관행, 푸시는 사용자 결정.
- 서브에이전트 리뷰는 사용자가 요청할 때만 (기본은 셀프 리뷰 + 공개 disclosure).

## 7. 기록 문서 지도

- 계획/근거 ledger: `.superpowers/sdd/2026-10-12-noise-editor/progress.md` (판정·실수·교훈 전부)
- 노이즈+에디터 설계: `docs/superpowers/specs/2026-10-12-skin-noise-editor-design.md` (§2~§12)
- held-out 사다리 전체 근거: `docs/superpowers/specs/2026-10-11-heldout-protocol.md`
  (L0→L3, L2b raw색, L2c 머리/신발, 웹검증, S2 enum 검증 + 사람 라벨 정확도 부록)
- S2 검증 산출물: `out/s2_enum_val.py`/`out/s2_enum_val.json`/`out/s2_review.html`/
  `out/s2_human_labels.json` (기입 완료 — strict 0.72 / coarse 0.76, top 3/10 최약)
- 전체 계획: `/home/achi/.opencode/plan/2026-10-11-skinmaker-finish-wip.md`

## 8. 검증 기법 보물창고 (이 세션에서 검증됨)

- **CDP 헤들리스**: `/usr/bin/google-chrome --headless=new --remote-debugging-port=...`
  + `websocket-client`(venv에 설치됨)로 실앱 스크롤/레이아웃/스크린샷 측정 —
  `/tmp/opencode/scrolltest/{check,diag,probe2,probe3}.py` 참조. 레이아웃 검증은
  **반드시 실앱에서** (fixture 재현 실패 사례 있음).
- 노이즈/렌더 A/B 보드 스크립트: `out/shoes_ab.py`, `out/noise_ab.py` (사람 시각 판정용).
- 세션 메모: `uvicorn` 로그 `out/uvicorn.log`; 백그라운드 프로세스는 `pgrep -f uvicorn`.
