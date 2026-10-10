"""테스트·오프라인용 가짜 전송 계층.

kwargs 로 시나리오를 주입한다. 프로덕션 경로가 아니다.
"""
from __future__ import annotations

from typing import Any

from PIL import Image


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

    def available(self) -> tuple[bool, str]:
        if self.fail:
            return False, self.error or "mock 실패 모드"
        return True, "mock (오프라인)"

    def complete(self, image: Image.Image, prompt: str, schema: dict[str, Any]) -> dict | None:
        self.calls.append({"prompt": prompt, "schema": schema, "size": image.size})
        if self.fail:
            self.last_error = self.error or "mock 실패 모드"
            return None
        payload = self.first if len(self.calls) == 1 else self.second
        if payload is None:
            payload = self.first
        return dict(payload) if payload else None
