"""Конфигурация LLM-анализа: модели, провайдеры и палитра."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

ProviderId = Literal["openai", "deepseek"]

# Рекомендуемые модели (OpenAI + DeepSeek).
LLM_MODELS: dict[str, str] = {
    # OpenAI
    "gpt-5.5": "флагман, максимум качества (по умолчанию)",
    "gpt-5.4": "рабочая лошадка, баланс цена/качество",
    "gpt-5.4-mini": "быстрее и дешевле",
    "gpt-4.1": "предыдущее поколение, temperature=0",
    "gpt-4.1-mini": "бюджетная",
    "o4-mini": "reasoning, фонетика",
    # DeepSeek (OpenAI-совместимый API, ключ DEEPSEEK_API_KEY)
    "deepseek-v4-pro": "V4 Pro — флагман DeepSeek, thinking, максимум качества",
    "deepseek-v4-flash": "V4 Flash — быстрый и дешёвый, без thinking",
    "deepseek-chat": "legacy: V4 Flash без thinking (до июля 2026)",
    "deepseek-reasoner": "legacy: V4 Flash с thinking (до июля 2026)",
}

DEFAULT_MODEL = "gpt-5.5"

# Провайдер API для каждой модели.
MODEL_PROVIDER: dict[str, ProviderId] = {
    "gpt-5.5": "openai",
    "gpt-5.4": "openai",
    "gpt-5.4-mini": "openai",
    "gpt-4.1": "openai",
    "gpt-4.1-mini": "openai",
    "o4-mini": "openai",
    "deepseek-v4-pro": "deepseek",
    "deepseek-v4-flash": "deepseek",
    "deepseek-chat": "deepseek",
    "deepseek-reasoner": "deepseek",
}

PROVIDER_LABELS: dict[ProviderId, str] = {
    "openai": "OpenAI",
    "deepseek": "DeepSeek",
}

PROVIDER_ENV_KEYS: dict[ProviderId, str] = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}

DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# Сколько блоков одновременно слать в LLM (лимит rate limit).
DEFAULT_MAX_PARALLEL_BLOCKS = 5

PALETTE = ("purple", "green", "blue", "orange", "pink")


@dataclass(frozen=True)
class ModelPricing:
    """Тариф за 1M токенов (USD). Ориентир для калькулятора в UI."""

    input_per_1m_usd: float
    output_per_1m_usd: float


# Оценочные тарифы — обновляйте по pricing-страницам провайдеров.
MODEL_PRICING_USD: dict[str, ModelPricing] = {
    # OpenAI — https://openai.com/api/pricing/
    "gpt-5.5": ModelPricing(2.50, 10.00),
    "gpt-5.4": ModelPricing(2.00, 8.00),
    "gpt-5.4-mini": ModelPricing(0.60, 2.40),
    "gpt-4.1": ModelPricing(2.00, 8.00),
    "gpt-4.1-mini": ModelPricing(0.40, 1.60),
    "o4-mini": ModelPricing(1.10, 4.40),
    # DeepSeek V4 — https://api-docs.deepseek.com/quick_start/pricing
    "deepseek-v4-pro": ModelPricing(0.435, 0.87),
    "deepseek-v4-flash": ModelPricing(0.14, 0.28),
    "deepseek-chat": ModelPricing(0.14, 0.28),
    "deepseek-reasoner": ModelPricing(0.14, 0.55),
}


def model_provider(model: str) -> ProviderId:
    """Провайдер API для модели."""
    return MODEL_PROVIDER.get(model, "openai")


def provider_label(provider: ProviderId) -> str:
    return PROVIDER_LABELS.get(provider, provider)


def _raw_env_key(provider: ProviderId) -> str:
    return (os.environ.get(PROVIDER_ENV_KEYS[provider]) or "").strip()


def is_provider_configured(provider: ProviderId) -> bool:
    """Есть ли непустой ключ провайдера в окружении."""
    key = _raw_env_key(provider)
    if not key:
        return False
    bad = {"sk-...", "sk-…", "your-api-key", "changeme"}
    if key in bad or key.endswith("..."):
        return False
    return key.startswith("sk-")


def is_model_available(model: str) -> bool:
    """Модель можно вызвать: для её провайдера задан API-ключ."""
    if model not in LLM_MODELS:
        return False
    return is_provider_configured(model_provider(model))


def available_models() -> dict[str, str]:
    """Модели, для которых настроен ключ провайдера."""
    return {name: desc for name, desc in LLM_MODELS.items() if is_model_available(name)}


def effective_default_model() -> str:
    """Модель по умолчанию, если для неё есть ключ; иначе первая доступная."""
    if is_model_available(DEFAULT_MODEL):
        return DEFAULT_MODEL
    for name in LLM_MODELS:
        if is_model_available(name):
            return name
    return DEFAULT_MODEL


def models_help() -> str:
    lines = [f"  {name:20} — {desc}" for name, desc in LLM_MODELS.items()]
    return "Рекомендуемые модели:\n" + "\n".join(lines)
