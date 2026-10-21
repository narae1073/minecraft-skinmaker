# SDD ledger — plan: docs/superpowers/plans/2026-10-15-hair-silhouette-refinement.md

Ruling: execute on current `master` rather than worktree — repository handover norm explicitly requires direct commits on master; cost if wrong: reduced isolation from unrelated work.
Spec: user-approved chat design (2026-10-15), A = head sides/back + body back/sides to observed length, short shoulder strands on front.
Pre-flight: Task 1 produces `HairStencil` per-column face profiles; Task 2 consumes the same type and adds body extent. Keep Task 1's legacy rule output and golden hashes, Task 2 body painting gated on `hair_source=mask` stencil evidence.
Initial HEAD: `8973626`.
Task 1: Ruling: side face profile width is 8, not 4 — `get_layout()` shows head is 8×8×8 and all head side faces are 8 columns; cost if wrong: half the legacy side fill disappears (the golden test caught this).
Task 1: Ruling: derive side/back profiles from post-arch, post-symmetry coverage before the front eye clamp — the clamp is a front-only face-template policy and must not shorten inferred side/back geometry; cost if wrong: longer side locks/back coverage get clipped to the eyes' safety boundary.
Task 1: complete (commits 8973626..4b54f3f, tests: .venv/bin/python -m pytest tests/test_hairstencil.py tests/test_render.py -q → 106 passed in 0.89s)
Task 2: RED verified: new tests failed because HairStencil had no `body_rows` and constructor rejected the new field. GREEN: `.venv/bin/python -m pytest tests/test_hairstencil.py tests/test_render.py tests/test_colors.py -q` → 185 passed.
Task 2: body extent = longest contiguous row run of Hair/Hat classes in a side corridor from face.bottom through one face height; maps ceil(run / face.h * 12), clamps at 12. Front only outer two columns × first two torso rows; back and sides extend to measured rows. Risk/cost if this interpretation is wrong: hair extends too little/much on torso; A/B validation will expose.
Task 2: complete (commits 4b54f3f..5f7e118, tests: .venv/bin/python -m pytest tests/test_hairstencil.py tests/test_render.py tests/test_colors.py -q → 185 passed in 61.02s (0:01:01))
Task 3: Ruling: cap observed torso hair at 6/12 rows (upper torso) and map a face-height of below-jaw hair to 6 rows, rather than scaling to the full 12-row torso — live A/B on `input_196882f56133.jpeg` showed the raw 12-row mapping reached the waist although the photo hair ends at the chest; cost if wrong: exceptionally long hair gets truncated before the waist (user can request longer drape).
Task 3 RED: `test_mask_stencil_body_extent_caps_at_upper_torso` failed against 12-row mapping (actual 12, expected 6); GREEN after upper-torso cap.
Task 3 A/B: ran `out/hair_ab.py` against archived peach-shirt woman (`input_196882f56133.jpeg`), man (`input_1586289351d3.jpeg`), crop-top woman (`input_b39cf826de70.jpeg`) for mask+symmetrized/raw/rule. Boards in `out/hair_ab/*_ab.png`; masks in `/tmp/opencode/*_masks.png`; enlarged preview boards in `/tmp/opencode/*_detail.png`.
Observed: man `body_rows=0` and short mask profiles; peach-shirt woman `body_rows=6` after cap (was 11, waist spill); crop-top woman `body_rows=4`. Head profiles are visibly nonuniform, and the ∩ background corners are filled only where adjacent mask evidence supports; explicit FACE/part cells remain skin. `rule` outputs continue to match the original golden hashes. Crop-top pale hair still resolves to default dark brown because its measured hair sample is unconfident — pre-existing hair-colour fallback, outside this shape/body-render scope (cost: her correct silhouette can still look dark).
Task 3: full suite `.venv/bin/python -m pytest -q` → 477 passed in 199.28s.
Task 3: Final review: self-review (no subagent; developer instruction prohibits delegation unless explicitly requested).
Task 3: complete (commits 5f7e118..a1b8be8, tests: .venv/bin/python -m pytest -q → 477 passed in 165.91s (0:02:45))
Final review: self-review (no subagent). Diff review checked plan alignment, tests, mask→stencil→renderer wiring, rule golden hashes, body-row cap, classic/slim validation, and `git diff --check` (clean). No Critical/Important implementation findings.
Final: Ruling: leave pale-hair colour confidence/fallback unchanged — this approved segment is silhouette/body geometry; the crop-top sample's color-confidence failure is a separate measurement-policy task — cost if wrong: that blonde can still render dark brown despite corrected geometry.

## 후속: 머리선 다듬기 (2026-10-15, 사용자 목업 승인)
- 사용자 결정(목업 리뷰): ① 뒤통수는 머리가 있으면 가득(대머리만 피부) ② 정면 머리선은 '사진 머리선' 추적 ③ 위 모서리 피부 구멍 금지 — "머리 있는 열은 0행부터".
- 룰링: 위 구멍 금지(closure)는 모든 열에 적용 — 승인 문장 "every hair column reaches the top edge"의 문자 그대로. 결과: 0행 가르마(scalp) 셀도 아래에 머리가 있으면 덮인다. 틀렸을 경우 비용: 정수리 가르마 표현이 위 1행에서 사라짐 (test_mask_stencil_covers_arch_corners로 문서화).
- 룰링: 트림은 가운데 열(1-6)만, ceil(t*8) 1..3행 클램프(눈 보호 유지), 대칭화는 mirror-max. 옆열(0,7)은 사진 그대로.
- 실사진 검증: 남 [3,2,1,1,1,1,2,3] / 여 [8,3,3,1,1,3,3,8] — 승인 목업과 일치. 전체 스위트 481 passed.

## 후속 2: 옆면 머리선 연속 (2026-10-15)
- 사용자 지적: "머리선이 끊김 없이 자연스럽게 흘러야" — 진단: 뒤통수 가득 이후 옆 프로파일이 앞-안쪽 깊이(heights[3]/[4])로 수렴해 뒤 모서리에 최대 5행 단차 (남 side 3,3.. vs back 8; 여 side 8→3 vs back 8).
- 룰링: 옆면 머리선 = 앞 가장자리(관자 깊이) → 뒤통수 끝값(가득 8) 선형 보간. 대머리(0) 가드와 모호크(옆 0) 가드는 유지 — 틀렸을 경우 비용: 옆이 뒤로 갈수록 관측보다 조금 더 덮임 (짧은 머리도 뒤쪽은 가득 뒤통수와 이어짐).
- 검증: 남 left/right (3,4,4,5,6,7,7,8)·여 (8,)*8, 앞 모서리(3=3, 8=8)·뒤 모서리(8=8) 연속. 스위트 482 passed.

## 후속 3: 얼굴 디자인 (2026-10-20)
- 사용자 결정: 안경·입·눈썹 없음, 눈 4-5행(한 행 아래), 수염은 턱 6-7행(입이 없어 full은 전폭), 앞머리는 사진 추적 유지하되 눈이 내려가 상한 4행(3행까지), 수염 픽셀은 머리선 추적으로 오인 금지(스캔 얼굴 위 55%).
- 근거: 34장 검증 — VLM glasses 33/33(안경 제거로 폐기), beard 존재 32/33, 표정 28/33(입 제거로 폐기). 홍채는 눈 밴드 어두운 픽셀(색기 상위)에서 측정, 양쪽 눈 필요 — 7장 실사진 전부 confident.
- 룰링: 얼굴 템플릿 변경은 전역(rule 포함) — 골든 해시 재기록(2026-10-20). 대가: rule 베이스라인이 얼굴까지 새 스타일.
- 스위트 491 passed.

## 후속 4: 겹쳐 입은 상의 (2026-10-21, 사용자 선택 C)
- 범위: 목 V·라펠 + 커프스 + 타이까지. VLM 필드 inner_top(none/shirt/tee/knit)·neckwear(none/tie) — 10장 검증(존재 8/9, 503 재시도 필요).
- 색: 겉옷 표본 = 넓은 상체 상자에서 배경 크로마 제거 + 피부 오인 가드(명도 포함) — 흰 셔츠·배경이 정장색을 오염시키는 문제(310/43/8이 흰색으로 렌더) 해결. 안쪽/타이 = 기준색과 RGB 대비 군집(크로마 전용은 검정↔흰 구분 실패). 픽셀 게이트 미달 시 안쪽은 밝은 셔츠 기본, 타이는 그리지 않음(승인 규칙).
- 룰링: 겉옷 표본은 재킷류/레이어드에만 적용(픽셀 ≥400). 타이는 색 측정 시에만 렌더. 실사진 측정은 부분 성공(43 안쪽 ✓; 310 타이 ✓; 61/4/8 안쪽 폴백) — 포즈 모델 비활성(pose_landmarker...disabled)이라 칼라 기하가 얼굴 비례라 한계. 스위트 500 passed.

## 후속 5: L2(오버레이) 헤어 (2026-10-21, 사용자 선택 "all three")
- 범위: 부피 셸(실루엣 복제) + 앞머리 1행 연장(가르마선 ≤2행 열만, 눈 4-5행 금지) + 몸통 드레이프(오버레이 레이어). 요청 스위치 hair_overlay=on|off (기본 on).
- 배선: ObservedColors.hair_overlay → render()가 rule/mask 공통으로 L2 패스. 백엔드 폼 필드·응답 에코·시트 스탬프(overlay=on/off) — 진실 규칙 유지.
- 프론트: 설정에 'L2 머리' 선택, 3D 뷰어에 오버레이 박스(레이어1 rect +0.0625) 추가. lint 통과(미뤄둔 Skin3DViewer immutability 3건도 이번에 수정: texture.clone useMemo).
- 골든 재기록(L2 기본 on이 이미지 바이트를 바꾼다). 스위트 502 passed.

## 후속 6: L2 사고 수정 (2026-10-21)
- 사용자 보고: L2 on/off 무관하게 한 팔·한 다리가 이상한 색. 원인: Skin3DViewer 의 왼팔/왼다리 L2 rect 오프셋을 (0,+16)으로 적용 → 레이아웃의 (48,48)/(0,48) 대신 (32,64)/(16,64) = 텍스처 밖 → GPU 클램프로 가장자리 색이 칠해짐. 생성 PNG 자체는 정상(네 팔다리 L2 모두 투명 0px 확인).
- 수정: LARM2 +16,0 / LLEG2 -16,0. 가드: JS rect 상수를 format.get_layout()과 대조하는 테스트 추가(과거 오프셋이면 실패 확인 — rect y=68). lint/빌드/스위트 503 passed.

## 후속 7: 민소매·끈나시 상의 오분류 (2026-10-21)
- 사용자 질문: 목이 드러나는 사진에서 "상의 없음" — YuNet 탓인가? 아님. YuNet=얼굴 검출기(옷 무관). 실제 원인: VLM이 캐미솔 사진(images24.jpeg)을 top_garment=none으로 분류(두 질의 불일치, uncertain=top_garment), 후보 변형은 hair_length/sleeve_len만이라 대안이 안 나옴. S1은 상의색(#e9f5f1, confident)을 정상 측정.
- 수정: 프롬프트 규칙 — 민소매/끈나시/탱크톱/캐미솔도 상의(가장 가까운 종류, sleeve_len=none); none은 맨몸만. vary_fields에 top_garment 추가(두 질의 불일치 시 옷 입은 대안 후보).
- 검증: 같은 사진 재분류 → top_garment=tee, sleeve_len=none, uncertain=none. 스위트 505 passed.
