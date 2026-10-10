# CONTEXT.md — 프로젝트 인수인계 문서

새 세션의 AI 또는 사람이 이 파일 하나만 읽고 계속 일할 수 있게 쓴다.
토론 이력은 요약하지 않고 **결정과 그 이유**를 남긴다. 근거를 기억한 AI가 같은 논쟁을 반복하지 않도록.

최종 갱신: S4 후보+검증 완료. 테스트 277개 통과 시점.

---

## 1. 이 프로젝트가 뭔가

사람 사진 → Minecraft 스킨 PNG(64×64).
배경: 형제 프로젝트 `~/Programming/crawler`는 고양이 동영상 크롤러. **완전히 무관하며 섞지 않는다** (초상권·법적 위험).

---

## 2. 요구사항 (이것이 모든 설계의 근거)

> **얼굴과 헤어는 정확히 안 닮아도 되고 비슷하게만 만들면 된다.**

이 한 줄이 설계 무게중심을 완전히 옮겼다. 다음을 의미한다:

- 얼굴은 enum 으로 끝난다. 8×8=64픽셀에 정체성을 담을 수 없다.
- 헤어 실루엣은 창작해도 된다. 관측은 색만.
- **관측 불가능한 75%** 가 진짜 품질 문제다. (14개 면 중 4개만 관측 가능)
- 위 요구사항을 **내면화하지 못한 AI가 이 문서를 critiq 하는 실수를 반복해서 했다.** 요구사항이 바뀌면 enum 오류 비용 순위가 뒤집힌다 (얼굴 필드 관대, 의상 필드 엄격).

---

## 3. 이미 확정한 사실 (다시 조사하지 말 것)

### 3.1 포맷 — 4중 교차검증 완료

| 검증 | 결과 |
|---|---|
| 위키 수치 (레이어당 classic 1632 / slim 1568) | 코드 합계 3264 / 3136 — **정확히 일치** |
| **vanilla `ModelBox` 소스** 6개 quad 해석 | 머리/몸통 면 좌표 **정확히 일치** |
| Mojang `player_armor.json` (`uv:[40,16] + "mirror":true`) | 좌우 관계 일치 |
| 독립 구현 xJamp 24개 좌표 대조 | 20개 일치. 4개는 그쪽의 좌우 *이름* 오류 (좌표는 같음) |

vanilla `ModelBox` 의 quad → rect (u=texOffsU, w=폭, d=깊이, h=높이):

```
[2] (u+d,     v,     w, d)  TOP
[0] (u+d+w,   v,     d, h)  BOTTOM
[1] (u,       v+d,   d, h)  −X 면
[4] (u+d,     v+d,   w, h)  FRONT
[3] (u+d+w,   v+d,   w, h)  +X 면
[5] (u+d+w+d, v+d,   w, h)  BACK
```

머리는 `u=0` 이 −X = 플레이어 오른쪽 → **RIGHT 가 x=0**. 위의 UV 가이드 이미지와 일치.

### 3.2 픽셀 예산 (레이어당)

| 부위 | 픽셀 | 占比 | 성격 |
|---|---|---|---|
| 머리 8×8×8 | 384 | 23.5% | 정면 64px + 모자 레이어 |
| 몸통 8×12×4 | 352 | 21.6% | 상의 |
| 팔 4×12×4 ×2 | 448 | 27.5% | 소매 + **손 (총 160px, 4.9%)** |
| 다리 4×12×4 ×2 | 448 | 27.5% | 바지 + 신발 |

**정면 얼굴 64px = 전체의 1.96%. 정체성은 헤어+의상(약 87%)이 결정한다.**
팔 측면은 4×12 한 장이라 사실상 단색만 가능. 넓이는 고정이고 우회 방법이 없다.

### 3.3 알파 규칙 (앞선 오류 정정)

- **Java**: 외곽 레이어는 부분 투명(1~255) 허용, **내곽 레이어만 완전 불투명 강제**
- **Bedrock**: 0/255 만 허용
- 1.8+ 기준 사용 가능 픽셀: classic 1,632 / slim 1,568 (레이어당)

### 3.4 slim 모델

앞/뒤 면만 3px, 깊이(좌우 면)는 4px 유지. 박스 폭이 줄므로 back 면 시작 x 가 1px 이동(51).
4번째 열은 게임이 무시한다.

### 3.5 렌더링 확인 방법

- **Java**: 시그니처 검증이 있어 minecraft.net 업로드 + 正版 계정 필요
- **Bedrock**: PNG 를 `com.mojang/custom_skins/` 에 복사만 하면 즉시 확인. 계정 불필요
- 따라서 30초짜리 검증이 있는데 **지금까지 실행하지 않았다** (아직 하지 않은 최우선 항목)

### 3.6 환경

- 프로젝트: `~/Programming/skinmaker` (crawler 밖으로 이동 완료)
- venv: `.venv` (python3.12 로 2026-10-10 재생성. 기존 것은 /home/jasen 경로+python3.13 잔재라 깨져 있었음)
- **GPU 2070 Super 는 별도 Windows 컴퓨터에 있다.** 이 환경에서는 보이지 않는다 (`nvidia-smi` 없음). 8GB, Turing(7.5) → **bf16·FA2·fp8 미지원**
- 이 환경 RAM 7GB, 8코어, node 없음

---

## 4. 확정된 파이프라인

```
사진
 └─ S0 입력 판정 (코드)           ✅ 완료   YuNet + 품질 4지표 + 저하 계획
 └─ S1 관측 추출 (코드)           ✅ 완료   skin-referenced 화이트밸런스 + 클러스터 모드
 └─ S2 분류      (VLM 1회)       ⬜ 진행 중  5개 enum 필드만. 픽셀 0개
 └─ S3 렌더      (코드)           ⬜         픽셀 100%
 └─ S4 후보+검증 (코드)           ⬜         후보 3개 무순위
```

### 핵심 불변식

```
AI 가 만드는 것  :  enum 값 5개 + hair_bbox + 불확실성     ← 픽셀 0개
코드가 만드는 것:  3,264 픽셀 전부
```

### 하드 게이트는 1개뿐

`얼굴 검출 실패` 만 거부한다. 나머지(blur/dark/bright/small/flat)는 **거부가 아니라 렌더러 파라미터**다.
품질이 나쁘면 같은 결과가 아니라 **다른 결과**(더 보수적인 렌더)를 낸다.
게이트 4개를 쌓으면 곱으로 발산해 거부율이 35~55% 가 된다. 곱셈을 계산할 것.

### S2 스키마 (확정)

```json
{
  "top_garment":    "tee|hoodie|jacket|shirt|sweater|vest|uniform|apron|overalls|dress|none",
  "bottom_garment": "jeans|shorts|skirt|pants|none",
  "pattern":        "plain|vertical_stripe|horizontal_stripe|check|plaid|graphic",
  "sleeve_len":     "none|short|three_quarter|long",
  "hair_length":    "short|medium|long|very_long",
  "hair_bbox":      [x0,y0,x1,y1]
}
```

- **색 필드는 넣지 않는다.** S1 이 코드로 정확히 읽는다. VLM 에 색을 물으면 회색 셔츠를 네이비로 부른다
- **`glasses`/`beard` 는 v1 에서 제외.** 오탐 시 머리 전체에 1px 셸이 생겨 눈에 띄는데, 요구사항상 얼굴은 관대하므로 비용 대비 이득이 없다. 필드를 줄이면 정확도가 오른다
- `hair_bbox` 는 Qwen2.5-VL 의 visual grounding 용도. **헤어 색은 코드가 읽는다**

### 스키마 方言 주의 (실제로 밟은 함정)

정본은 **표준 JSON Schema(소문자 타입)** — `attributes.build_schema()` 하나뿐.
전송 계층마다 方言 이 다르다: **Gemini `responseSchema` 는 대문자(OpenAPI), Ollama `format` 은 소문자(Go 바인딩)**.
Gemini 는 `_gemini_schema()` 가 변환한다. 변환 없이 그대로 넘기면 400 이 난다.

### enum 은 독립이 아니다 (실제 모델을 돌려서 발견)

`top_garment=none` 인데 `sleeve_len=long` 을 내놓는 모델이 있었다. 스키마로는 강제되지 않는다.
→ `attributes.apply_cross_rules()` 가 코드에서 막는다. 위반은 `Attributes.derived` 에 **기록**한다(숨기지 않음).

### 불확실성 신호

- self-reported `confidence` 는 **쓰지 않는다** (교정 안 되고 프롬프트에 극도로 민감)
- ~~logprob 엔트로피~~ → Ollama 가 per-token logprobs 를 주는지 **미확인**
- 대안(무조건 동작): **순서 교환 이중 질의**. 필드 순서를 뒤집어 2회 호출, 일치하면 confident. 무료 티어에서 무비용
- ⚠️ Ollama 의 `format` 스키마 강제는 enum 을 강제하므로 **"coerce 발생" 신호를 무효화**한다. 강제와 측정이 충돌함

---

## 5. 이미 기각된方案 (재제안 금지)

| 기각 | 이유 |
|---|---|
| **확산 모델 / P4 보강** | 8×8 얼굴에 SDXL 을 걸면 텍셀 격자가 출력 공간에 없어 색 얼룩이 된다. 384px 헤어도 6면이 분리된 조각이라 일관성 보장 불가. 요구사항("비슷게만")이 이미 충족됨. **GPU 2070S 는 이 프로젝트에서 놀게 된다** |
| **SAM / 세그멘테이션** | 분할은 "마스크"를 주는데 UV 채우기엔 "표준 표면 샘플"이 필요하다. 그 갭은 코드가 이미 메운다. 게다가 평면 색칠된 블록 아트에서 SAM 마스크 품질이 급락 |
| **파인튜닝 (LoRA 등)** | 배울 대상이 이미 코드에 있다 (UV 레이아웃을 정확히 아는 코드). 8GB 에서 SDXL LoRA 라도 7~9시간 + 데이터셋 |
| **FLUX.2 [dev] 32B** | FP16 70GB / INT4 18GB 최소. group_offload 에도 시스템 RAM 32~96GB |
| **헤어/얼굴 분할 생성 후 조립** | 부품별 독립 생성은 전역 팔레트 일관성을 파괴한다. 512px 를 만들어 96px 로 줄인 뒤 8색으로 양자화하면 생성 정보의 0.1%만 살아남는다 |
| **중앙값 + VLM 색 하이브리드** | 두 측정 대상을 혼동한 것. 중앙값="이 사진에 찍힌 색", VLM="조명 무시한 색". 역광에서 어긋나는 건 오류가 아니라 목표 모호함. 중재 불가능 |

---

## 6. 현재 코드

`~/Programming/skinmaker/skinmaker/` · 2,604 LOC · **테스트 108개 통과**

| 파일 | 담당 | 상태 |
|---|---|---|
| `format.py` | UV 레이아웃 상수. `get_layout()` 이 위키 수치와 대조해 틀리면 예외 | ✅ |
| `canvas.py` | 픽셀 쓰기. `LEFT_PARTS` 는 자동 미러 | ⚠️ **비대칭 미지원** (아래 결함) |
| `validate.py` | 6개 불변식 (size/mode/overlap/bleed/base_alpha/mirror) | ✅ |
| `preview.py` | 3면 프리뷰 (front/side/back/top/overlay) | ✅ |
| `uvguide.py` | 색으로 코딩된 UV 가이드 이미지 | ✅ |
| `quality.py` | S0: YuNet 검출, 품질 4지표, 저하 계획, 샘플 영역 기하 | ✅ |
| `measure.py` | S0: 배치 계측 CLI | ✅ |
| `colors.py` | S1: 화이트밸런스, 클러스터 모드, 신뢰도, `top_skinlike` | ✅ |
| `debugview.py` | 단계별 시각 패널 5종 + registry | ✅ |
| `samples.py` | contact sheet CLI | ✅ |
| `placeholder.py` | 더미 스킨 (E2E 증거) | ✅ |

### 명령어

```bash
cd ~/Programming/skinmaker
.venv/bin/python -m pytest -q                      # 108 tests
.venv/bin/python -m skinmaker.measure <사진폴더>    # S0 계측
.venv/bin/python -m skinmaker.samples <사진폴더>    # 단계별 contact sheet
.venv/bin/python -m skinmaker --model classic      # 더미 스킨 + 프리뷰
```

### 시각 샘플 (단계마다 눈으로 봐야 한다)

> **2단계에서 잘못 남긴 비트는 4단계에서 절대 못 찾는다.**

```bash
.venv/bin/python -m skinmaker.samples out/s0_photos -o out/samples
```

패널: S0(얼굴박스+샘플영역) / S1(원본 vs 보정 + 추출 HEX·점유율) / S3 atlas / S3 UV 가이드 합성 / S4 3면 프리뷰.
**이 도구가 실제로 설계 결함을 3건 잡았다** (아래 7절).

---

## 7. 시각 샘플이 잡은 실제 결함 (반복하지 말 것)

1. **`hair_region` 이 모자를 헤어로 인식.** 얼굴 박스 안쪽 상단 1/3 만 잡았다. YuNet 박스는 얼굴에 밀착하는데 긴머리는 전부 박스 밖이다. → **사방 확장**(위 35%, 좌우 10%) + `clip_to()` 추가
2. **`skin_region` 이 눈·입을 포함.** 얼굴 높이 33~83% 는 눈 구간(45~55%)을 포함해 중앙값이 흰자국으로 끌려감. → **55~83%(볼·코)**
3. **화이트밸런스가 사진을 망가뜨림.** `wb_gain=0.76,1.14,1.00` 로 전체가 초록으로 물듦. 원인이 "평균"이었음. 피부 영역에 그림자·배경·모자 테두리가 섞이면 평균이 피부가 아니고, skin-referenced 보정은 그 오염을 **상쇄가 아니라 증폭**한다. → 중앙값, 클립 1.6→**1.25**, 크로마 드리프트 >0.20 이면 보정 중단
4. **갈색 셔츠를 색상 탈락이 죽임.** 피부 크로마 탈락을 옷에도 적용하니 상의가 전부 missing. **갈색/베이지 셔츠는 피부와 크로마가 닮았다.** → **크로마 탈락은 헤어에만.** 의상은 공간 인셋 + 최빈 점유율
5. **`top` 이 셔츠가 아니라 맨살.** 81% 점유율의 색이 목·어깨에서 나옴. 맨살과 살구색 셔츠는 색이 같아 **구별 불가** → `ObservedColors.top_skinlike` 플래그로 노출

### 남은 한계 (정확히 기록)

**헤어 = 모자.** 모자를 쓴 사진에서 헤어 영역이 갓이라 `hair` 값이 무용(점유율 2% → `low` 로 표시되지만 값은 못 씀).
**솔루션은 S2 의 `hair_bbox`.** 얼굴 박스 기하로는 못 푼다.

---

## 8. 알려진 결함 (S3 전에 반드시 처리)

| 결함 | 처리 |
|---|---|
| `canvas.put()` 이 좌우를 강제 미러 → **비중앙 파팅 헤어 표현 불가** | 미러를 opt-in 으로 변경, 검증기의 `mirror` 도 파트별 on/off (`head` 만 비대칭 허용) |
| YuNet 모델(232KB) 미커밋 | README 에 fetch 명령 있음. `SKINMAKER_YUNET` 로 경로 지정 |
| 포즈 모델은 이 머신에서 사용 불가 | Pentium G6400 에서 mediapipe 네이티브 로드가 SIGILL 로 죽음. `assets/*.task.disabled` 로 격리, 얼굴 비례 밴드로 폴백. 집 Ubuntu 에서는 파일명 복원 후 사용 |
| Java 시그니처 미검증 | 사람이 30초. Bedrock 에 복사 |

---

## 9. 배포 목표 (결정됨)

```
브라우저/폰 ──업로드──▶ 집 Ubuntu (웹 호스팅 + S0/S1/S3/S4)
                            │
                            └──HTTP──▶ Gemini API (유일한 AI 호출)
```

- 렌더는 집 Ubuntu 에서. AI 호출만 외부
- Tailscale/작업 큐/Windows 워커 **불필요**
- **비용 ≈ $0.001/장**, Gemini 2.5 Flash 무료 티어 250 req/일 (Lite 1,000/일)
- ⚠️ 무료 티어는 입력이 학습에 쓰일 수 있음. 유료 Tier 1 은 `No` 이고 비용이 무의미하므로 **프라이버시 중요하면 바로 유료**
- ⚠️ 2026-10-10: 2.5 시리즈(flash·lite) 신규 사용자 퇴역 확인. 기본 모델을 `gemini-3.1-flash-lite` 로 교체. 에러문구가 권한 없는 모델명(3.5/3.8)을 안내하므로 모델 목록 API 로 실재 확인 후 지정할 것
- Colab 은 서버가 아님 (URL 없음, 세션 휘발). **측정/모델 A-B 용도**로만

---

## 10. 남은 작업 순서

```
① [30초]  out/placeholder_classic.png → Bedrock com.mojang/custom_skins/ → ✅ 뜸 (2026-10-10 확인)
② [반나절] 50장 계측 (정면20/측면10/역광10/어두운 피부10)
           python -m skinmaker.measure out/gate50
           → 거부율이 S1 임계값을, brightness/saturation 분포가 보정 전략을 정한다
           (2026-10-10: 91장으로 계측. 검출79·거절12(13.2%)·small13·blur2·dark2.
           거절 12장 전수 육안 확인 → 전부 실루엣·뒷모습·극역광이라 정당한 거절.
           어두운 피부 미검출 편향 없음. 일반 믹스에서는 7.7%였으므로 10% 목표는 유지.
           avif 7장이 빠져서 SUFFIXES+pillow-avif-plugin 추가함)
③ [1일]   S2 transport 분리 구조 (Gemini / Ollama / Colab 교체 가능한 구조)
④ [1.5일] S3 파라메트릭 렌더 (얼굴 enum · 헤어 정면24+파생5 · 의상 enum · 75% 규칙표)
⑤ [0.5일] S4 후보 3개 + 검증
           (2026-10-10 완료: `candidates.build` + `s4.py` CLI + 테스트 6개.
           변형 근거는 이중 질의 불일치만. vary=`hair_length`·`sleeve_len`.
           일치하면 후보 1개, 근거 없는 변형 금지. cross 규칙 재적용+중복 제거.
           전 후보 validate_image 통과. 무순위.)
⑥ [1.5일] 웹 (FastAPI + JS 캡처·다운스케일 + pixelated 표시 + skinview3d CDN)
           (2026-10-10 진행 중: 친구 Vite 앱 `frontend/` 병합. `backend/app.py` 가
           `/api/v1/generate-skin` 계약 구현. 8000 충돌로 백엔드는 8001+프록시 수정.
           messi5·lena e2e 통과. 남은 것: dist 정적 서빙 확인, 에러 UX(422 문구).)
```

### S2 의 transport 분리 요건

VLM 호출부만 교체 가능해야 한다. 그 결과로 Colab(Gemma/qwen)·Gemini·Ollama 를 **같은 코드로 비교**할 수 있어야 한다.
후처리·폴백·불확실성 판정은 전송 계층과 무관하게 유지.

---

## 11. 하지 말 것

- 확산 모델/SAM/파인튜닝 재제안
- 요구사항(얼굴은 관대, 의상은 엄격)을 되돌려놓기
- 3면 프리뷰를 후면 없이 평가하기 — 정면은 관측된 면이라 평가력이 없다
- 게이트를 쌓아가며 곱셈 계산 안 하기
- 게이트가 "개선율 10%" 처럼 기준선 자체가 없는 형태가 되는 것 — 객관 지표(검출 실패율·대칭·형식·점유율)만 쓰기
