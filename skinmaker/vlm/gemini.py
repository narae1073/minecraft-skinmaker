"""Gemini 전송 계층. Google Generative Language API 를 직접 호출한다.

SDK 의존성을 피하려고 requests + JSON 만 쓴다. 모델 교체는 config 문자열로.
"""
from __future__ import annotations

import os
from typing import Any

import requests
from PIL import Image

from ..attributes import parse_json_object
from . import TransportError, _b64_jpeg

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
API_KEY_ENV = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
DEFAULT_MODEL = "gemini-3.1-flash-lite"

GEMINI_TYPES = {
    "object": "OBJECT",
    "string": "STRING",
    "integer": "INTEGER",
    "array": "ARRAY",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
}


def _gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """표준 JSON Schema → Gemini responseSchema (OpenAPI 부분집합, 대문자 타입).

    Ollama 는 소문자를 받으므로 두 전송 계층의 方言 이 다르다.
    정본은 attributes.build_schema() 하나뿐이다.
    """
    declared = str(schema.get("type", "object")).lower()
    if declared not in GEMINI_TYPES:
        raise ValueError(f"Gemini 로 변환할 수 없는 스키마 타입: {declared}")
    out: dict[str, Any] = {"type": GEMINI_TYPES[declared]}
    if "enum" in schema:
        out["enum"] = list(schema["enum"])
    if "items" in schema:
        out["items"] = _gemini_schema(schema["items"])
    if "properties" in schema:
        out["properties"] = {k: _gemini_schema(v) for k, v in schema["properties"].items()}
    if "required" in schema:
        out["required"] = list(schema["required"])
    return out


class GeminiTransport:
    name = "gemini"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        timeout: float = 30.0,
        session: Any = None,
        use_schema: bool = True,
    ):
        self.model = model or DEFAULT_MODEL
        self.api_key = api_key or next((os.environ.get(k) for k in API_KEY_ENV if os.environ.get(k)), None)
        self.timeout = timeout
        self.use_schema = use_schema
        self.session = session or requests
        self.last_error: str | None = None

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, f"API 키 없음 ({' 또는 '.join(API_KEY_ENV)})"
        return True, f"{self.model} (키 있음)"

    def complete(self, image: Image.Image, prompt: str, schema: dict[str, Any]) -> dict | None:
        if not self.api_key:
            raise TransportError("Gemini API 키가 없다")
        config: dict[str, Any] = {
            "temperature": 0,
            "responseMimeType": "application/json",
            "seed": 0,
        }
        if self.use_schema:
            config["responseSchema"] = _gemini_schema(schema)
        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": _b64_jpeg(image)}},
                    ],
                }
            ],
            "generationConfig": config,
        }
        url = ENDPOINT.format(model=self.model)
        try:
            resp = self.session.post(
                url,
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                json=body,
                timeout=self.timeout,
            )
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
        if "error" in payload:
            self.last_error = str(payload["error"])[:300]
            return None
        return self._extract(payload)

    def _extract(self, payload: dict) -> dict | None:
        candidates = payload.get("candidates") or []
        if not candidates:
            self.last_error = f"후보 없음: {str(payload)[:200]}"
            return None
        parts = (candidates[0].get("content") or {}).get("parts") or []
        texts = [p.get("text", "") for p in parts if "text" in p]
        return parse_json_object("".join(texts))
