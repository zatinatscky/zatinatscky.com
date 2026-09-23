"""Форматирование текста для вывода (отчёт, HTML, превью).

Анализ и сопоставление рифм идут по исходному вводу; здесь — только отображение.
"""

from __future__ import annotations

from .models import Token


def capitalize_word_start(word: str) -> str:
    """Первая буква слова — заглавная (остальное без изменений)."""
    for i, ch in enumerate(word):
        if ch.isalpha():
            upper = ch.upper()
            if upper != ch:
                return word[:i] + upper + word[i + 1 :]
            return word
    return word


def token_displays_for_output(tokens: list[Token]) -> list[str]:
    """Текст токенов строки для показа: у первого слова — заглавная буква."""
    displays = [t.display for t in tokens]
    for i, tok in enumerate(tokens):
        if tok.is_word:
            displays[i] = capitalize_word_start(tok.display)
            break
    return displays
