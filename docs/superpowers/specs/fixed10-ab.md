# fixed10 A-B: base(5b51a3a) vs head(808644e + fix wave) — 수치만, 개선 주장 없음

- 방법: base는 `/tmp/skinmaker-base` worktree(5b51a3a, Task 1~4 전)에,
  head는 본 브랜치에, 같은 스크립트(`/tmp/ab_fixed10.py`)로
  `inspect → extract(photo)`(plain, bbox 없음) `→ evaluate` 실행.
  같은 사진(`out/s0_photos`), 같은 YuNet 모델, 같은 venv.
- base를 체크아웃하지 않았음 (worktree 분리. plan Task-5 Step 6의 `git stash` 대신).
- head 측정 시점의 코드는 fix wave 포함이나, extract 측정값에는 영향 없음
  (fix wave는 s4 배선 1줄·eval 리포트 밴드·help 문구·skip 가드·docstring 뿐).
  실제로 아래 head 열은 task-5-report §A의 post 열과 전부 일치한다.
- headline counts는 동일할 것으로 예상됨: Task 1은 값 교정(확신율 아님),
  Task 3 bbox 경로는 plain 실행에 안 나타남, Task 4는 값 이동(확신율 아님),
  거절은 손대지 않은 `quality.inspect`에서 옴.

## headline counts (10장)

| metric | base (5b51a3a) | head |
|---|---|---|
| evaluated / rejected | 10 / 0 | 10 / 0 |
| valid (validate_image) | 10/10 | 10/10 |
| hair fallback | 9/10 | 9/10 |
| bottom/skin/top fallback | 0 | 0 |

## per-photo hex table (skin / hair / top / bottom. M=missing, U=unconfident)

| photo | base | head |
|---|---|---|
| images31.jpeg | `#03505d` / `#021e22` / `#03161a` / `#030c0e` | `#02515d` / `#021e22` / `#03161a` / `#030c0e` |
| images10.jpeg | `#8e7065` / `#000000MU` / `#b9b49c` / `#caf8ee` | `#907266` / `#000000MU` / `#cbf8ef` / `#caf8ef` |
| istockphoto-1660422184-612x612.jpg | `#e6b8a2` / `#000000MU` / `#faf8f9` / `#f9f7f9` | `#e9baa2` / `#000000MU` / `#fcf8f7` / `#fbf7f7` |
| full-body-portrait-...-307892842.webp | `#dcb39d` / `#000000MU` / `#31394a` / `#2f3748` | `#e0b49e` / `#000000MU` / `#323949` / `#303747` |
| asian-man-casual-full-body-260nw-111554696.webp | `#c49e89` / `#000000MU` / `#c9dde7` / `#c7dde7` | `#c49f8a` / `#000000MU` / `#c8dde6` / `#c6dde6` |
| images4.jpeg | `#c89f8b` / `#000000MU` / `#deb1bb` / `#dfb0b8` | `#cb9f8c` / `#000000MU` / `#e0b1bb` / `#e1b0b8` |
| images12.jpeg | `#ddb09b` / `#000000MU` / `#f0df8a` / `#c8b43c` | `#deb099` / `#ac7355-U` / `#f2df8b` / `#cbb53e` |
| istockphoto-1372309567-612x612.jpg | `#6f4e3d` / `#503426-U` / `#9a6223` / `#9a6223`(==top) | `#6e4d3d` / `#503426-U` / `#9a6223` / `#6e3b0b` |
| 1000_F_247111204_ronTlofPxQGLlIijbhhnJUBbJ2bDfQ8N.jpg | `#967769` / `#af7e4a-U` / `#101111` / `#101111` | `#99796b` / `#b07e48-U` / `#101111` / `#101111` |
| ex6(half).png | `#ffdbc5` / `#2f2826-U` / `#f4e5e4` / `#f4e5e3` | `#ffdbc1` / `#2f2825-U` / `#f7e5e0` / `#f7e5df` |

## flipped 3 (값이 뒤집힌 사진. contact sheet는 `out/contact-fixed10/`)

- images10.jpeg — top flip (`#b9b49c`→`#cbf8ef`)
- istockphoto-1372309567-612x612.jpg — bottom flip (`#9a6223`(==top)→`#6e3b0b`)
- images12.jpeg — hair newly measured (`#000000MU`→`#ac7355-U`)

값의 정답 여부는 contact sheet 후면/UV 패널로 사람이 판정한다 (여기서 주장하지 않음).
