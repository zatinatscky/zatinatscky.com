"""Сборка промптов: текст + IPA (из espeak, не от модели)."""

from __future__ import annotations

from ..models import Block, Line
from ..skip_line import skip_line_hints

_LANG_LABELS = {"ru": "русский", "en": "английский", "es": "испанский"}


def _line_text(line: Line) -> str:
    """Оригинальный текст строки."""
    return "".join(t.display for t in line.tokens)


def _line_ipa(line: Line) -> str:
    """IPA-строка: слова — ipa из G2P, разделители — как в тексте."""
    parts: list[str] = []
    for tok in line.tokens:
        if tok.is_word:
            # Если IPA ещё не посчитан — fallback на display (не должно случаться в --llm).
            parts.append(tok.ipa if tok.ipa else tok.display)
        else:
            parts.append(tok.display)
    return "".join(parts)


# Подписи типов секций для промпта LLM (EN / RU / ES).
_SECTION_KIND_LABELS = {
    "verse": "куплет (verse)",
    "chorus": "припев (chorus / refrain)",
    "hook": "hook",
    "bridge": "бридж (bridge)",
    "intro": "интро (intro)",
    "outro": "аутро (outro)",
    "other": "секция",
}


def block_to_prompt_text(block: Block) -> str:
    """Формат блока для LLM: заголовок + тип секции + пары строк текст/IPA."""
    kind_label = _SECTION_KIND_LABELS.get(block.section_kind, block.section_kind)
    parts = [f"## {block.title} ({kind_label})"]
    for line in block.lines:
        parts.append(f"{line.no}| {_line_text(line)}")
        parts.append(f"   IPA| {_line_ipa(line)}")
    return "\n".join(parts)


def build_block_user_prompt(
    block: Block,
    *,
    lang: str,
    block_index: int,
    block_total: int,
    validation_errors: list[str] | None = None,
) -> str:
    """Пользовательский промпт для анализа одного блока."""
    lang_label = _LANG_LABELS.get(lang, lang)
    line_nos = [line.no for line in block.lines]
    lo, hi = min(line_nos), max(line_nos)

    parts = [
        f"Язык песни: {lang_label}.",
        f"Блок {block_index + 1}/{block_total}: «{block.title}» "
        f"({_SECTION_KIND_LABELS.get(block.section_kind, block.section_kind)}, строки {lo}–{hi}).",
        "Проанализируй рифмоконструкцию только в этом блоке. Используй IPA для фонетики.",
        "",
        block_to_prompt_text(block),
    ]

    # Подсказки: эвристика «рифма через строку-заглушку» (конец строки N ~ конец N+2).
    hints = skip_line_hints([block])
    if hints:
        parts.extend([
            "",
            "ВОЗМОЖНЫЕ РИФМЫ ЧЕРЕЗ СТРОКУ (проверь по IPA, не пропускай):",
            *[f"- {h}" for h in hints],
        ])
    if validation_errors:
        parts.extend([
            "",
            "ПРЕДЫДУЩИЙ ОТВЕТ СОДЕРЖАЛ ОШИБКИ — исправь:",
            *[f"- {e}" for e in validation_errors],
        ])
    return "\n".join(parts)
