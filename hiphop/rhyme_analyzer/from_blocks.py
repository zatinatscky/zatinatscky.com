"""Сборка Block из структурированного ввода веб-формы (без чистки Genius)."""

from __future__ import annotations

from dataclasses import dataclass

from .block_limits import MAX_BLOCKS, ALLOWED_KINDS, validate_block_text
from .cleaning import tokenize_line
from .models import Block, Line

# Подписи секций по умолчанию (RU); при необходимости расширим по lang.
_DEFAULT_TITLES = {
    "verse": "Куплет",
    "chorus": "Припев",
    "hook": "Hook",
}


@dataclass
class BlockSubmission:
    """Один блок из POST /api/analyze."""

    kind: str  # verse | chorus | hook
    text: str
    title: str | None = None


def _default_title(kind: str, ordinal: int) -> str:
    """Автозаголовок: «Куплет 1», «Припев 2» и т.д."""
    base = _DEFAULT_TITLES.get(kind, kind.capitalize())
    return f"{base} {ordinal}"


def _kind_ordinal(blocks: list[BlockSubmission], index: int) -> int:
    """Порядковый номер блока того же kind до index включительно."""
    kind = blocks[index].kind
    return sum(1 for i, b in enumerate(blocks) if i <= index and b.kind == kind)


def validate_submission(blocks: list[BlockSubmission]) -> list[str]:
    """Валидация всей формы перед анализом (пустые блоки пропускаются)."""
    errors: list[str] = []
    filled = [b for b in blocks if b.text.strip()]

    if not filled:
        errors.append("заполните хотя бы один блок текста")
        return errors
    if len(blocks) > MAX_BLOCKS:
        errors.append(f"не больше {MAX_BLOCKS} блоков (сейчас {len(blocks)})")
        return errors

    for i, block in enumerate(filled, start=1):
        kind = block.kind.strip().lower()
        if kind not in ALLOWED_KINDS:
            errors.append(
                f"блок {i}: неизвестный тип «{block.kind}» "
                f"(допустимо: {', '.join(sorted(ALLOWED_KINDS))})"
            )
            continue
        label = block.title.strip() if block.title and block.title.strip() else f"блок {i}"
        errors.extend(validate_block_text(block.text, block_label=label))

    return errors


def blocks_from_submission(submissions: list[BlockSubmission]) -> list[Block]:
    """Превращает ввод формы в список Block для пайплайна (без пустых блоков)."""
    filled = [s for s in submissions if s.text.strip()]
    errors = validate_submission(filled)
    if errors:
        raise ValueError("; ".join(errors))

    result: list[Block] = []
    line_index = 0

    for i, sub in enumerate(filled):
        kind = sub.kind.strip().lower()
        title = (sub.title or "").strip() or _default_title(kind, _kind_ordinal(filled, i))

        block = Block(title=title, section_kind=kind)
        # Нумерация line_no сквозная по всей песне — важно для LLM и эталона.
        for raw_line in sub.text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            line_index += 1
            block.lines.append(
                Line(no=line_index, index=line_index, tokens=tokenize_line(line, line_index, line_index))
            )

        if block.lines:
            result.append(block)

    if not result:
        raise ValueError("после разбора не осталось ни одной строки текста")
    return result
