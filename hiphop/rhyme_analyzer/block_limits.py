"""Лимиты блоков текста для веб-формы и API.

Ограничения защищают контекст LLM: один блок ≈ один запрос к модели.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- Публичные лимиты (дублируются на фронтенде через GET /api/limits) ---
MAX_BLOCKS = 5
MAX_LINES_PER_BLOCK = 24
MAX_WORDS_PER_BLOCK = 200
MAX_CHARS_PER_BLOCK = 1000

ALLOWED_KINDS = frozenset({"verse", "chorus", "hook"})

_WORD_RE = re.compile(
    r"[A-Za-zА-Яа-яЁё0-9]+(?:['’ʼ][A-Za-zА-Яа-яЁё0-9]+)?",
    re.UNICODE,
)


@dataclass(frozen=True)
class BlockStats:
    """Счётчики одного блока текста."""

    lines: int
    words: int
    chars: int


@dataclass(frozen=True)
class BlockLimits:
    """Снимок лимитов для API и фронтенда."""

    max_blocks: int = MAX_BLOCKS
    max_lines: int = MAX_LINES_PER_BLOCK
    max_words: int = MAX_WORDS_PER_BLOCK
    max_chars: int = MAX_CHARS_PER_BLOCK


def count_words(text: str) -> int:
    """Число слов в тексте (та же эвристика, что при токенизации)."""
    return len(_WORD_RE.findall(text))


def count_lines(text: str) -> int:
    """Число непустых строк после trim."""
    return sum(1 for line in text.splitlines() if line.strip())


def block_stats(text: str) -> BlockStats:
    """Счётчики блока: строки, слова, символы (включая переносы)."""
    return BlockStats(lines=count_lines(text), words=count_words(text), chars=len(text))


def validate_block_text(text: str, *, block_label: str = "блок") -> list[str]:
    """Проверяет один блок; возвращает список ошибок (пустой = ок)."""
    errors: list[str] = []
    stats = block_stats(text)

    if not text.strip():
        errors.append(f"{block_label}: текст не может быть пустым")
        return errors

    if stats.lines > MAX_LINES_PER_BLOCK:
        errors.append(
            f"{block_label}: слишком много строк ({stats.lines}/{MAX_LINES_PER_BLOCK})"
        )
    if stats.words > MAX_WORDS_PER_BLOCK:
        errors.append(
            f"{block_label}: слишком много слов ({stats.words}/{MAX_WORDS_PER_BLOCK})"
        )
    if stats.chars > MAX_CHARS_PER_BLOCK:
        errors.append(
            f"{block_label}: слишком много символов ({stats.chars}/{MAX_CHARS_PER_BLOCK})"
        )
    return errors
