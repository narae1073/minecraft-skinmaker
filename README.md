# skinmaker

사람 사진 → Minecraft 64x64 스킨. **AI는 픽셀을 그리지 않는다.**

AI(VLM)는 사진에서 속성 JSON만 뽑고, 64x64 픽셀은 전부 코드가 그린다.
이렇게 나눈 이유는 픽셀 예산 때문이다: 64x64 스킨에서 실제로 칠할 수 있는 픽셀은
3,264개뿐이고, 그중 얼굴 정면은 64개다. 정체성의 87%는 헤어와 의상이 결정한다.
8x12 크기의 옷에 신경망이 만든 이미지를 다운스케일하면 색 얼룩이 되므로
AI의 몫은 분류(무슨 옷인가)와 색 추출로 한정한다.

```
사진 ──VLM──→ 속성 JSON ──→ 코드 렌더러 ──→ 64x64 RGBA
             (분류/색)      (픽셀 100%)      + 불변식 검증
```

## 설치 / 실행

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python -m pytest -q
.venv/bin/python -m skinmaker --model classic   # out/ 에 스킨 + 프리뷰
```

`out/placeholder_<model>.png` 가 스킨, `..._preview.png` 가 QA용 3면도다.
프리뷰 패널 순서: 정면 / 측면 / 후면 / 위 / 오버레이(모자 레이어).

## 확정된 설계

| 항목 | 결정 |
|---|---|
| AI 역할 | 텍스트 시야 API → 속성 JSON만. 픽셀 생성 0개 |
| 얼굴 | 코드 직접 렌더 (눈 2x2, 입 4x1) |
| 손 | 코드 직접 렌더 (팔 하단 3~4행) |
| 헤어 | 단색 10종 × 길이 4단계 enum |
| 겉옷 | AI가 enum + HEX 색 반환, 코드가 8x12에 렌더 |
| 경계 규칙 | 코드가 100% 픽셀을 소유한다. 렌더러가 하나이므로 이음매가 구조적으로 불가능 |
| 모형 | classic(4px 팔) / slim(3px 팔) |

## 64x64 UV 레이아웃

`skinmaker/format.py` 가 단일 진실 소스다. `get_layout()` 이 생성 시 위키 수치와
대조해 틀리면 예외를 던진다.

| 파트 | 레이어 0 영역 | 레이어 1 영역 | 박스 |
|---|---|---|---|
| head | (0,0) 32x16 | (32,0) 32x16 | 8x8x8 |
| body | (16,16) 24x16 | (16,32) 24x16 | 8x12x4 |
| r_arm | (40,16) 16x16 | (40,32) 16x16 | 4x12x4 |
| r_leg | (0,16) 16x16 | (0,32) 16x16 | 4x12x4 |
| l_leg | (16,48) 16x16 | (0,48) 16x16 | 4x12x4 |
| l_arm | (32,48) 16x16 | (48,48) 16x16 | 4x12x4 |

면 순서는 머리/몸통과 팔다리가 다르다 (팔다리는 front→right→back→left→top→bottom).
이 차이를 잘못 그리면 텍스처가 뒤집혀 보이므로 코드로만 처리한다.

**slim 은 앞/뒤 면만 3px 가 되고 깊이(좌우 면)는 4px 그대로다.** 팔다리 박스 폭이
줄어드므로 back 면의 시작 x 도 1px 왼쪽으로 이동한다. 4번째 열은 게임이 무시한다.

## 왼팔/왼다리의 미러 규칙

`canvas.put(part, face, u, v, color)` 의 `u` 는 **텍스처 좌표가 아니라 저자 좌표**다.
`l_arm` / `l_leg` 는 `u` 방향이 우측 파트와 반대이므로 캔버스가 자동으로 뒤집어 쓴다.
같은 팔레트를 양쪽에 같은 코드로 그리면 텍스처상 좌우 대칭이 자동으로 성립한다.

## 불변식 (`validate.py`)

게임에서 스킨이 깨지는 조건을 전부 여기에 고정했다.

| 코드 | 조건 |
|---|---|
| `size` | 정확히 64x64 |
| `mode` | RGBA |
| `overlap` | 서로 다른 파트의 면이 겹치지 않음 |
| `bleed` | 어느 면에도 속하지 않는 픽셀은 완전 투명 |
| `base_alpha` | 내곽 레이어 사용 가능 픽셀은 완전 불투명 (Java 강제) |
| `mirror` | 좌우 파트가 텍스처상 정확히 좌우 반전 |

알파 규칙 주의: **Java 는 외곽 레이어의 부분 투명(1~255)을 허용하고 내곽 레이어만
완전 불투형을 강제한다.** Bedrock 가 0/255 만 허용한다. 참고로 1.8+ 기준
레이어당 사용 가능 픽셀은 classic 1,632 / slim 1,568 이다.

## assets/YuNet 모델

S0 는 OpenCV 내장 YuNet 을 쓴다. 모델 파일은 저장소에 넣지 않는다.

```bash
mkdir -p assets
curl -sSLf -o assets/face_detection_yunet_2023mar.onnx \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
```

다른 경로를 쓰려면 `SKINMAKER_YUNET` 환경변수로 지정한다.

## S0 계측

```bash
.venv/bin/python -m skinmaker.measure path/to/photos
```

거부율, 품질 플래그 분포, 얼굴 크기/밝기/선명도/채도 분포를 뽑는다.
하드 게이트는 "얼굴 검출 실패" 하나뿐이고 나머지 플래그(blur/dark/bright/small/flat)는
거부가 아니라 S1~S3 이 사용할 렌더러 파라미터다.

## assets/YuNet 모델

S0 는 OpenCV 내장 YuNet 을 쓴다. 모델 파일(232KB)은 저장소에 넣지 않는다.

```bash
mkdir -p assets
curl -sSLf -o assets/face_detection_yunet_2023mar.onnx \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
```

다른 경로를 쓰려면 `SKINMAKER_YUNET` 환경변수로 지정한다.

## S0 계측

```bash
.venv/bin/python -m skinmaker.measure path/to/photos
```

거부율, 품질 플래그 분포, 얼굴 크기/밝기/선명도/채도 분포를 뽑는다.
**하드 게이트는 "얼굴 검출 실패" 하나뿐**이고 나머지 플래그(blur/dark/bright/small/flat)는
거부가 아니라 S1~S3 이 참조할 렌더러 파라미터다.

## 단계별 시각 샘플

```bash
.venv/bin/python -m skinmaker.samples <사진파일|폴더> -o out/samples
```

사진 한 장당 contact sheet 한 장이 나온다. 패널은 위에서부터:

| 패널 | 보이는 것 | 이걸로 잡는 오류 |
|---|---|---|
| **S0 input gate** | 원본 + 얼굴 박스 + 헤어/피부/상의 샘플 영역 | 얼굴을 못 찾음 /wrong face, 헤어 영역이 모자를 잡음, 상의 밴드가 배경에 감 |
| **S3 atlas 64x64** | 스킨 텍스처 8배 확대 + 8텍셀 격자 | 어떤 텍셀이 어느 좌표인지 |
| **S3 skin over UV guide** | 스킨을 색으로 코딩된 UV 가이드에 55% 합성 | **内容和 영역이 맞는 rect 에 들어갔는지** (가장 중요) |
| **S4 preview** | 정면/측면/후면/위/오버레이 | 어색한 면, 실루엣 붕괴 |

패널 하단 note 에 검출 점수·품질 지표·영역 크기·플래그가 찍힌다.
note 가 두 줄 넘으면 자동으로 접힌다.

S1~S3 가 아직 없어 스킨 자리는 **PLACEHOLDER** 더미로 채운다. 헤더에 표시되며
실제 결과로 오인하지 않는다. S1~S3 를 추가하면서 `debugview.PANELS` 에 한 줄씩 넣는다.

**이 도구가 실제로 잡은 것들** (S1 코드를 쓰기 전에 설계 결함 3건이 드러남):

1. `hair_region` 이 얼굴 박스 안쪽 상단 1/3 만 잡아 모자 챙을 헤어로 인식
   → 사방 확장(위 35%, 좌우 10%)으로 변경. 긴머리는 얼굴 박스 밖에 있다.
2. `skin_region` 이 눈·입을 포함해 중앙값을 흰자국으로 끌고 감
   → 얼굴 높이의 55~83%(볼·코)로 변경.
3. 후면/측면이 1순위 패널이 아님
   → 정면은 관측된 면이라 평가력이 없다. UV 가이드 패널이 그 역할을 대신함.

## 진행 상태

- [x] 1단계: UV 상수, 캔버스, 불변식 검증, 3면 프리뷰, 더미 스킨
- [x] S0: 입력 판정 (YuNet 검출, 품질 신호, 저하 계획, 계측 CLI)
- [x] 단계별 시각 샘플 (contact sheet, 4개 패널)
- [ ] S1: 관측 추출 (화이트밸런스 + 클러스터 모드)
- [ ] S2: VLM 분류 (스키마 5필드)
- [ ] S3: 파라메트릭 렌더
- [ ] S4: 후보 3개 + 검증

## 주의

- Java Edition 은 스킨 텍스처에 **서명이 필요**해서 minecraft.net 에 업로드해야 실제
  게임에서 보인다. 정품 계정 없이는 `validate.py` 와 프리뷰로만 검증 가능하다.
  Bedrock 은 PNG 를 파일에 복사하는 것만으로 적용되므로 빠른 확인이 목적이라면
  Bedrock 을 쓴다.
- 타인 사진을 넣을 때는 초상권 동의가 필요하다. 이 프로젝트는 로컬 전용 CLI 다.
