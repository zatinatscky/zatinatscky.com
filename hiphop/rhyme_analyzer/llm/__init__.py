"""LLM-слой: анализ рифм через OpenAI (сервисная структура).

Публичный API:
  RhymeLlmService — оркестратор (блоки параллельно, IPA из espeak в промпт).
"""

from .service import RhymeLlmService
from .config import (
    DEFAULT_MAX_PARALLEL_BLOCKS,
    DEFAULT_MODEL,
    LLM_MODELS,
    effective_default_model,
    is_model_available,
    model_provider,
    models_help,
)

__all__ = [
    "RhymeLlmService",
    "DEFAULT_MODEL",
    "DEFAULT_MAX_PARALLEL_BLOCKS",
    "LLM_MODELS",
    "effective_default_model",
    "is_model_available",
    "model_provider",
    "models_help",
]
