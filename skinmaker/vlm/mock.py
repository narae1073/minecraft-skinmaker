"""테스트·오프라인용 가짜 전송 계층.

kwargs 로 시나리오를 주입한다. 프로덕션 경로가 아니다.

`DEFAULT_SCENARIO` 는 시나리오를 주입할 수 없는 경로 — `.env` 의
`SKINMAKER_TRANSPORT=mock`(backend/app.py)와 `--transport mock`(CLI) — 에서
`get_transport()` 가 채운다. 주입 경로(MockTransport(first=...))는 그대로 둔다.
"""
from __future__ import annotations

from typing import Any

from PIL import Image

# validate() 를 통과하는 최소 필드. 값은 흔한 캐주얼 복장이라 UI 미리보기가
# 자연스럽다. 14필드를 모두 채운다 — 빠진 필드는 missing 으로 판정되어
# 불확실성 플래그가 생기기 때문이다 (mock 실행이 거짓 경고를 만들지 않게).
DEFAULT_SCENARIO: dict[str, Any] = {
    "top_garment": "tee",
    "bottom_garment": "shorts",
    "pattern": "plain",
    "sleeve_len": "short",
    "hair_length": "medium",
    "hair_style": "bob",
    "hood": "none",
    "beard": "none",
    "inner_top": "none",
    "neckwear": "none",
    "closure_type": "buttons",
    "collar_type": "crew",
    "pocket_type": "none",
    "symmetry": "symmetric",
    "hair_bbox": [200, 50, 800, 600],
}


class MockTransport:
    name = "mock"

    def __init__(
        self,
        first: dict | None = None,
        second: dict | None = None,
        fail: bool = False,
        error: str | None = None,
    ):
        self.first = first
        self.second = second
        self.fail = fail
        self.error = error
        self.calls: list[dict] = []
        self.last_error: str | None = None

    def configured(self) -> tuple[bool, str]:
        if self.fail:
            return False, self.error or "mock 실패 모드"
        return True, "mock (오프라인)"

    def available(self) -> tuple[bool, str]:
        return self.configured()

    def complete(self, image: Image.Image, prompt: str, schema: dict[str, Any]) -> dict | None:
        self.calls.append({"prompt": prompt, "schema": schema, "size": image.size})
        if self.fail:
            self.last_error = self.error or "mock 실패 모드"
            return None
        payload = self.first if len(self.calls) == 1 else self.second
        if payload is None:
            payload = self.first
        return dict(payload) if payload else None
