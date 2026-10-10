"""OpenRouter 전송 계층. 여러 무료 모델을 순차적으로 시도하는 폴백 체인이 특징.

     python -m skinmaker.s2 --transport openrouter --photo a.jpg
     OPENROUTER_DEFAULT_MODELS="gem-31b,apodex" \
         python -m skinmaker.s2 --transport openrouter --photo a.jpg
"""
from __future__ import annotations

import os
from typing import Any

import requests
from PIL import Image

from ..attributes import parse_json_object
from ..vlm.openrouter_models import DEFAULT_MODELS
from . import TransportError, _b64_jpeg

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
API_KEY_ENV = "OPENROUTER_API_KEY"
HTTP_REFERER_ENV = "OPENROUTER_HTTP_REFERER"
X_TITLE_ENV = "OPENROUTER_X_TITLE"


def _load_default_models() -> tuple[str, ...]:
    raw = os.environ.get("OPENROUTER_DEFAULT_MODELS")
    if raw:
        return tuple(m.strip() for m in raw.split(",") if m.strip())
    return DEFAULT_MODELS


class OpenRouterTransport:
    """모델 순서를 바꿔가며 무료 모델들을 모두 시도한다."""

    name = "openrouter"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        host: str | None = None,
        timeout: float = 120.0,
        use_schema: bool = True,
    ):
        self.model = model or DEFAULT_MODELS[0]
        self.api_key = api_key or os.environ.get(API_KEY_ENV)
        self.host = host or ENDPOINT
        self.timeout = timeout
        self.use_schema = use_schema
        self._models = _load_default_models()
        if model and "," in model:
            self._models = tuple(m.strip() for m in model.split(",") if m.strip())
        elif model and self.model not in self._models:
            self._models = (self.model, *self._models)
        self.session = requests.Session()
        self.last_error: str | None = None
        self.last_model: str | None = None

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, f"API 키 없음 ({API_KEY_ENV})"
        try:
            resp = self.session.get(
                self.host.replace("/chat/completions", "/models"),
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5,
            )
        except Exception as exc:
            return False, f"프로브 실패: {type(exc).__name__}"
        if resp.status_code >= 400:
            return False, f"API 키 확인 실패 (HTTP {resp.status_code})"
        return True, f"{self.model} (키 있음, 폴백 {len(self._models)}개)"

    def complete(self, image: Image.Image, prompt: str, schema: dict[str, Any]) -> dict | None:
        if image is None:
            return None
        if not self.api_key:
            raise TransportError("OpenRouter API 키가 없다")

        parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        try:
            parts.append(
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64_jpeg(image)}"}}
            )
        except Exception as exc:  # base64 변환 실패는 절대 넘어가지 않게
            self.last_error = f"이미지 인코딩 실패: {exc}"
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        headers["HTTP-Referer"] = os.environ.get(HTTP_REFERER_ENV, "https://github.com/obra/skinmaker")
        headers["X-Title"] = os.environ.get(X_TITLE_ENV, "skinmaker")

        body: dict[str, Any] = {
            "model": "",
            "messages": [{"role": "user", "content": parts}],
            "temperature": 0,
        }
        if self.use_schema:
            body["response_format"] = {"type": "json_object"}

        errors: list[tuple[str, str]] = []
        for cand in self._models:
            body["model"] = cand
            try:
                resp = self.session.post(self.host, headers=headers, json=body, timeout=self.timeout)
            except Exception as exc:
                errors.append((cand, f"{type(exc).__name__}: {exc}"))
                continue
            if resp.status_code >= 400:
                errors.append((cand, f"HTTP {resp.status_code}: {resp.text[:200]}"))
                continue
            try:
                payload = resp.json()
            except ValueError:
                errors.append((cand, "JSON 아님"))
                continue
            if payload.get("error"):
                errors.append((cand, str(payload["error"])[:200]))
                continue
            choices = payload.get("choices") or []
            if not choices:
                errors.append((cand, "후보 없음"))
                continue
            message = choices[0].get("message") or {}
            text = message.get("content") or ""
            result = parse_json_object(text)
            if isinstance(result, dict):
                self.last_model = cand
                self.last_error = None
                return result
            errors.append((cand, "출력 중 JSON 객체 아님"))
            continue

        self.last_error = "; ".join(f"{m}: {e}" for m, e in errors[:5])
        return None
