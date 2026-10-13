# 스킨 노이즈 + 편집기 설계 (2026-10-12)

상태: 초안 (승인 대기). 소속: 웹 제품 과제. 근거 사진: 사용자 지적 "스킨이 밋밋하다"
(스티브 텍스처에는 미세 톤 밴딩이 있다), 편집기 요청: "3D 렌더러 확장 → 신발 2톤 토글".

## 1. 의도와 배경

현재 렌더는 면(face)별 단색 SHADE 밴드라 평면하게 보인다. 스티브류 마인크래프트
기본 텍스처는 같은 기저색 위에 **2~4단 이산 톤 밴딩**으로 질감을 준다. 여기에
(1) 후보별 텍스처 노이즈를 얹고, (2) 웹 결과에서 "Edit Skin" → 에디터(3D 뷰어 확장)
에서 신발 2톤을 ON/OFF 토글(기본 ON)로 바꿔본다.

- 3D 렌더러(react-three-fiber `Skin3DViewer`)는 이미 에디터 확장 1단계다. 이번에
  **에디터 모달(`SkinEditor`)** 로 감싸 옵션 상태를 지닌 껍데기를 만든다 — 이후
  옷/피부색 변경 등의 옵션이 같은 자리에 붙는다 (지금 구현은 신발 토글뿐).

## 2. 노이즈 설계 (결정)

- **대칭 (개정 2026-10-12, 사용자 피드백: "uniform·좌우대칭 낫다")**: 노이즈 적용은
  **좌우 비대칭·불규칙**이다 — 면(face)마다 독립 rng 해시, 가변 pitch(1~3px) 파절,
  단계 무작위(1.0 가중 6/11). 기저색 드로잉은 여전히 좌우 대칭; 노이즈만 비대칭.
  이에 따라 `validate`의 mirror 불변식은 **등식 → |Δ|≤NOISE_TOL**로 완화한다.
  첫 목적(배선 결함 나포)은 유지 — 잘못된 기저색은 노이즈 단계 한계(≈±8%)보다
  훨씬 큰 차이를 만들므로 여전히 잡힌다.
- **형태**: 기저색 보존. 셀마다 이산 계수 중 하나를 곱한다:
  `NOISE_STEPS = (0.92, 0.96, 1.0, 1.08)` — 1.0 중심, 가끔 밝고 어두운 밴드.
  거친 밴딩을 위해 임의 픽셀 독립 난수 대신 **2×2 블록 단위 + 블록 경계 흔들기**로
  클러스터를 만든다 (개정: 위 거친 밴딩 문단은 2026-10-12에 가변 pitch(1~3px)
  파절로 대체 — 규칙성이 사용자에게 거부됐다 (§대칭 개정 참조). (정확한 패턴은 구현이 고르되, 1픽셀 순수 static은 기각).
- **대칭 (validate_image의 mirror 불변식)**: 좌우 거울 면(MIRRORED_PAIRS)이 다르면
  `mirror` problem 으로 탈락한다. 그러므로 노이즈 인덱스는 거울 좌표를 정규화해야
  한다: 계수 추출 키 = `(part role(head/body/arm/leg), face_name, u, v)` —
  좌/우 팔다리가 같은 role+face+좌표면 **같은 계수**를 얻는다 (거울 대칭 유지).
- **시드 결정론**: `noise_seed` 는 후보 내용을 해시해 파생한다
  (observed 색 hex + attrs values + degrade + 후보 index → sha256 int).
  재생성·재다운로드가 같은 텍스처를 주고, ON/OFF 변형 쌍이 **같은 노이즈**를 유지한다
  (토글이 노이즈를 다시 섞으면 안 된다).
- **적용 대상**: 불투명 픽셀 전부 (머리·얼굴 포함 — 스티브도 그렇다). 알파는 건드리지
  않는다 (binary alpha 불변식 유지).

## 3. eval 프로브 의미 변경 (공개 결정)

`eval` 하네스는 `crown==hair · cheek==skin · torso==top`을 **픽셀 동등**으로 단다.
노이즈는 이 등식을 깬다. 변경:

- 프로브는 "기대색과 채널별 |Δ| ≤ 32" 톨러런스로 바꾼다 (`NOISE_MAX` 배율
  1.08 → 채널 최대 ~36 상향 위생 값 32는 warm shade에서 여유 있음 — 구현 시
  실제 상한에서 재계산하여 `NOISE_TOL` 상수로 고정하고 주석에 산출식을 남긴다).
- 프로브의 목적(헤어/상의 배선 스왑 같은 결함 나포)은 32 톨러런스로 유지된다.
  이 변경은 ledger 에 의미 변경으로 기록한다 (숨기지 않는다).

## 4. 렌더 API 결정

```python
render(observed, attrs, degrade, model, *, shoe_two_tone: bool = True,
       noise_seed: int | None = None)
```

- `noise_seed=None` → 노이즈 없음 (기존 동작 — 기존 테스트·플레이스홀더 무변).
  파이프라인(`candidates.build`)은 항상 시드를 넣어 호출한다.
- `shoe_two_tone=False` → 신발 블록만 구 단색(`shade(shoe, FACE_SHADE)`)으로
  되돌린다. 노이즈는 ON/OFF 양쪽 변형에 **항상** 같게 적용된다 (2톤 판정과 노이즈는
  독립 옵션이다).
- `candidates.build`는 후보마다 `noise_seed`를 파생해 render에 전달한다.

## 5. 백엔드/프론트 계약 (결정)

- **생성 시 2변형 선렌더** (서버 상태·재렌더 API 없음, 토글은 즉시·오프라인 안전):
  - `{token}_c{n}.png` — 지금과 같은 2톤 ON (기본). `skins` 응답 불변.
  - `{token}_c{n}_flat.png` — 신발 2톤 OFF 변형. **같은 노이즈 시드**로 렌더.
  - 응답에 `skins_flat: [url…]` 추가 (`skins` 과 같은 순서·개수).
- **프론트**: 카드마다 "Edit Skin" 버튼 → **`SkinEditor` 모달**:
  - 큰 `<Skin3DViewer>` (기존 컴포넌트 재사용, 크기 확장 가능하게), 표시할
    텍스처 URL은 토글이 고른다 (기본 ON).
  - 신발 2톤 토글 1개만 v1. 다운로드 링크는 현재 토글 변형을 내려준다.
  - 옵션 상태 구조는 확장 가능하게 (이후 옷/피부 옵션이 같은 모달에 붙는다).

## 6. 비목표 (v1)

- 픽셀 단위 손그림 편집, 옷/피부 변경, slim 모델, 2레이어(hat) 노출 — 전부 이후.
- 노이즈 세기·스텝 값의 정량 A/B — 이 건은 상수 튜닝 과제가 아니라 **시각 판정**이다:
  구현 후 fixed-10 샘플 보드(노이즈 on/off·서로 다른 후보) 사람이 본다.

## 7. 검증 원칙

- TDD: 시드 결정론(같은 시드 동일 텍스처), 시드 차이 → 텍스처 차이,
  mirror·alpha 불변식 통과, `validate_image` 통과 (noisy 렌더 포함),
  eval 톨러런스 프로브, TestClient `skins_flat` 계약.
- 시각: fixed-10 보드 A/B → 사람 판정 (지금까지의 A/B 보드 스타일), 웹 업로드 1장 e2e.

## 8. 결정 보충 (builder check 반영 — 내 판정, reject 자유)
1. **flat 렌더 소유**: `candidates.build` 가 후보마다 ON·OFF **둘 다** 렌더하고
   `Candidate` 에 `noise_seed: int` + `image_flat: Image | None = None` 를 추가한다
   (기존 위치 인자 생성은 영향 없음). app.py 는 파일 저장만 한다 — 시드 파생 로직
   사본을 만들지 않는다 (드리프트 원천 금지). **계약 테스트**: 같은 후보의 두 파일을
   픽셀 비교해 shoe 행 밖에서 동일함을 고정한다. flat 도 같은 `ok` 게이트를 통과한다
   (flat 검증 실패 = 렌더 결함이므로 500 처리 동일).
2. **eval 은 시드를 넣는다**: 파이프라인 수행 형태를 그대로 쟁다 — `candidates.build`
   와 eval 이 **같은 파생 함수** `derive_noise_seed(observed, attrs, degrade, index)`
   (공유 위치: `skinmaker/render.py`) 를 임포트해 쓴다. `--no-noise` 플래그는 만들지
   않는다 (YAGNI; 결함 나포는 ±NOISE_TOL 톨러런스가 계속 담당). 데이터 재인 기준이
   바뀌면 ledger 에 기록.
3. **시드 해시 입력 = 저장 후보 기준**: resolve_colors로 해석된 색 hex(관측 미신뢰
   값이 폴백해도 텍스처는 최종 픽셀 기준 고정) + **정렬된** attrs items + degrade +
   index → sha256. **근속 보장의 범위**: "같은 저장 후보는 언제나 같은 텍스처"다.
   같은 사진 **재업로드**는 VLM 응답이 바뀌면 다른 시드·다른 텍스처가 될 수 있다 —
   보장 아님을 여기에 명시한다 (VLM 비결정성은 스캐폴드 밖 문제).
4. **프론트 history 를 쌍으로**: 각 스킨 상태를 `{url, flatUrl, summary}`로 보관
   (인덱스 선택·삭제 로직을 객체 대상으로 이식). 새 결과 카드와 사이드바 이력 양쪽에
   Edit Skin 진입점이 있다. 사이드바 다운로드는 ON url(기존 파일명)을 계속 내려준다.

## 9. 노이즈 세기 슬라이더 (추가 2026-10-13, 생성 전 웹 선택)

- **계약**: `noise_level: float ∈ [0,1]`, 기본 1.0 (현행 동일 — 기존 호출자 무변).
  적용은 **크기 배율**: 각 톤 단계 s → `1 + (s-1)·level`. 같은 셀이 톤되지만
  부드러워져서 슬라이더가 연속 노브처럼 읽힌다. 레벨은 **시드에 넣지 않는다**
  (패턴 불변 — 시드 계약 §8.3 유지). `level == 0`은 무노이즈 렌더와 **바이트 동일**.
- **배선**: `render(..., noise_level=1.0)` → `_apply_noise(canvas, seed, level)`;
  `candidates.build(..., noise_level=1.0)` 가 ON/OFF 쌍 모두에 전달.
  API: multipart 필드 `noise_level` (부재 → 1.0; 숫자 아니면 400; 범위 밖 숫자는 [0,1] 클램프).
- **프론트**: 업로드 섹션 슬라이더 0–100% (기본 100), FormData에 실어 보냄.
  생성 후 에디터의 신발 토글과 독립 (레벨은 생성 시 고정).
- **비용 유의**: 슬라이더 실험 = 재생성 = Gemini 호출 1회. 생성 후 실시간 조정은
  토큰별 관측치 저장 + 재렌더 엔드포인트가 필요 — 별도 과제 (phase 2), 여기선 안 함.
- **테스트**: level 0 바이트 동일 · 단조성 (0.5 값이 기저와 1.0 사이) · 패턴 셀 불변
  (계수 공간) · API 부재/가비지/클램프 · 기존 후보·렌더 테스트 무변 (기본 1.0).

## 10. 하체 미관측 → jeans 기본 (추가 2026-10-13, 사용자 요청)

- **현상**: 상반신 사진에서 S2가 bottom="none" (크롭에 하의 없음) → 렌더가 맨다리+신발.
  뷰어 결함 아님 — 텍스처 자체가 맨다리였다 (픽셀 덤프로 확인).
- **신호**: `ObservedColors.lower_body_seen` (colors.extract, 파서 마스크:
  Pants/Skirt px 또는 BARE_LEGS(12,13) px 존재). None=파서 꺼짐/실패(기본 미적용).
- **룰** (`render.resolve_bottom_ex` → (garment, default발동)):
  S2 확신값 "none" + lower_body_seen is False + top != "dress" → **"jeans", True**.
  맨다리 보이는 전신은 none 유지 (D3 유지), 드레스 가드.
- **색**: 발동 시 `DEFAULT_JEANS = #3b5a86` (클래식 데님 청색, 사용자 결정) —
  관측 '하의' 샘플은 상반신에서 오탐(셔츠 꼬리)이므로 쓰지 않는다.
- **요약 정합**: app.py가 같은 결정을 summary에 반영 (derived 표기).
- **실측**: 사용자 avif + ex6(half) → jeans 발동; istock 전신 → none 유지.

## 11. 분류 카테고리 표시 (추가 2026-10-13, 표시 전용)

- 결과 화면에 LLM 분류 카테고리를 보여준다: 사람용 칩 (한글 라벨, 미지 값은 원문 폴백,
  불확실 필드 호박색, derived 표기 '*') + 접이식 **카테고리 JSON 표** (원본 JSON 값
  그대로: values 5필드 · uncertain · derived · coerced · noise_level · 후보별 varied).
- API 추가 필드: `attributes {values, uncertain, derived, coerced}` (jeans 기본
  발동분 반영 = 요약과 동일 근거), `candidates [{index, varied}]`, `noise_level`.
  JSON 복사 버튼은 pretty-print 원본 JSON을 클립보드로.
- 파이프라인·LLM 호출 변화 없음 (표시 전용). 검증: TestClient 2건 + build + 사람 확인.

## 12. 처리 과정 이미지 (추가 2026-10-13, 표시 전용)

- 결과 화면에 파이프라인 단계 이미지를 보여준다. 기존 QA 시트 디바이스
  (debugview.build_panels/contact_sheet)를 웹으로 노출 + 신규 **마스크 패널**
  (SCHP class map 색 오버레이 — 파싱 국소화 단계가 눈에 보이는 유일한 새 패널).
- 두 벌 (웹 토글로 전환): **간단** s0(사진+얼굴박스) → mask → s1(색샘플) → atlas(64×64),
  **전체 QA** s0 → s1 → atlas → uvmap → preview (+mask, seg 있을 때).
- 비용: LLM 없음, PIL 만. 파서 마스크는 app.py에서 **1회** 계산해 extract와
  패널에 같이 전달 (extract에 seg= 파라미터 추가 — 제공되면 재계산 안 함).
- 저장: `backend/static/steps/{token}_steps.png` (간단) / `_{token}_steps_full.png`
  (전체 QA) — 스킨 목록과 분리된 steps/ 하위폴더. 응답 `data.steps {clean, full}`.
- 프론트: 결과 화면 + 편집기 모달에 접이식 "처리 과정" 섹션 (간단/QA 토글, 원본 크기 링크).
