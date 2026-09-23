"""Общие структуры данных, которыми обмениваются модули пайплайна."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Token:
    """Один кусочек строки: слово или разделитель (пробел/пунктуация)."""

    display: str  # как в исходном тексте (показывается в Canvas)
    is_word: bool  # True — это слово; False — пробел/знак препинания

    # Заполняется на этапах нормализации и фонетики:
    norm: str = ""  # нормализованная форма для произношения (8 -> "восемь")
    ipa: str = ""  # транскрипция IPA с ударением
    tail: str = ""  # рифменный хвост (от ударной гласной до конца), IPA
    vowel: str = ""  # класс ударной гласной: a/e/i/o/u/y ("" если не слово)

    # Позиция в документе:
    line_no: int = 0  # номер исходной строки
    line_index: int = 0  # сквозной индекс строки (для оценки близости)
    is_last_word: bool = False  # последнее слово в строке (концевая рифма)

    # Результат детекции рифм:
    chain: Optional[str] = None  # id звуковой цепочки, если слово рифмуется
    internal: bool = False  # созвучие внутри строки (слово не на конце)


@dataclass
class Line:
    """Строка текста = номер + список токенов."""

    no: int  # исходный номер строки
    index: int  # сквозной индекс
    tokens: list[Token] = field(default_factory=list)

    def words(self) -> list[Token]:
        """Только словесные токены строки."""
        return [t for t in self.tokens if t.is_word]


@dataclass
class Block:
    """Логический блок песни (припев / куплет / интро)."""

    title: str
    lines: list[Line] = field(default_factory=list)
    section_kind: str = "other"  # verse | chorus | hook | bridge | intro | outro | other


@dataclass
class Chain:
    """Звуковая цепочка — группа созвучных слов."""

    id: str
    color: str
    sound: str  # человекочитаемый паттерн, напр. "ó (…ʂə)"
    words: str  # перечисление слов цепочки
    lines: str  # диапазон строк
    kind: str  # тип: концевая / внутренняя / многосложная и т.п.
