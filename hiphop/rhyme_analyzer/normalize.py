"""Нормализация токенов: превращаем числа и латиницу в произносимые слова.

Это ключевой шаг: без него цифры (8) и бренды (Porsche) не попадут в фонетический
анализ и их рифмы будут потеряны. Например:
    8     -> "восемь"   (рифма к "больше")
    i8    -> "айвосемь" (рифма к "позе")
    Porsche -> "порше"
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from num2words import num2words

from .models import Block, Token

_LEXICON_PATH = Path(__file__).with_name("lexicon.json")

# Грубая посимвольная транслитерация латиницы в русское звучание —
# fallback для слов, которых нет в lexicon.json. Диграфы идут первыми.
_TRANSLIT_DIGRAPHS = [
    ("sch", "ш"), ("tch", "ч"), ("sh", "ш"), ("ch", "ч"), ("th", "т"),
    ("ph", "ф"), ("ck", "к"), ("oo", "у"), ("ee", "и"), ("ou", "ау"),
    ("ay", "эй"), ("ai", "эй"), ("ey", "эй"), ("ge", "дж"), ("dge", "дж"),
    ("qu", "кв"), ("ya", "я"), ("yu", "ю"), ("oa", "оу"),
]
_TRANSLIT_SINGLE = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г",
    "h": "х", "i": "и", "j": "дж", "k": "к", "l": "л", "m": "м", "n": "н",
    "o": "о", "p": "п", "q": "к", "r": "р", "s": "с", "t": "т", "u": "у",
    "v": "в", "w": "в", "x": "кс", "y": "й", "z": "з",
}

_LATIN_RE = re.compile(r"[A-Za-z]")
_APOSTROPHE_RE = re.compile(r"['’ʼ]")


def _load_lexicon() -> dict[str, str]:
    """Читает пользовательский словарь чтения латиницы/брендов."""
    data = json.loads(_LEXICON_PATH.read_text(encoding="utf-8"))
    return {k.lower(): v for k, v in data.items() if not k.startswith("_")}


def _translit_latin(word: str) -> str:
    """Приблизительная транслитерация латинского слова в кириллицу по звучанию."""
    s = word.lower()
    for digraph, repl in _TRANSLIT_DIGRAPHS:
        s = s.replace(digraph, repl)
    out = []
    for ch in s:
        out.append(_TRANSLIT_SINGLE.get(ch, ch))
    return "".join(out)


def _normalize_number(tok: str) -> str:
    """Число -> слова по-русски. Длинные «телефонные» числа читаем по цифрам."""
    # Чистое целое — читаем как число (8 -> восемь, 183 -> сто восемьдесят три).
    if tok.isdigit():
        # короткие числа читаем целиком, очень длинные — по цифрам
        if len(tok) <= 4:
            return num2words(int(tok), lang="ru")
        return " ".join(num2words(int(d), lang="ru") for d in tok)
    return tok


class Normalizer:
    """Нормализатор токенов с подгружаемым словарём."""

    def __init__(self, extra_lexicon: dict[str, str] | None = None) -> None:
        self.lexicon = _load_lexicon()
        if extra_lexicon:
            self.lexicon.update({k.lower(): v for k, v in extra_lexicon.items()})

    def normalize_token(self, word: str) -> str:
        """Возвращает произносимую (кириллическую) форму одного слова."""
        key = word.lower()

        # 1) Точное совпадение в словаре (бренды, особые формы вроде "i8").
        if key in self.lexicon:
            return self.lexicon[key]

        # 2) Токен с цифрами + буквами (i8) — словарь не нашёл, разберём по частям.
        if any(c.isdigit() for c in word) and not word.isdigit():
            parts = re.findall(r"\d+|[^\d]+", word)
            return "".join(
                _normalize_number(p) if p.isdigit() else self.normalize_token(p)
                for p in parts
            )

        # 3) Чистое число.
        if word.isdigit():
            return _normalize_number(word)

        # 4) Латиница (возможно с кириллическим окончанием через апостроф: iTunes'е).
        if _LATIN_RE.search(word):
            # отделим латинскую основу от кириллического хвоста
            m = re.match(r"^([A-Za-z]+)(?:['’ʼ]?([А-Яа-яЁё]+))?$", word)
            if m:
                base = self.lexicon.get(m.group(1).lower()) or _translit_latin(m.group(1))
                suffix = m.group(2) or ""
                return base + suffix
            return _translit_latin(_APOSTROPHE_RE.sub("", word))

        # 5) Обычное русское слово — без изменений.
        return word

    def apply(self, blocks: list[Block]) -> None:
        """Проставляет .norm всем словесным токенам (мутирует структуру)."""
        for block in blocks:
            for line in block.lines:
                for tok in line.tokens:
                    if tok.is_word:
                        tok.norm = self.normalize_token(tok.display)
