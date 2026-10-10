"""s4 CLI: S2 bbox → S1 crown 배선 (네트워크 없음).

backend/app.py는 classify 결과의 hair_bbox_px를 extract에 전달하는데,
s4.py 생산 경로는 빼먹고 있었다. 이 테스트는 s4 경로의 정수리가
bbox 영역 실측색으로 칠해지는지 고정한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from skinmaker import quality as Q
from skinmaker import s4 as S4
from skinmaker.canvas import rgba, shade
from skinmaker.classify import classify
from skinmaker.colors import extract
from skinmaker.eval import expected_pixel
from skinmaker.render import DEFAULT_HAIR, FACE_SHADE
from skinmaker.vlm.mock import MockTransport

GOOD = {
    "top_garment": "tee",
    "bottom_garment": "shorts",
    "pattern": "plain",
    "sleeve_len": "short",
    "hair_length": "medium",
    # 크롭 하단(몸통 zone)으로 역투영되는 박스. 기본 hair_region(얼굴 위)과
    # 겹치지 않아야 배선 전/후 정수리가 갈린다.
    "hair_bbox": [300, 650, 700, 900],
}


def make_photo():
    img = Image.new("RGB", (400, 500), (30, 30, 30))
    face = Q.FaceBox(150, 100, 100, 130)
    q = Q.Quality(0.9, face.area, 120.0, 400.0, 110.0, True)
    photo = Q.PhotoInput("t.jpg", img, face, q, ())
    # classify가 돌려줄 bbox를 미리 계산해 그 영역만 헤어색으로 채운다.
    # (역투영은 기하만 쓰므로 픽셀과 무관하게 결정적이다.)
    box = classify(photo, MockTransport(first=GOOD)).hair_bbox_px
    assert box is not None
    px = img.load()
    for y in range(box.y, box.y + box.h):
        for x in range(box.x, box.x + box.w):
            px[x, y] = (150, 90, 40)
    # WB 앵커 (skin_region). bbox와 겹쳐 덮였을 수 있으니 마지막에 칠한다.
    for y in range(171, 207):
        for x in range(170, 230):
            px[x, y] = (204, 161, 141)
    return photo, box


def test_s4_passes_hair_bbox_to_extract(tmp_path, monkeypatch):
    photo, _box = make_photo()
    monkeypatch.setattr(S4, "inspect", lambda p: photo)
    monkeypatch.setattr(S4, "get_transport", lambda *a, **k: MockTransport(first=GOOD))

    rc = S4.main(["--photo", "input.jpg", "--transport", "mock",
                  "--out", str(tmp_path), "--single"])
    assert rc == 0
    saved = list(tmp_path.glob("*.png"))
    assert len(saved) == 1

    # 기대 정수리: 같은 사진 + 같은 classify bbox로 extract를 재실행해 구한다.
    # (WB·클러스터 문턱 재조정에도 깨지지 않게 하드코딩 hex를 쓰지 않는다.)
    result = classify(photo, MockTransport(first=GOOD))
    assert result.ok and result.hair_bbox_px is not None
    observed = extract(photo, hair_bbox=result.hair_bbox_px)
    assert observed.hair.confident  # 픽스처 변별력 가드: 미달이면 loudly 실패
    expected = expected_pixel(observed, "hair", "top")

    crown = Image.open(saved[0]).convert("RGBA").getpixel((8, 0))  # head top (0,0)
    default_crown = shade(rgba(DEFAULT_HAIR), FACE_SHADE["top"])
    assert crown != default_crown  # 배선 전에는 기본 헤어색으로 굳는다
    assert crown == expected
