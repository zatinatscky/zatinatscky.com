"""Оценка стоимости LLM-анализа до запуска (приблизительно, в USD)."""

from __future__ import annotations

from dataclasses import dataclass

from .block_limits import count_lines, count_words
from .from_blocks import BlockSubmission
from .llm.config import MODEL_PRICING_USD, ModelPricing, model_provider, provider_label
from .llm.schema import SYSTEM_PROMPT

# Фиксированные накладные расходы на один запрос к API.
_SYSTEM_PROMPT_TOKENS = max(400, len(SYSTEM_PROMPT) // 3)
_SCHEMA_OVERHEAD_TOKENS = 450  # json_schema + служебные поля ответа
_USER_PROMPT_OVERHEAD = 140  # заголовки блока, подсказки skip-line
_RETRY_MARGIN = 1.12  # запас на 1–2 повтора валидации (~12%)

# Символов на 1 токен (грубо; кириллица плотнее латиницы).
_CHARS_PER_TOKEN = {"ru": 2.3, "en": 3.8, "es": 3.8}


@dataclass(frozen=True)
class BlockTokenEstimate:
    """Оценка токенов одного блока."""

    lines: int
    words: int
    chars: int
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class CostEstimate:
    """Итог оценки для API и UI."""

    model: str
    api_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    cost_usd_label: str
    input_cost_usd: float
    output_cost_usd: float
    pricing_input_per_1m: float
    pricing_output_per_1m: float
    blocks: list[BlockTokenEstimate]
    breakdown: list[dict[str, str]]


def _chars_to_tokens(chars: int, lang: str) -> int:
    div = _CHARS_PER_TOKEN.get(lang, 3.5)
    return max(0, int(chars / div))


def _estimate_block_tokens(text: str, lang: str, *, model: str) -> BlockTokenEstimate:
    """Один блок ≈ один вызов chat.completions с текстом + IPA в промпте."""
    lines_n = count_lines(text)
    words_n = count_words(text)
    chars_n = len(text)

    # Текст строк + номера + дублирующая строка IPA на каждую строку.
    text_tokens = _chars_to_tokens(chars_n, lang)
    ipa_tokens = int(text_tokens * 1.35)
    line_overhead = lines_n * 12

    input_tokens = (
        _SYSTEM_PROMPT_TOKENS
        + _SCHEMA_OVERHEAD_TOKENS
        + _USER_PROMPT_OVERHEAD
        + text_tokens
        + ipa_tokens
        + line_overhead
    )

    # JSON-цепочки: база + ~90 токенов на строку песни.
    output_tokens = 220 + lines_n * 95 + max(0, words_n // 8) * 25

    # Reasoning-модели (DeepSeek Pro/reasoner, o-серия) пишут больше на выходе.
    ml = model.lower()
    if "reasoner" in ml or ml == "deepseek-v4-pro" or model.lower().startswith("o"):
        output_tokens = int(output_tokens * 1.75)

    return BlockTokenEstimate(
        lines=lines_n,
        words=words_n,
        chars=chars_n,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _pricing_for(model: str) -> ModelPricing:
    return MODEL_PRICING_USD.get(model, MODEL_PRICING_USD["gpt-4.1"])


def _usd(amount: float) -> str:
    """Короткая подпись для кнопки."""
    if amount < 0.01:
        return "~<$0.01"
    if amount < 1:
        return f"~${amount:.2f}"
    return f"~${amount:.2f}"


def estimate_analysis_cost(
    blocks: list[BlockSubmission],
    *,
    model: str,
    lang: str = "ru",
) -> CostEstimate:
    """Считает примерную стоимость всех LLM-запросов по блокам."""
    filled = [b for b in blocks if b.text.strip()]
    pricing = _pricing_for(model)

    per_block = [_estimate_block_tokens(b.text, lang, model=model) for b in filled]
    api_calls = len(per_block)

    input_tokens = sum(b.input_tokens for b in per_block)
    output_tokens = sum(b.output_tokens for b in per_block)

    input_cost = input_tokens / 1_000_000 * pricing.input_per_1m_usd
    output_cost = output_tokens / 1_000_000 * pricing.output_per_1m_usd
    subtotal = input_cost + output_cost
    total = subtotal * _RETRY_MARGIN

    total_lines = sum(b.lines for b in per_block)
    total_words = sum(b.words for b in per_block)

    prov = provider_label(model_provider(model))
    billing = "DeepSeek" if prov == "DeepSeek" else "OpenAI"

    breakdown = [
        {
            "title": f"Запросы к {prov}",
            "detail": (
                f"{api_calls} блок(ов) текста = {api_calls} вызов(ов) API. "
                "Параллельная обработка ускоряет работу, но не умножает стоимость."
            ),
        },
        {
            "title": "Объём текста",
            "detail": (
                f"≈ {total_lines} строк, {total_words} слов → "
                f"~{input_tokens:,} входных токенов (текст + IPA-транскрипция в промпте)."
            ),
        },
        {
            "title": "Ответ модели",
            "detail": (
                f"JSON с цепочками рифм: оценка ~{output_tokens:,} выходных токенов "
                f"(зависит от числа найденных рифм)."
            ),
        },
        {
            "title": f"Тариф модели «{model}»",
            "detail": (
                f"${pricing.input_per_1m_usd:.2f} за 1M входных токенов, "
                f"${pricing.output_per_1m_usd:.2f} за 1M выходных. "
                f"Вход: ~${_fmt(input_cost)}, выход: ~${_fmt(output_cost)}."
            ),
        },
        {
            "title": "Повторы и погрешность",
            "detail": (
                "К сумме добавлен запас ~12% на автоматические повторы, если модель "
                f"ошибается в разметке. Фактический счёт {billing} может отличаться на 10–30%."
            ),
        },
    ]

    return CostEstimate(
        model=model,
        api_calls=api_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        cost_usd=round(total, 4),
        cost_usd_label=_usd(total),
        input_cost_usd=round(input_cost, 4),
        output_cost_usd=round(output_cost, 4),
        pricing_input_per_1m=pricing.input_per_1m_usd,
        pricing_output_per_1m=pricing.output_per_1m_usd,
        blocks=per_block,
        breakdown=breakdown,
    )


def _fmt(n: float) -> str:
    return f"{n:.3f}" if n < 0.1 else f"{n:.2f}"


def estimate_dual_analysis_cost(
    blocks: list[BlockSubmission],
    *,
    model_primary: str,
    model_secondary: str,
    lang: str = "ru",
) -> CostEstimate:
    """Сумма оценок двух моделей (два полных прогона)."""
    est_a = estimate_analysis_cost(blocks, model=model_primary, lang=lang)
    est_b = estimate_analysis_cost(blocks, model=model_secondary, lang=lang)
    total = est_a.cost_usd + est_b.cost_usd
    label = f"{model_primary} + {model_secondary}"

    breakdown = [
        {
            "title": "Режим двух моделей",
            "detail": (
                f"Два полных прогона: «{model_primary}» и «{model_secondary}». "
                f"Цепочки рифм объединяются (union), дубликаты по units сливаются."
            ),
        },
        {
            "title": f"Модель 1 «{model_primary}»",
            "detail": (
                f"~{est_a.cost_usd_label} · {est_a.api_calls} запрос(ов) · "
                f"{est_a.total_tokens:,} токенов."
            ),
        },
        {
            "title": f"Модель 2 «{model_secondary}»",
            "detail": (
                f"~{est_b.cost_usd_label} · {est_b.api_calls} запрос(ов) · "
                f"{est_b.total_tokens:,} токенов."
            ),
        },
        {
            "title": "Итого",
            "detail": (
                f"Суммарно ~{_usd(total)} · {est_a.api_calls + est_b.api_calls} запросов · "
                f"{est_a.total_tokens + est_b.total_tokens:,} токенов."
            ),
        },
    ]

    return CostEstimate(
        model=label,
        api_calls=est_a.api_calls + est_b.api_calls,
        input_tokens=est_a.input_tokens + est_b.input_tokens,
        output_tokens=est_a.output_tokens + est_b.output_tokens,
        total_tokens=est_a.total_tokens + est_b.total_tokens,
        cost_usd=round(total, 4),
        cost_usd_label=_usd(total),
        input_cost_usd=round(est_a.input_cost_usd + est_b.input_cost_usd, 4),
        output_cost_usd=round(est_a.output_cost_usd + est_b.output_cost_usd, 4),
        pricing_input_per_1m=est_a.pricing_input_per_1m,
        pricing_output_per_1m=est_b.pricing_output_per_1m,
        blocks=est_a.blocks + est_b.blocks,
        breakdown=breakdown,
    )
