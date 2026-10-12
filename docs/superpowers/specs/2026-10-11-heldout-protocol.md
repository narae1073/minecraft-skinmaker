# held-out 라벨 세트 프로토콜 (2026-10-11)

상태: 인프라 완성 (샘플러 `skinmaker/heldout.py`, 게이트 판정표 아래). 라벨 미작성.
소속: B 경로 — "bottom_eval 59장이 오염됐는가 / 무엇으로 재검증하는가".

## 1. held-out 이 답하는 질문 (왜 59로는 안 되는가)

- `bottom_labels.json`의 **59장 scored 세트는 이제 적합(fitting) 세트다.**
  F1 (blue luma 게이트 40→25, 커밋 `c84438c`)의 상수 `25.0`은 그 세트의 4장 navy
  (예: `#141a25` luma 25.5) 바로 아래에 맞춰졌고, F2·grain 도 같은 59장으로
  채택/기각했다. 이 세트로 측정된 0.644 는 "F1 이 일반화한다"의 증거가 아니라
  "F1 이 이 세트에 맞는다"의 증거다.
- held-out 이 유일하게 답할 수 있는 질문 3개:
  1. **F1 일반화**: luma 25 게이트는 4장 navy 이외의 짙은 네이비에서도
     `1.645σ` 한계 안에서 성립하는가 (held-out agreement ≥ 아래 표 기준).
  2. **임계 과적합 실재성**: colored/light/mid 경계(미결 후보들)가 59장 특유의
     예시가 아니라 실제 분포 문제인가.
  3. **미래 A-B의 오염 없는 기준**: A(교차군 병합 등 product 변경)의 효과를
     적합 세트로 측정하지 않고 비교할 수 있는 유일한 무결 비교 대상.

## 2. 오염 정의와 제외 규칙

- 제외 대상: `docs/superpowers/specs/bottom_labels.json` 의 **모든 키(83장)**.
  scored 59장만으로는 안 된다 — none/unclear 24장도 라벨러가 봤고, 오염의 단위는
  "파이프라인 산출물 없이 색을 본 적 있는 사진"이다.
- 자동 검사: `python -m skinmaker.heldout` 이 `already_labeled` 로 배제한다.
  동결 후 `heldout_labels.json` ∩ `bottom_labels.json` = ∅ 인지 사람이 1회 확인.

## 3. 풀의 현실 (2026-10-11 실측, `heldout_manifest.json`)

| 구분 | 수 |
|---|---|
| 풀 (`out/s0_photos`) | 98 |
| 이미 라벨됨 | 83 |
| 미라벨 + 얼굴 없음 | 14 |
| 미라벨 + 확장자 없는 잔여 (`images24jpeg`) | 1 |
| **disjoint·검출 가능 후보** | **0** |

→ **현 풀에서 held-out 은 0장**. N=30 이상을 만들려면 새 사진이 필수다.
`images24jpeg`는 `images24.jpeg`(라벨 colored)의 확장자 유실 중복으로 보이므로
소유자가 삭제 판단을 한다 (이 작업은 측정 전용이라 건드리지 않는다).

## 4. 목표 크기와 판정표 (F1 게이트)

- 목표 **N=45** (최소 30). 95% 반폭은 `1.645·sqrt(p(1-p)/n)`, `p=0.644` 가정.
- 합격 규칙: held-out mask-on agreement 가
  `0.644 − 1.645·sqrt(0.644·0.356/n)` 이상이면 F1 일반화 통과.

| N | 합격 하한 | 실패 기준 |
|---|---|---|
| 25 | 0.49 | < 0.49 |
| 30 | 0.50 | < 0.50 |
| 40 | 0.52 | < 0.52 |
| 45 | 0.53 | < 0.53 |
| 60 | 0.54 | < 0.54 |

- 실패하면: 0.644 를 "세트 특유"로 기록하고, A(교차군 병합) 등 그 어떤 상수
  튜닝도 held-out 기준으로 다시 검증 전에 진행하지 않는다.

## 5. 라벨링 프로토콜

1. **라벨러**: 사람(소유자)만. AI는 라벨 금지 — 측정 대상이고 실패 4장을 본 당사자다.
2. **맹검**: 라벨 전에 파이프라인 출력(contact sheet·rendered skin·필터 결과)을
   보지 않는다. manifest는 파일명·face_h/img_h만 담고 색 정보가 없으므로
   이미지를 열기 전 배제 검사에 쓸 수 있다.
3. **사진당 단일 범주**: `blue / dark / light / mid / colored / none / unclear`
   (정의는 `bottom_labels.json` 헤더와 동일). 범주는 **옷 그 자체** 기준; 씬 조명은
   눈에 보이는 대로. 두 범주 사이면 그중 하나를 고른다 — 기권은 none/unclear 뿐.
4. **기록**: `docs/superpowers/specs/heldout_labels.json`, 스키마는
   `bottom_labels.json`과 동일 (`{"labeler": ..., "categories": [...], "labels": {...}}`).
   커밋 = 동결. 동결 후에는 라벨 수정 금지(오탈자는 별도 커밋 + 설명).
5. **신뢰도 (권장)**: 동결 후 최소 하루 뒤 재판정 1회 → intra-rater 일치율 기록.
6. **측정**: `python -m skinmaker.bottom_eval --labels docs/superpowers/specs/heldout_labels.json`
   (bottom_eval.py:160-165 이미 지원). 분모 규칙은 현행과 동일 — none/unclear 제외.
7. **튜닝 금지**: 이 세트는 게이트 질문(§4)에 처음 쓰이고, 이후 product 변경
   평가 세트로 남는다. **어떤 상수 결정에도 적합 용도로 재사용하지 않는다.**

## 6. 절차 (보충 사진 준비 → 동결 → 판정)

```bash
# 1. 새 사진 40~50장을 임의 폴더에 (조명·장면 다양성, 파일명 중복 주의)
# 2. 샘플 + manifest
python -m skinmaker.heldout --source <새폴더> --n 45 \
  --out docs/superpowers/specs/heldout_manifest.json
# 3. 사람 라벨링 → heldout_labels.json 작성 → 커밋(동결)
# 4. 게이트 측정
python -m skinmaker.bottom_eval --labels docs/superpowers/specs/heldout_labels.json
# 5. §4 판정표로 go/no-go
```

현재 manifest(전량 shortfall)는 풀 고객을 기록한 스냅샷으로 커밋한다.

## Addendum — 2026-10-11 (pre-labeling pin)

- Pool: 49 face-detectable photos from heldout-photos/ (70 files, 21 no_face).
- n (gate denominator): scored count from `bottom_eval --labels`, after none/unclear exclusion.
- Threshold: §4 formula 0.644 − 1.645·sqrt(0.644·0.356/n) at that exact n.
- Floor: if scored < 30, no verdict.
- Band mix: full 25 / mid 15 / portrait 9. Portrait n=9 underpowered for per-band claims; aggregate only.
- Label distribution: blue=15, colored=13, dark=6, light=6, none=7, mid=2, unclear=0.
- Distribution caveat: mid=2 (4%) vs fitting set's ~14%. The held-out under-represents neutral-gray garments. If the aggregate passes, the verdict holds for the dominant categories (blue/colored/dark/light) but NOT for mid — mid is underpowered. If the aggregate is borderline, a supplementary mid-focused check is warranted after the gate, not before.
- Anchor caveat: 0.644 is the fitting-set result of F1; this is a generalization check of a post-hoc number.

## Addendum — 2026-10-12 (decision: labels are ground truth)

- **Decision (a):** the 7-category label set is declared **ground truth**. It is not an instrument to be redefined. Category definitions stay as written; no category merge/drop.
- **Rationale:** the reliability disambiguation (pass 2 intra-rater, rater B inter-rater) was **declined**, so the label noise floor is unmeasured. Redefining categories without a reliability measurement would be unverifiable and would leave the next gate equally ambiguous. The "instrument is broken" hypothesis is therefore **untested, not resolved** — recorded as a standing risk.
- **Consequence for the metric:** `bottom_eval` agreement is a **relative A/B signal only**, never an absolute quality number. The gate result 0.476 (n=42) means "pipeline vs a single coarse human pass of unknown consistency"; it is not evidence about the pipeline alone.
- **Gate record:** §4 verdict stands — observed 0.476 < threshold 0.52 (n=42) → **FAIL**, 0.644 recorded as set-specific. Path A (cross-bin merge) and all constant tuning remain **blocked** until re-verified on a fresh held-out. The 49 are consumed; they must not be reused as a fresh gate.
- **Next work:** mechanism diagnosis of the real misses (decomposition: localization 8, pose/framing 2) — diagnosis only, **no constant changes**, and any candidate fix is validated on the fitting set first, then a **new** held-out, never tuned against the 49.
- **Anchor set:** `docs/superpowers/specs/anchor-set/` (2 fitting-set photos, `mid` and `colored`) retained for any future rater-facing calibration; unused under decision (a).
