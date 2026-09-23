"""Применение «эталонной» разметки рифм (ручной разбор) к токенам.

Автодетектор (rhymes.py) выводит цепочки эвристически и не может дословно
воспроизвести ручной разбор: там есть субъективная группировка и составные
рифменные единицы («копы нас», «том ям»). Этот модуль решает задачу иначе —
он берёт заранее описанную схему рифм песни (JSON) и детерминированно
раскрашивает текст ровно так, как в ручной версии.

Формат JSON-эталона:
{
  "title": "...",
  "chains": [
    {
      "id": "k2",
      "color": "green",                 # имя из палитры (purple/green/blue/orange/pink)
      "sound": "á + з",                 # человекочитаемый паттерн (для таблицы)
      "words": "мазы · Мазду",          # как показать в таблице (дословно)
      "lines": "8",                      # диапазон строк (дословно, для таблицы)
      "kind": "внутренняя",             # тип
      "windows": [[8, 8]],               # окна строк (line_no), где искать единицы
      "units": ["мазы", "Мазду"]         # рифменные единицы: слово или фраза из слов
    },
    ...
  ]
}

Единица "units" может быть многословной ("копы нас") — тогда ищется
последовательность подряд идущих слов. Поиск ограничен окнами "windows",
чтобы повторы слова (припев, «судьба» и т.п.) не цеплялись в чужие цепочки.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Block, Chain, Token
from .yo_restore import fold_yo_for_match


def load_spec(path: Path) -> dict:
    """Читает JSON-эталон с диска."""
    return json.loads(path.read_text(encoding="utf-8"))


def _norm_word(s: str) -> str:
    """Нормализует слово для сравнения: нижний регистр, ё≡е, без пунктуации."""
    return fold_yo_for_match(s)


def _unit_word_parts(unit: str) -> list[str]:
    """Части рифменной единицы для сопоставления с токенами.

    Пробелы делят фразу («копы нас»), дефис внутри слова — тоже («бабл-ти» → бабл + ти),
    потому что токенизатор хранит «бабл» и «ти» отдельно.
    """
    parts: list[str] = []
    for piece in unit.split():
        norm = _norm_word(piece)
        if not norm:
            continue
        if "-" in norm:
            parts.extend(p for p in norm.split("-") if p)
        else:
            parts.append(norm)
    return parts


def _in_windows(line_no: int, windows: list[list[int]]) -> bool:
    """Попадает ли номер строки хотя бы в одно из окон [start, end]."""
    return any(start <= line_no <= end for start, end in windows)


def _word_tokens_in_windows(blocks: list[Block], windows: list[list[int]]) -> list[Token]:
    """Все словесные токены из строк, попадающих в окна (в порядке текста)."""
    result: list[Token] = []
    for block in blocks:
        for line in block.lines:
            if _in_windows(line.no, windows):
                result.extend(line.words())
    return result


def _find_unit(tokens: list[Token], unit: str) -> int:
    """Считает вхождения единицы (слова/фразы) в списке токенов без разметки."""
    unit_words = _unit_word_parts(unit)
    n = len(unit_words)
    hits = 0
    i = 0
    while i + n <= len(tokens):
        window = tokens[i : i + n]
        if [_norm_word(t.display) for t in window] == unit_words:
            hits += 1
            i += n
        else:
            i += 1
    return hits


def _tag_unit(tokens: list[Token], unit: str, chain_id: str) -> int:
    """Помечает все вхождения единицы (слова или фразы) в списке токенов.

    Возвращает число найденных вхождений. Многословная единица ищется как
    последовательность подряд идущих словесных токенов.
    """
    unit_words = _unit_word_parts(unit)
    n = len(unit_words)
    hits = 0
    i = 0
    while i + n <= len(tokens):
        window = tokens[i : i + n]
        if [_norm_word(t.display) for t in window] == unit_words:
            # Не перезаписываем слово, уже размеченное другой цепочкой.
            if any(t.chain for t in window):
                i += 1
                continue
            for t in window:
                t.chain = chain_id
                # Внутренняя рифма = ни одно слово единицы не стоит в конце строки.
                t.internal = not any(w.is_last_word for w in window)
            hits += 1
            i += n
        else:
            i += 1
    return hits


def annotate(blocks: list[Block], spec: dict) -> list[Chain]:
    """Размечает токены блоков по эталону и возвращает список цепочек для вывода."""
    chains: list[Chain] = []
    for raw in spec.get("chains", []):
        cid = raw["id"]
        windows = raw.get("windows", [])
        tokens = _word_tokens_in_windows(blocks, windows)

        # Размечаем все единицы цепочки внутри её окон.
        for unit in raw.get("units", []):
            _tag_unit(tokens, unit, cid)

        chains.append(
            Chain(
                id=cid,
                color=raw.get("color", "green"),
                sound=raw.get("sound", ""),
                words=raw.get("words", " · ".join(raw.get("units", []))),
                lines=raw.get("lines", _lines_label(windows)),
                kind=raw.get("kind", ""),
            )
        )
    return chains


def _lines_label(windows: list[list[int]]) -> str:
    """Строит подпись диапазона строк из окон, если она не задана явно."""
    if not windows:
        return ""
    parts = [f"{a}" if a == b else f"{a}\u2013{b}" for a, b in windows]
    return ", ".join(parts)
