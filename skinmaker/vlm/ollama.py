"""Ollama 전송 계층. 집 Windows 의 2070 Super 용.

주의: Ollama 는 `format` 으로 enum 을 강제하므로 "coerce 발생" 신호가 사라진다.
불확실성은 순서 교환 이중 질의의 일치 여부로만 판정한다.
"""
from __future__ import annotations

import os
from typing import Any

import requests
from PIL import Image

from ..attributes import parse_json_object
from . import TransportError, _b64_jpeg

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5vl:3b"


class OllamaTransport:
    name = "ollama"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: str | None = None,
        timeout: float = 120.0,
        session: Any = None,
        keep_alive: str = "30m",
        use_format: bool = True,
    ):
        self.model = model or DEFAULT_MODEL
        self.host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
        self.timeout = timeout
        self.use_format = use_format
        self.keep_alive = keep_alive
        self.session = session or requests
        self.last_error: str | None = None

    def configured(self) -> tuple[bool, str]:
        # 호스트 설정만 확인한다 — 모델 서버 도달 여부는 available() 프로브의 몫.
        return True, f"{self.model} @ {self.host} (연결 미확인)"

    def available(self) -> tuple[bool, str]:
        try:
            resp = self.session.get(f"{self.host}/api/tags", timeout=3)
        except Exception as exc:
            return False, f"{self.host} 연결 실패: {type(exc).__name__}"
        if resp.status_code >= 400:
            return False, f"HTTP {resp.status_code}"
        names = [str(m.get("name") or "") for m in (resp.json().get("models") or [])]
        vision = [n for n in names if n]
        wanted = self.model.split(":")[0]
        have = [n for n in vision if n.split(":")[0] == wanted]
        if vision and not have:
            return False, f"{self.model} 미설치. 설치: ollama pull {self.model}  (있음: {', '.join(vision)})"
        return True, f"{self.model} @ {self.host}  (설치됨: {', '.join(vision) or '없음'})"

    def complete(self, image: Image.Image, prompt: str, schema: dict[str, Any]) -> dict | None:
        body: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"temperature": 0, "seed": 0, "top_p": 1.0},
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [_b64_jpeg(image)],
                }
            ],
        }
        if self.use_format:
            body["format"] = schema
        try:
            resp = self.session.post(f"{self.host}/api/chat", json=body, timeout=self.timeout)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None
        if resp.status_code >= 400:
            self.last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
            return None
        try:
            payload = resp.json()
        except ValueError:
            self.last_error = "JSON 아님"
            return None
        if payload.get("error"):
            self.last_error = str(payload["error"])[:300]
            return None
        return parse_json_object((payload.get("message") or {}).get("content"))
