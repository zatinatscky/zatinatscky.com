"""Восстановление буквы «ё» там, где «е» читается как [о]/[jo].

В рэп-текстах «счет» часто пишут через «е», но произносят «счёт» — без этого
espeak даёт ɕˈet и ложные рифмы с другими словами на -et.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .models import Block

_LEXICON_PATH = Path(__file__).with_name("yo_lexicon.json")
_CYR_WORD_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9]+(?:['’ʼ][A-Za-zА-Яа-яЁё0-9]+)?$")

# Суффикс 3 л. ед.: -ет → -ёт (только для согласной основы, не из блоклиста).
_VERB_YO_ET_SUFFIX = ("ет", "ёт")

# Формы, где «-ет/-ете» читается как [e], не [o] — эвристику -ёт не применяем.
_YO_ET_KEEP_E = frozenset({
    "будет", "будете", "будешь",
    "может", "можете", "можешь",
    "сможет", "сможете", "сможешь",
    "знает", "знаете", "знаешь",
    "умеет", "умеете", "умеешь",
    "имеет", "имеете", "имеешь",
    "сделает", "сделаете", "сделаешь",
    "хочет", "хочете", "хочешь",
    "говорит", "говорите", "говоришь",
    "стоит", "стоите", "стоишь",
    "летит", "летите", "летишь",
    "играет", "играете", "играешь",
    "думает", "думаете", "думаешь",
    "работает", "работаете", "работаешь",
    "платит", "платите", "платишь",
    "любит", "любите", "любишь",
})


def _load_lexicon() -> dict[str, str]:
    data = json.loads(_LEXICON_PATH.read_text(encoding="utf-8"))
    return {k.lower(): v for k, v in data.items() if not k.startswith("_")}


def _preserve_case(original: str, fixed: str) -> str:
    """Сохраняет регистр исходного токена (ФОТ, Счет, счет)."""
    if original.isupper():
        return fixed.upper()
    if original[:1].isupper() and original[1:].islower():
        return fixed[:1].upper() + fixed[1:]
    # Смешанный регистр (ФОТ уже обработан) — по символам.
    out: list[str] = []
    for o, f in zip(original, fixed):
        out.append(f.upper() if o.isupper() else f.lower())
    if len(fixed) > len(original):
        out.extend(fixed[len(original) :])
    return "".join(out)


def _verb_yo_et_singular(lower: str) -> str | None:
    """Эвристика 3 л. ед.: берет → берёт (только согласная + не в блоклисте)."""
    if lower in _YO_ET_KEEP_E:
        return None
    if re.search(r"[A-Za-z]", lower):
        return None
    src, dst = _VERB_YO_ET_SUFFIX
    if not lower.endswith(src) or len(lower) <= len(src):
        return None
    stem = lower[: -len(src)]
    if not stem or stem[-1] in "аеёиоуыэюя":
        return None
    return stem + dst


def _verb_yo_conjugation_from_lex(lower: str, lex: dict[str, str]) -> str | None:
    """-ете / -ешь только если в лексиконе есть 3 л. ед. на -ёт (берет → берёте)."""
    for src, dst in (("ете", "ёте"), ("ешь", "ёшь")):
        if not lower.endswith(src) or len(lower) <= len(src):
            continue
        if lower in _YO_ET_KEEP_E:
            return None
        stem = lower[: -len(src)]
        if not stem:
            continue
        fixed_et = lex.get(stem + "ет")
        if not fixed_et or not fixed_et.endswith("ёт"):
            continue
        yo_stem = fixed_et[:-2]
        if yo_stem:
            return yo_stem + dst
    return None


def _verb_yo_form(lower: str, lex: dict[str, str]) -> str | None:
    """Согласованные формы глагола: лексикон для -ете/-ешь, эвристика для -ет."""
    from_lex = _verb_yo_conjugation_from_lex(lower, lex)
    if from_lex:
        return from_lex
    return _verb_yo_et_singular(lower)


def restore_yo_in_word(word: str, *, lexicon: dict[str, str] | None = None) -> str:
    """Возвращает слово с «ё» в произносимых позициях (или исходное, если правок нет)."""
    if not word or not _CYR_WORD_RE.match(word):
        return word
    if re.fullmatch(r"[A-Za-z0-9]+", word):
        return word

    lex = lexicon if lexicon is not None else _load_lexicon()
    lower = word.lower()

    if lower in lex:
        return _preserve_case(word, lex[lower])

    # Явно не меняем формы на -ет/-ете с звуком [e].
    if lower in _YO_ET_KEEP_E:
        return word

    # Слово уже с «ё» — не трогаем.
    if "ё" in lower:
        return word

    guessed = _verb_yo_form(lower, lex)
    if guessed:
        return _preserve_case(word, guessed)

    return word


def fold_yo_for_match(word: str) -> str:
    """Нормализация для сопоставления единиц LLM с токенами: ё ≡ е."""
    return word.strip().strip(".,!?;:—–-…\"'«»()").lower().replace("ё", "е")


class YoRestorer:
    """Проставляет «ё» в display и norm перед транскрипцией."""

    def __init__(self, extra: dict[str, str] | None = None) -> None:
        self.lexicon = _load_lexicon()
        if extra:
            self.lexicon.update({k.lower(): v for k, v in extra.items()})

    def apply(self, blocks: list[Block], *, lang: str = "ru") -> int:
        """Обновляет токены; возвращает число исправленных слов."""
        if lang != "ru":
            return 0
        changed = 0
        for block in blocks:
            for line in block.lines:
                for tok in line.tokens:
                    if not tok.is_word:
                        continue
                    fixed = restore_yo_in_word(tok.display, lexicon=self.lexicon)
                    if fixed != tok.display:
                        tok.display = fixed
                        tok.norm = fixed
                        changed += 1
        return changed
