"""Фасад LLM-анализа (обратная совместимость CLI).

Реализация перенесена в rhyme_analyzer.llm (сервисная структура).
"""

from __future__ import annotations

import json
from pathlib import Path

from .llm import DEFAULT_MODEL, LLM_MODELS, RhymeLlmService, models_help
from .models import Block
from .progress import ProgressReporter
from .spec_validate import require_valid, validate_spec
from .llm.merge import merge_specs

__all__ = [
    "DEFAULT_MODEL",
    "LLM_MODELS",
    "RhymeLlmService",
    "analyze_with_openai",
    "analyze_dual_models",
    "blocks_to_numbered_text",
    "load_spec",
    "models_help",
    "save_spec",
]


def blocks_to_numbered_text(blocks: list[Block]) -> str:
    """Устаревший хелпер; для промптов используйте llm.prompt.block_to_prompt_text."""
    from .llm.prompt import block_to_prompt_text

    return "\n\n".join(block_to_prompt_text(b) for b in blocks)


def analyze_with_openai(
    blocks: list[Block],
    *,
    lang: str = "ru",
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    max_retries: int = 2,
    max_parallel: int | None = None,
    title: str = "Фонетический разбор рифм",
    reporter: ProgressReporter | None = None,
) -> dict:
    """Анализ через RhymeLlmService (блоки параллельно, IPA в промпте).

    blocks должны быть уже нормализованы и транскрибированы (IPA заполнен).
    """
    return RhymeLlmService(
        model=model,
        api_key=api_key,
        max_retries=max_retries,
        max_parallel=max_parallel,
        reporter=reporter,
    ).analyze(blocks, lang=lang, title=title)


def analyze_dual_models(
    blocks: list[Block],
    *,
    model_primary: str,
    model_secondary: str,
    lang: str = "ru",
    api_key: str | None = None,
    max_retries: int = 3,
    max_parallel: int | None = None,
    title: str = "Фонетический разбор рифм",
    reporter: ProgressReporter | None = None,
) -> tuple[dict, dict]:
    """Два прогона LLM → union цепочек (дедуп по units).

    Возвращает (merged_spec, dual_stats).
    """
    rep = reporter or ProgressReporter()
    rep.log_llm(
        f"[llm] режим двух моделей: {model_primary} + {model_secondary}"
    )

    spec_a = RhymeLlmService(
        model=model_primary,
        api_key=api_key,
        max_retries=max_retries,
        max_parallel=max_parallel,
        reporter=rep,
        llm_base_percent=15,
        llm_span_percent=32,
    ).analyze(blocks, lang=lang, title=title)

    rep.log_llm(f"[llm] {model_primary}: {len(spec_a.get('chains', []))} цепочек")

    spec_b = RhymeLlmService(
        model=model_secondary,
        api_key=api_key,
        max_retries=max_retries,
        max_parallel=max_parallel,
        reporter=rep,
        llm_base_percent=48,
        llm_span_percent=37,
    ).analyze(blocks, lang=lang, title=title)

    rep.log_llm(f"[llm] {model_secondary}: {len(spec_b.get('chains', []))} цепочек")

    merged, stats = merge_specs(spec_a, spec_b, title=title)
    errors = validate_spec(blocks, merged)
    if errors:
        require_valid(blocks, merged)

    rep.log_llm(
        f"[llm] объединение: {stats['chains_merged']} цепочек "
        f"(+{stats['chains_union_added']} уникальных от {model_secondary})"
    )

    dual_meta = {
        "model_primary": model_primary,
        "model_secondary": model_secondary,
        **stats,
    }
    return merged, dual_meta


def save_spec(spec: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_spec(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
