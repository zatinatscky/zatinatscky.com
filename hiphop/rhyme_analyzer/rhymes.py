"""Детекция рифм: рифменные хвосты, фонетическая близость и сборка цепочек.

Идея:
  1. У каждого слова берём «рифменный хвост» — от ударной гласной до конца (IPA).
  2. Считаем близость хвостов: совпадает ли ударный гласный + насколько похож остаток.
  3. Строим граф «созвучий» между близкими словами (в пределах окна строк) и
     выделяем компоненты связности — это и есть звуковые цепочки.
  4. Каждой цепочке назначаем цвет, тип и человекочитаемый ярлык.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from .models import Block, Chain, Token
from .phonetics import STRESS_PRIMARY, STRESS_SECONDARY, VOWELS
from .skip_line import SKIP_LINE_GAP, find_skip_line_pairs, multisyllable_zone_similarity

# Грубые классы гласных (редуцированные сводим к базовым) — рифма держится на них.
_VOWEL_CLASS = {
    "a": "a", "ɐ": "a", "ə": "a", "ʌ": "a", "ɑ": "a", "æ": "a", "ɒ": "a",
    "e": "e", "ɛ": "e", "ɜ": "e",
    "i": "i", "ɪ": "i",
    "o": "o", "ɔ": "o", "ø": "o", "œ": "o",
    "u": "u", "ʊ": "u", "ʉ": "u",
    "ɨ": "y", "y": "y",
}
# Для красивого ярлыка цепочки.
_VOWEL_ACCENT = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú", "y": "ы́"}

# Набор редуцированных гласных (нужен для проверки «открытая ↔ закрытая рифма»).
_VOWEL_REDUCED = set("aeiou")

# 5 цветов палитры Canvas SDK (порядок = порядок назначения цепочкам).
_PALETTE = ["purple", "green", "blue", "orange", "pink"]
# Точные значения берём из colorPalette на стороне Canvas — здесь только ключи-имена,
# которые маппятся в генераторе.

# Параметры детектора.
_LINE_WINDOW = 3  # макс. расстояние между строками, чтобы считать слова рифмой
_RHYME_THRESHOLD = 0.5  # порог похожести хвостов для КОНЦЕВЫХ рифм (мягче — ловим ассонанс)
_INTERNAL_THRESHOLD = 0.8  # строгий порог для ВНУТРЕННИХ созвучий (меньше шума)
_MIN_TAIL_END = 1  # концевая рифма может быть открытой (1 гласная): "судьба"/"навсегда"
_MIN_TAIL_INTERNAL = 3  # внутренняя рифма должна быть многосложной/различимой

# Служебные слова: их не считаем рифмами (предлоги, союзы, частицы, местоимения).
_STOPWORDS = {
    "в", "во", "на", "и", "а", "но", "с", "со", "к", "ко", "о", "об", "у", "за",
    "по", "из", "от", "до", "для", "не", "ни", "же", "бы", "ли", "я", "ты", "мы",
    "вы", "он", "она", "оно", "они", "это", "эта", "этот", "то", "та", "тот", "те",
    "как", "что", "чем", "кто", "был", "была", "было", "были", "её", "его", "их",
    "мне", "нас", "вас", "там", "тут", "вот", "уж", "ещё", "уже", "так", "там",
    "да", "нет", "ну", "вс", "всё", "все", "был", "чё", "че", "ой", "эй",
}


def _tail_strength(tok: Token) -> int:
    """Длина «скелета» хвоста — мера информативности рифмы."""
    return len(_reduce_tail(tok.tail))


def _is_candidate(tok: Token) -> bool:
    """Может ли слово вообще участвовать в рифме."""
    if not tok.tail:
        return False
    if tok.display.lower() in _STOPWORDS:
        return False
    # Концевая рифма может быть открытой (1 гласная); внутренняя — только различимая.
    min_tail = _MIN_TAIL_END if tok.is_last_word else _MIN_TAIL_INTERNAL
    if _tail_strength(tok) < min_tail:
        return False
    return True


def _vowels_compatible(v1: str, v2: str) -> bool:
    """и и ы в русском рифмуются свободно — считаем их совместимыми."""
    if v1 == v2:
        return True
    return {v1, v2} <= {"i", "y"}


def _clean_ipa(ipa: str) -> str:
    """Убирает вторичное ударение и разделители, оставляя фонемы и ˈ."""
    return ipa.replace(STRESS_SECONDARY, "").replace("ː", "").strip()


def extract_tail(ipa: str) -> tuple[str, str]:
    """Возвращает (рифменный хвост, класс ударной гласной).

    Хвост — от ударной гласной до конца слова (без знака ударения).
    Если ударение не отмечено — берём последнюю гласную (монослог/fallback).
    """
    s = _clean_ipa(ipa)
    if not s:
        return "", ""

    # Найдём позицию ударной гласной.
    stressed_pos = -1
    if STRESS_PRIMARY in s:
        i = s.index(STRESS_PRIMARY)
        # первая гласная после знака ударения
        for j in range(i + 1, len(s)):
            if s[j] in VOWELS:
                stressed_pos = j
                break
    if stressed_pos == -1:
        # последняя гласная
        for j in range(len(s) - 1, -1, -1):
            if s[j] in VOWELS:
                stressed_pos = j
                break
    if stressed_pos == -1:
        return "", ""  # слово без гласных (напр. предлог "с")

    tail = s[stressed_pos:].replace(STRESS_PRIMARY, "")
    vowel_class = _VOWEL_CLASS.get(s[stressed_pos], s[stressed_pos])
    return tail, vowel_class


def _reduce_tail(tail: str) -> str:
    """Сводит хвост к «скелету»: гласные -> классы (ы сводим к и), согласные оставляем."""
    out = []
    for ch in tail:
        if ch in VOWELS:
            cls = _VOWEL_CLASS.get(ch, ch)
            out.append("i" if cls == "y" else cls)  # ы -> и для сравнения
        elif ch == STRESS_PRIMARY:
            continue
        else:
            out.append(ch)
    return "".join(out)


def tail_similarity(a: Token, b: Token) -> float:
    """Похожесть рифменных хвостов двух слов в диапазоне 0..1."""
    if not a.tail or not b.tail:
        return 0.0
    # Разные ударные гласные — для рифмы это почти приговор (и/ы — исключение).
    if not _vowels_compatible(a.vowel, b.vowel):
        return 0.0
    ra, rb = _reduce_tail(a.tail), _reduce_tail(b.tail)
    # Открытая рифма (голая ударная гласная: "судьба") не рифмуется с закрытой
    # ("следят") — иначе все á-слова слиплись бы в одну цепочку.
    bare_a = len(ra) == 1 and ra in _VOWEL_REDUCED
    bare_b = len(rb) == 1 and rb in _VOWEL_REDUCED
    if bare_a != bare_b:
        return 0.0
    return SequenceMatcher(None, ra, rb).ratio()


class _UnionFind:
    """Система непересекающихся множеств для сборки цепочек."""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def detect_chains(blocks: list[Block]) -> list[Chain]:
    """Главная функция: проставляет токенам .chain/.internal и возвращает метаданные цепочек."""
    # 1. Считаем хвосты для всех слов, в кандидаты берём только значимые.
    words: list[Token] = []
    for block in blocks:
        for line in block.lines:
            for tok in line.words():
                tok.tail, tok.vowel = extract_tail(tok.ipa)
                if _is_candidate(tok):
                    words.append(tok)

    n = len(words)
    uf = _UnionFind(n)

    # 2. Связываем созвучные слова в пределах окна строк.
    #    Концевые рифмы (оба слова — в конце строки) — более мягкий порог;
    #    внутренние созвучия — более строгий, чтобы не плодить шум.
    for i in range(n):
        for j in range(i + 1, n):
            if words[j].line_index - words[i].line_index > _LINE_WINDOW:
                break  # слова отсортированы по строкам — дальше только дальше
            a, b = words[i], words[j]
            # Одинаковые слова (повторы строк/припева) — это не рифма.
            if a.norm.lower() == b.norm.lower():
                continue
            both_end = a.is_last_word and b.is_last_word
            threshold = _RHYME_THRESHOLD if both_end else _INTERNAL_THRESHOLD
            if tail_similarity(a, b) >= threshold:
                uf.union(i, j)

    # 2b. Рифмы «через строку»: концы строк i и i+2 (между ними заглушка).
    last_by_line: dict[int, Token] = {}
    for block in blocks:
        for line in block.lines:
            w = line.words()
            if w:
                last_by_line[line.index] = w[-1]

    for line_a, line_b, _score in find_skip_line_pairs(blocks):
        ta = last_by_line.get(line_a.index)
        tb = last_by_line.get(line_b.index)
        if not ta or not tb:
            continue
        # Находим индексы в words[] для union.
        idx_a = next((i for i, w in enumerate(words) if w is ta), None)
        idx_b = next((i for i, w in enumerate(words) if w is tb), None)
        if idx_a is not None and idx_b is not None:
            uf.union(idx_a, idx_b)

    # 2c. Внутри строки: «кашей» может рифмоваться с концом через заглушку —
    #     связываем предпоследнее слово строки с концом строки i+2, если зона совпала.
    for line_a, line_b, score in find_skip_line_pairs(blocks):
        wa = line_a.words()
        if len(wa) < 2:
            continue
        penult = wa[-2]
        last_b = line_b.words()[-1]
        if multisyllable_zone_similarity(penult.ipa, last_b.ipa) >= _RHYME_THRESHOLD:
            ia = next((i for i, w in enumerate(words) if w is penult), None)
            ib = next((i for i, w in enumerate(words) if w is last_b), None)
            if ia is not None and ib is not None:
                uf.union(ia, ib)

    # 3. Группируем по компонентам связности.
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    # 3b. Склеиваем одинаковые цепочки из повторов (припев повторяется несколько раз):
    #     компоненты с тем же набором слов считаем одной цепочкой.
    by_signature: dict[frozenset, list[int]] = {}
    merged_components: list[list[int]] = []
    for idxs in sorted(groups.values(), key=lambda x: min(x)):
        sig = frozenset(words[i].norm.lower() for i in idxs)
        if sig in by_signature:
            by_signature[sig].extend(idxs)
        else:
            by_signature[sig] = idxs
            merged_components.append(idxs)

    # 4. Оставляем только настоящие цепочки (>=2 слов с разными вхождениями).
    chains: list[Chain] = []
    chain_counter = 0
    # Сортируем цепочки по первому появлению (для стабильных цветов).
    ordered = sorted(merged_components, key=lambda idxs: min(idxs))
    for idxs in ordered:
        members = [words[i] for i in idxs]
        # Настоящая цепочка — это >=2 РАЗНЫХ слов (а не повтор одного слова в припеве).
        if len({m.norm.lower() for m in members}) < 2:
            continue
        # Цепочка должна быть «заякорена» концевой рифмой: чисто внутренние
        # совпадения (оба слова в середине строк) чаще всего случайны.
        if not any(m.is_last_word for m in members):
            continue
        chain_counter += 1
        cid = f"c{chain_counter}"
        color = _PALETTE[(chain_counter - 1) % len(_PALETTE)]

        # Проставляем токенам id цепочки и флаг внутренней рифмы.
        for tok in members:
            tok.chain = cid
            tok.internal = not tok.is_last_word

        chains.append(_build_chain_meta(cid, color, members))

    return chains


def _classify(members: list[Token]) -> str:
    """Определяет тип цепочки по средней похожести хвостов."""
    sims = []
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            sims.append(tail_similarity(members[i], members[j]))
    avg = sum(sims) / len(sims) if sims else 0.0

    # Рифма через строку-заглушку: строки ровно через одну (gap=2).
    line_idxs = sorted({m.line_index for m in members})
    is_skip_line = (
        len(line_idxs) >= 2
        and any(abs(line_idxs[j] - line_idxs[i]) == SKIP_LINE_GAP
                for i in range(len(line_idxs)) for j in range(i + 1, len(line_idxs)))
    )

    has_internal = any(t.internal for t in members)
    if avg >= 0.9:
        base = "точная"
    elif avg >= 0.75:
        base = "почти точная"
    else:
        base = "ассонанс"
    if is_skip_line and avg < 0.75:
        base = "через строку (" + base + ")"
    elif is_skip_line:
        base = "через строку"
    if len(members) >= 4:
        base = "многосложная (" + base + ")"
    elif has_internal:
        base = base + " (внутр.)"
    return base


def _build_chain_meta(cid: str, color: str, members: list[Token]) -> Chain:
    """Собирает человекочитаемые метаданные цепочки для таблицы/легенды."""
    vowel = members[0].vowel
    accent = _VOWEL_ACCENT.get(vowel, vowel)
    # Ярлык: ударный гласный + типичный скелет хвоста.
    skeleton = _reduce_tail(members[0].tail)
    sound = f"{accent} ({skeleton})"

    words_str = " · ".join(dict.fromkeys(t.display for t in members))  # уникальные, по порядку
    line_nos = sorted({t.line_no for t in members})
    lines_str = f"{line_nos[0]}" if len(line_nos) == 1 else f"{line_nos[0]}–{line_nos[-1]}"
    kind = _classify(members)

    return Chain(id=cid, color=color, sound=sound, words=words_str, lines=lines_str, kind=kind)
