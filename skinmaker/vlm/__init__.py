"""VLM 전송 계층. 프롬프트는 attributes 가 만들어 여기에는 오직 전송만 있다.

전송 계층 교체로 비교 실험이 가능해지려면 prompt/schema 는 절대 바꾸지 않는다.
"""
from __future__ import annotations

import inspect
from typing import Any, Protocol, runtime_checkable

from PIL import Image


class TransportError(RuntimeError):
    pass


@runtime_checkable
class Transport(Protocol):
    name: str

    def configured(self) -> tuple[bool, str]:
        """자격증명·설정이 갖춰졌는지. 네트워크를 호출하지 않는다 (health 용)."""

    def available(self) -> tuple[bool, str]:
        """실제로 호출 가능한지, 아니면 왜 안 되는지 (CLI 진단용 — 프로브 가능)."""

    def complete(self, image: Image.Image, prompt: str, schema: dict[str, Any]) -> dict | None:
        """원시 JSON 객체. 파싱 실패는 None."""


def _b64_jpeg(image: Image.Image, quality: int = 88) -> str:
    import base64
    import io

    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("ascii")


_BUILDERS = {
    "mock": (".mock", "MockTransport"),
    "gemini": (".gemini", "GeminiTransport"),
    "ollama": (".ollama", "OllamaTransport"),
    "openrouter": (".openrouter", "OpenRouterTransport"),
}


def get_transport(name: str, **cfg: Any) -> Transport:
    """전송 계층 이름을 받아 인스턴스를 만든다.

    cfg 에 지원하지 않는 키가 섞여 있어도 걸러준다. CLI 는 모든 옵션을
    한꺼번에 넘겨도 되게 해서 전송 계층 교체 시 명령줄이 안 바뀌게 한다.
    """
    key = name.lower()
    if key not in _BUILDERS:
        raise ValueError(f"알 수 없는 전송 계층: {name!r} ({' | '.join(_BUILDERS)})")
    module_name, cls_name = _BUILDERS[key]
    module = __import__(f"skinmaker.vlm{module_name}", fromlist=[cls_name])
    cls = getattr(module, cls_name)
    accepted = set(inspect.signature(cls.__init__).parameters) - {"self"}
    unknown = set(cfg) - accepted
    for dropped in unknown:
        cfg.pop(dropped, None)
    # 오프라인 개발 경로(.env 의 SKINMAKER_TRANSPORT=mock, CLI --transport mock)는
    # 시나리오를 주입할 방법이 없다. 주입이 없을 때만 기본 시나리오를 채운다.
    if key == "mock" and not cfg.get("first"):
        cfg["first"] = module.DEFAULT_SCENARIO
    return cls(**cfg)
