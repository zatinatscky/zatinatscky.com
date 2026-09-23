"""Чистка сырого текста песни и разбивка на логические блоки.

Убирает мусор выгрузок Genius и распознаёт секции на EN / RU / ES:
  • [Verse 1], [Chorus], [Припев], [Coro], …
  • отдельные строки: Verse 1, Hook, Куплет 2, Chorus:
  • блок «You might also like», Embed, пустые строки.
"""

from __future__ import annotations

import re

from .models import Block, Line, Token
from .sections import parse_section_header

# Явный мусор от Genius.
_JUNK_RE = re.compile(
    r"^\s*(you might also like|\d*\s*embed|see .* live|translations?)\s*$",
    re.IGNORECASE,
)

_SUGGEST_TRIGGER_RE = re.compile(r"you might also like", re.IGNORECASE)

_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+(?:['’ʼ][A-Za-zА-Яа-яЁё]+)?|[^A-Za-zА-Яа-яЁё0-9]+")


def tokenize_line(text: str, line_no: int, line_index: int) -> list[Token]:
    """Разбивает строку на токены-слова и токены-разделители (с сохранением вида)."""
    tokens: list[Token] = []
    for m in _TOKEN_RE.finditer(text):
        chunk = m.group(0)
        is_word = bool(re.match(r"[A-Za-zА-Яа-яЁё0-9]", chunk))
        tokens.append(Token(display=chunk, is_word=is_word, line_no=line_no, line_index=line_index))
    for t in reversed(tokens):
        if t.is_word:
            t.is_last_word = True
            break
    return tokens


def _start_block(header_title: str, section_kind: str) -> Block:
    """Новый блок с заголовком и типом секции."""
    return Block(title=header_title, section_kind=section_kind)


def clean(raw_text: str) -> list[Block]:
    """Превращает сырой текст в список блоков с очищенными строками."""
    blocks: list[Block] = []
    current = _start_block("Intro", "intro")
    skip_suggestions = False
    line_index = 0

    for i, raw in enumerate(raw_text.splitlines(), start=1):
        line = raw.strip()

        # Заголовок секции (скобки или standalone, мультиязычный).
        section = parse_section_header(line)
        if section is not None:
            skip_suggestions = False
            if current.lines:
                blocks.append(current)
            current = _start_block(section.title, section.kind)
            continue

        if _SUGGEST_TRIGGER_RE.search(line):
            skip_suggestions = True
            continue
        if skip_suggestions:
            continue

        if not line or _JUNK_RE.match(line):
            continue

        line_index += 1
        current.lines.append(Line(no=i, index=line_index, tokens=tokenize_line(line, i, line_index)))

    if current.lines:
        blocks.append(current)

    return [b for b in blocks if b.lines]
