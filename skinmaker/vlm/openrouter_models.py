"""OpenRouter 무료 모델 목록 (2026-10-10 API 기준).

무료 (prompt $0) 이며 멀티모달/코딩/추론 능력으로 추려낸 모델들을 우선순위순
목록으로 담는다. 실제 호출은 vlm.openrouter 에서 이 목록을 순차적으로 훑어
최초 성공 모델을 쓴다.

순서 변경: OPENROUTER_DEFAULT_MODELS=모델1,모델2,...
(예: OPENROUTER_DEFAULT_MODELS="google/gemma-4-31b-it:free,apodex/apodex-1.1-mini:free")
"""
from __future__ import annotations

# 우선순위순 (멀티모달 코딩 · 추론 능력을 고려).
# 실패 시 다음 모델로 넘어가므로 실제 비용은 0 에 수렴한다.
DEFAULT_MODELS = (
    # 1 순위: 현재 환경에서 검증된 멀티모달, 컨텍스트 262k
    "apodex/apodex-1.1-mini:free",
    # Google Gemma 4 (멀티모달)
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    # NVIDIA Nemotron (코딩 · 멀티모달 · 추론)
    "nvidia/nemotron-3.5-lightning:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    # Poolside Laguna (멀티모달)
    "poolside/laguna-s-2.1:free",
    "poolside/laguna-xs-2.1:free",
    # 코딩 특화
    "cohere/north-mini-code:free",
    # 나머지 무료 (순서 민감도 낮음)
    "inclusionai/ling-3.1-flash",
    "thinkingmachines/inkling:free",
    "thinkingmachines/inkling-small:free",
    "dots-studio/dots-3-note-preview:free",
    "liquid/lfm-2.5-2.6b:free",
    "openrouter/free",  # OpenRouter 자체 라우터 (최후의 수단)
)
