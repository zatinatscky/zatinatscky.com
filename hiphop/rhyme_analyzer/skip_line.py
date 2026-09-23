"""Рифмы «через строку» (skip-line / bridge).

Паттерн: конец строки N рифмуется с концом строки N+2, а строка N+1 — заглушка,
которая при быстром чтении сливается со следующей и не участвует в рифме.

Пример:
  2. … кашей манной
  3. … даты и подписи   ← заглушка
  4. … ветерану
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from .models import Block, Line, Token
from .phonetics import STRESS_PRIMARY, STRESS_SECONDARY, VOWELS

# Грубые классы гласных (как в rhymes.py).
_VOWEL_CLASS = {
    "a": "a", "ɐ": "a", "ə": "a", "ʌ": "a", "ɑ": "a", "æ": "a", "ɒ": "a",
    "e": "e", "ɛ": "e", "ɜ": "e",
    "i": "i", "ɪ": "i",
    "o": "o", "ɔ": "o", "ø": "o", "œ": "o",
    "u": "u", "ʊ": "u", "ʉ": "u",
    "ɨ": "y", "y": "y",
}


def _clean_ipa(ipa: str) -> str:
    return ipa.replace(STRESS_SECONDARY, "").replace("ː", "").strip()


def _reduce_tail(tail: str) -> str:
    out = []
    for ch in tail:
        if ch in VOWELS:
            cls = _VOWEL_CLASS.get(ch, ch)
            out.append("i" if cls == "y" else cls)
        elif ch == STRESS_PRIMARY:
            continue
        else:
            out.append(ch)
    return "".join(out)


def _vowels_compatible(v1: str, v2: str) -> bool:
    if v1 == v2:
        return True
    return {v1, v2} <= {"i", "y"}


# Задние гласные: в рэпе -ок|-ук часто рифмуются (жесток|броук).
_BACK_VOWEL_CLASSES = frozenset({"o", "u"})
# Порог посыльного ассонанса для снятия «разрыва схемы».
_CODA_ASSONANCE_MIN = 0.65


def _final_syllable_coda(ipa: str) -> str:
    """Последний слог слова (от финальной гласной): ok, uk, ik…"""
    s = _clean_ipa(ipa)
    if not s:
        return ""
    positions = [i for i, ch in enumerate(s) if ch in VOWELS]
    if not positions:
        return ""
    return _reduce_tail(s[positions[-1] :])


def _coda_assonance_similarity(ipa_a: str, ipa_b: str) -> float:
    """Ассонанс финального слога: общий согласный хвост + близкие гласные (о|у).

    Пример: жесток (…ˈok) ~ броук (…ˈuk) — ударные o≠u, но посыльный -к и о/у.
    """
    ca, cb = _final_syllable_coda(ipa_a), _final_syllable_coda(ipa_b)
    if not ca or not cb:
        return 0.0
    if ca == cb:
        return 1.0
    if ca[-1] != cb[-1]:
        return 0.0
    va, vb = ca[0], cb[0]
    if va == vb:
        return 0.9
    if {va, vb} <= _BACK_VOWEL_CLASSES:
        return 0.75
    if _vowels_compatible(va, vb):
        return 0.68
    return SequenceMatcher(None, ca, cb).ratio() * 0.85


def _stressed_vowel_class(ipa: str) -> str | None:
    """Класс ударной гласной (после ˈ); без ударения — последняя гласная."""
    if not ipa:
        return None
    if STRESS_PRIMARY in ipa:
        idx = ipa.index(STRESS_PRIMARY)
        for ch in ipa[idx + 1 :]:
            if ch in VOWELS:
                cls = _VOWEL_CLASS.get(ch, ch)
                return "i" if cls == "y" else cls
        return None
    for ch in reversed(ipa.replace(STRESS_SECONDARY, "")):
        if ch in VOWELS:
            cls = _VOWEL_CLASS.get(ch, ch)
            return "i" if cls == "y" else cls
    return None


def _stress_rhyme_compatible(ipa_a: str, ipa_b: str) -> bool:
    """Ударные гласные совместимы для рифмы (е≠а, и≈ы)."""
    va = _stressed_vowel_class(ipa_a)
    vb = _stressed_vowel_class(ipa_b)
    if va is None or vb is None:
        return True
    return _vowels_compatible(va, vb)

# Ровно одна строка между рифмующимися концами.
SKIP_LINE_GAP = 2

# Мягче обычного порога: рифма часто ассонанс на 2+ слога (…анной ~ …ану).
_SKIP_LINE_THRESHOLD = 0.46

# Соседние строки с разными концовками (найти|колеса): ниже — разрыв схемы.
_RHYME_BOUNDARY_11_MAX = 0.35

# Соседние строки: концовки из 2 слов («Наших Данных» ~ «кашей манной»).
CONSECUTIVE_PHRASE_THRESHOLD = 0.45

# Внутренняя рифма между соседними строками (гномиков ~ экономике).
_INTERNAL_CROSS_LINE_THRESHOLD = 0.55
_MIN_INTERNAL_WORD_CHARS = 4
# Минимум слов между якорем в середине и финальной рифмой (дашборд … дал в рот).
_MIN_WORDS_BEFORE_END_RHYME = 2

# Окна слов на концах соседних строк: симметричные и асимметричные (1↔2, 1↔3).
_ADJACENT_WINDOWS: tuple[tuple[int, int], ...] = (
    (2, 2),
    (1, 1),
    (1, 2),
    (1, 3),
    (2, 1),
    (3, 1),
)

# Сколько последних гласных брать в «зону» конца слова / фразы.
_VOWELS_FROM_END = 2
_PHRASE_VOWELS_FROM_END = 3

# Служебные слова в хвосте строки не несут рифму («из трущоб» → только «трущоб»).
_RHYME_FILLERS = {
    "в", "во", "на", "и", "а", "но", "с", "со", "к", "ко", "о", "об", "у", "за",
    "по", "из", "от", "до", "для", "не", "ни", "же", "бы", "ли", "как", "что",
    "то", "та", "тот", "эта", "этот", "те", "это", "вот", "там", "тут", "ну",
    "да", "нет", "при", "про", "под", "над", "без", "меж", "через",
}


@dataclass(frozen=True)
class AdjacentPhraseMatch:
    """Созвучие концов двух соседних строк с конкретными unit для разметки."""

    line_a: Line
    line_b: Line
    unit_a: str
    unit_b: str
    n_words_a: int
    n_words_b: int
    score: float

    @property
    def asymmetric(self) -> bool:
        return self.n_words_a != self.n_words_b


@dataclass(frozen=True)
class InternalCrossLineMatch:
    """Внутреннее созвучие: слово в строке N ↔ слово в строке N+1 (не концы)."""

    line_a: Line
    line_b: Line
    unit_a: str
    unit_b: str
    score: float


@dataclass(frozen=True)
class IntraLineRhymeMatch:
    """Внутренняя рифма в одной строке: слово в середине ↔ хвостовая фраза.

    Пример: «Сделал дашборд, … дал в рот» — дашборд ~ дал в рот (паттерн гласных а-о).
    """

    line: Line
    unit_a: str
    unit_b: str
    n_words_b: int
    score: float

    @property
    def asymmetric(self) -> bool:
        return self.n_words_b > 1


def _is_rhyme_candidate_word(tok: Token) -> bool:
    """Слово-кандидат для внутренней рифмы (не служебное, не слишком короткое)."""
    if not tok.is_word or not tok.ipa:
        return False
    if _is_filler_word(tok.display):
        return False
    return len(tok.display.strip()) >= _MIN_INTERNAL_WORD_CHARS


def _is_line_end_rhyme_word(tok: Token) -> bool:
    """Короткое слово в конце строки — допустимая рифменная единица (рот, ук)."""
    if not tok.is_word or not tok.ipa or not tok.is_last_word:
        return False
    if _is_filler_word(tok.display):
        return False
    return len(tok.display.strip()) >= 2


def _vowel_class_sequence_ipa(ipa: str) -> str:
    """Классы гласных слова/фразы по порядку (дашборд → «ao»)."""
    seq: list[str] = []
    for ch in _clean_ipa(ipa):
        if ch in VOWELS:
            cls = _VOWEL_CLASS.get(ch, ch)
            seq.append("i" if cls == "y" else cls)
    return "".join(seq)


def _vowel_pattern_from_tokens(tokens: list[Token], *, skip_fillers: bool = False) -> str:
    """Последовательность гласных по токенам; служебные можно пропустить («в» в «дал в рот»)."""
    parts: list[str] = []
    for tok in tokens:
        if skip_fillers and _is_filler_word(tok.display):
            continue
        parts.append(_vowel_class_sequence_ipa(tok.ipa))
    return "".join(parts)


def _vowel_pattern_similarity(seq_a: str, seq_b: str) -> float:
    if not seq_a or not seq_b:
        return 0.0
    return SequenceMatcher(None, seq_a, seq_b).ratio()


def _phrase_chunk_start_index(words: list[Token], chunk: list[Token]) -> int:
    """Индекс первого слова хвостовой фразы в строке."""
    if not chunk:
        return len(words)
    first = chunk[0]
    for i, w in enumerate(words):
        if w is first:
            return i
    return len(words)


def internal_word_phrase_similarity(word: Token, phrase: list[Token]) -> tuple[float, float]:
    """Ассонанс внутреннего слова с хвостовой фразой; возвращает (общий, паттерн гласных)."""
    if not word.ipa or not phrase:
        return 0.0, 0.0

    seq_w = _vowel_pattern_from_tokens([word])
    # Гласные фразы без предлогов/частиц — «дал в рот» → а-о, как в «дашборд».
    seq_p = _vowel_pattern_from_tokens(phrase, skip_fillers=True)
    vowel_score = _vowel_pattern_similarity(seq_w, seq_p)

    content = [t for t in phrase if not _is_filler_word(t.display)]
    ipa_p = "".join(t.ipa for t in content) if content else ""
    zone = multisyllable_zone_similarity(word.ipa, ipa_p) if ipa_p else 0.0
    coda = _coda_assonance_similarity(word.ipa, phrase[-1].ipa)

    if len(phrase) > 1:
        combined = max(vowel_score, zone * 0.85, coda * 0.75)
    else:
        combined = max(vowel_score, zone, coda)
    return combined, vowel_score


def word_rhyme_similarity(ipa_a: str, ipa_b: str) -> float:
    """Фонетическая близость двух слов (хвост от ударной + зона конца)."""
    if not ipa_a or not ipa_b:
        return 0.0
    if not _stress_rhyme_compatible(ipa_a, ipa_b):
        return 0.0
    zone = multisyllable_zone_similarity(ipa_a, ipa_b)
    ta, tb = _tail_from_stress(ipa_a), _tail_from_stress(ipa_b)
    tail = 0.0
    # Короткий хвост (u, aɭ) даёт ложные 1.0 — учитываем ударение только от 3 символов.
    if len(ta) >= 3 and len(tb) >= 3:
        tail = _stressed_tail_similarity(ipa_a, ipa_b)
    coda = _coda_assonance_similarity(ipa_a, ipa_b)
    return max(zone, tail, coda)


def _common_tail_prefix(ta: str, tb: str) -> int:
    """Длина общего префикса хвостов от ударной гласной."""
    n = 0
    for ca, cb in zip(ta, tb):
        if ca == cb:
            n += 1
        else:
            break
    return n


def find_internal_cross_line_matches(blocks: list[Block]) -> list[InternalCrossLineMatch]:
    """Лучшее внутреннее созвучие между соседними строками (не по концам).

    Пример: строка 47 «…гномиков…белоснежка» ↔ строка 48 «…экономике…бережно».
    """
    lines: list[Line] = [line for block in blocks for line in block.lines]
    by_index = {line.index: line for line in lines}
    matches: list[InternalCrossLineMatch] = []

    for line_a in lines:
        line_b = by_index.get(line_a.index + 1)
        if line_b is None:
            continue

        best: InternalCrossLineMatch | None = None
        for wa in line_a.words():
            if wa.is_last_word or not _is_rhyme_candidate_word(wa):
                continue
            for wb in line_b.words():
                if wb.is_last_word or not _is_rhyme_candidate_word(wb):
                    continue
                if wa.display.lower() == wb.display.lower():
                    continue
                score = word_rhyme_similarity(wa.ipa, wb.ipa)
                if score < _INTERNAL_CROSS_LINE_THRESHOLD:
                    continue
                ta, tb = _tail_from_stress(wa.ipa), _tail_from_stress(wb.ipa)
                # гномиков|экономике: общий каркас omʲik…; слабые зональные пары отсекаем.
                if _common_tail_prefix(ta, tb) < 3 and score < 0.8:
                    continue
                match = InternalCrossLineMatch(
                    line_a=line_a,
                    line_b=line_b,
                    unit_a=wa.display,
                    unit_b=wb.display,
                    score=score,
                )
                if best is None or score > best.score:
                    best = match
        if best is not None:
            matches.append(best)
    return matches


def find_intra_line_rhyme_matches(blocks: list[Block]) -> list[IntraLineRhymeMatch]:
    """Внутренняя рифма в одной строке: слово в середине ↔ хвостовая фраза.

    Асимметричные пары 1↔2, 1↔3: «дашборд» ~ «дал в рот» по порядку гласных.
    """
    lines: list[Line] = [line for block in blocks for line in block.lines]
    matches: list[IntraLineRhymeMatch] = []

    for line in lines:
        words = line.words()
        best_for_line: IntraLineRhymeMatch | None = None

        for i, wa in enumerate(words):
            if wa.is_last_word or not _is_rhyme_candidate_word(wa):
                continue

            for n in (3, 2, 1):
                chunk = _rhyme_tail_tokens(line, n)
                if not chunk:
                    continue
                phrase_start = _phrase_chunk_start_index(words, chunk)
                if i >= phrase_start:
                    continue
                if phrase_start - i - 1 < _MIN_WORDS_BEFORE_END_RHYME:
                    continue

                score, vowel_score = internal_word_phrase_similarity(wa, chunk)
                if score < _INTERNAL_CROSS_LINE_THRESHOLD:
                    continue
                # Одно слово в конце — только при явном совпадении гласных.
                if n == 1 and vowel_score < 0.75:
                    continue
                # Многословная фраза — нужен явный паттерн гласных (а-о), не только «рот».
                if n > 1 and vowel_score < 0.7:
                    continue

                last_tok = chunk[-1]
                ta, tb = _tail_from_stress(wa.ipa), _tail_from_stress(last_tok.ipa)
                coda = _coda_assonance_similarity(wa.ipa, last_tok.ipa)
                if (
                    _common_tail_prefix(ta, tb) < 3
                    and score < 0.8
                    and coda < _CODA_ASSONANCE_MIN
                    and vowel_score < 0.7
                ):
                    continue

                unit_b = " ".join(t.display for t in chunk)
                candidate = IntraLineRhymeMatch(
                    line=line,
                    unit_a=wa.display,
                    unit_b=unit_b,
                    n_words_b=n,
                    score=score,
                )
                if best_for_line is None or score > best_for_line.score or (
                    score == best_for_line.score and n > best_for_line.n_words_b
                ):
                    best_for_line = candidate

        if best_for_line is not None:
            matches.append(best_for_line)
    return matches


def _is_filler_word(display: str) -> bool:
    """Предлог/союз/частица — не часть рифменной единицы в хвосте фразы."""
    from .yo_restore import fold_yo_for_match

    return fold_yo_for_match(display) in _RHYME_FILLERS


def _rhyme_tail_tokens(line: Line, n_words: int) -> list[Token]:
    """Последние n слов без ведущих служебных («из трущоб» → [трущоб])."""
    words = line.words()
    if not words or n_words < 1:
        return []
    chunk = words[-n_words:] if len(words) >= n_words else list(words)
    while len(chunk) > 1 and _is_filler_word(chunk[0].display):
        chunk = chunk[1:]
    return chunk


def extract_multisyllable_zone(ipa: str, vowels_from_end: int = _VOWELS_FROM_END) -> str:
    """Фонетический хвост от N-й гласной с конца (для многосложных концовок)."""
    s = _clean_ipa(ipa)
    if not s:
        return ""
    vowel_positions = [i for i, ch in enumerate(s) if ch in VOWELS]
    if not vowel_positions:
        return ""
    n = min(vowels_from_end, len(vowel_positions))
    start = vowel_positions[-n]
    return _reduce_tail(s[start:].replace(STRESS_PRIMARY, ""))


def _line_end_phrase_ipa(line: Line, n_words: int = 2) -> str:
    """IPA хвостовой фразы без служебных слов в начале."""
    chunk = _rhyme_tail_tokens(line, n_words)
    if not chunk:
        return ""
    return "".join(w.ipa for w in chunk)


def phrase_unit_text(line: Line, n_words: int) -> str:
    """Текстовая рифменная единица: хвост строки без ведущих служебных."""
    chunk = _rhyme_tail_tokens(line, n_words)
    if not chunk:
        return ""
    return " ".join(t.display for t in chunk)


def _zone_vowel_count(n_words_a: int, n_words_b: int) -> int:
    """Число гласных в сравниваемой зоне: больше для длинных асимметричных пар."""
    total = n_words_a + n_words_b
    if total <= 2:
        return _VOWELS_FROM_END
    return min(total + 2, 5)


def _zones_compatible(za: str, zb: str) -> bool:
    classes_a = {ch for ch in za if ch in "aeiouy"}
    classes_b = {ch for ch in zb if ch in "aeiouy"}
    if not classes_a or not classes_b:
        return False
    return any(_vowels_compatible(a, b) for a in classes_a for b in classes_b)


def end_zone_similarity(line_a: Line, n_words_a: int, line_b: Line, n_words_b: int) -> float:
    """Фонетическая близость концов строк: 1↔1, 2↔2, 1↔2, 1↔3 и т.д."""
    tail_a = _rhyme_tail_tokens(line_a, n_words_a)
    tail_b = _rhyme_tail_tokens(line_b, n_words_b)
    if not tail_a or not tail_b:
        return 0.0

    ipa_a = tail_a[-1].ipa if len(tail_a) == 1 else "".join(w.ipa for w in tail_a)
    ipa_b = tail_b[-1].ipa if len(tail_b) == 1 else "".join(w.ipa for w in tail_b)
    if not ipa_a or not ipa_b:
        return 0.0

    eff_a, eff_b = len(tail_a), len(tail_b)
    vowels = _zone_vowel_count(eff_a, eff_b)
    za = extract_multisyllable_zone(ipa_a, vowels)
    zb = extract_multisyllable_zone(ipa_b, vowels)
    coda = 0.0
    if eff_a == 1 and eff_b == 1:
        coda = _coda_assonance_similarity(ipa_a, ipa_b)
    if not za or not zb or not _zones_compatible(za, zb):
        return coda
    return max(SequenceMatcher(None, za, zb).ratio(), coda)


def is_rhyme_boundary(line_a: Line, line_b: Line) -> bool:
    """True, если концы соседних строк не рифмуются — схема должна разорваться.

    Пример: «найти» (…ɪ) и «колеса» (…esa) — разные окончания, хотя длинная
    фраза «Москве сук найти» даёт ложный ассонанс с «колеса».
    """
    if line_b.index != line_a.index + 1:
        return False
    words_a = line_a.words()
    words_b = line_b.words()
    if not words_a or not words_b:
        return False

    score_11 = end_zone_similarity(line_a, 1, line_b, 1)
    if score_11 >= _RHYME_BOUNDARY_11_MAX:
        return False
    if _stress_rhyme_compatible(words_a[-1].ipa, words_b[-1].ipa):
        return False
    # жесток|броук: разные ударные, но общий посыльный -ок/-ук.
    if _coda_assonance_similarity(words_a[-1].ipa, words_b[-1].ipa) >= _CODA_ASSONANCE_MIN:
        return False
    return True


def find_rhyme_boundaries(blocks: list[Block]) -> set[int]:
    """Номера строк N, после которых рифменная схема обрывается (N | N+1)."""
    lines: list[Line] = [line for block in blocks for line in block.lines]
    by_index = {line.index: line for line in lines}
    boundaries: set[int] = set()
    for line in lines:
        nxt = by_index.get(line.index + 1)
        if nxt is not None and is_rhyme_boundary(line, nxt):
            boundaries.add(line.no)
    return boundaries


def lines_share_rhyme_group(line_no_a: int, line_no_b: int, boundaries: set[int]) -> bool:
    """Разрыв схемы (N|N+1) режет только соседние строки, не skip-line через заглушку.

    Пример: границы 11|12 и 12|13 не мешают рифме 11↔13 (распятого — богатыми).
    """
    lo, hi = min(line_no_a, line_no_b), max(line_no_a, line_no_b)
    if hi - lo == 1:
        return lo not in boundaries
    return True


def _tail_from_stress(ipa: str) -> str:
    """Фонетический хвост от ударной гласной до конца слова."""
    if not ipa:
        return ""
    s = _clean_ipa(ipa)
    if STRESS_PRIMARY in ipa:
        idx = ipa.index(STRESS_PRIMARY)
        # С ударной гласной (символ ˈ стоит перед ней).
        tail = s[idx:]
    else:
        vowel_positions = [i for i, ch in enumerate(s) if ch in VOWELS]
        if not vowel_positions:
            return ""
        tail = s[vowel_positions[-1] :]
    return _reduce_tail(tail.replace(STRESS_PRIMARY, ""))


def _stressed_tail_similarity(ipa_a: str, ipa_b: str) -> float:
    """Похожесть хвостов от ударной гласной (распЯтого ~ богАтыми: …ат…)."""
    ta = _tail_from_stress(ipa_a)
    tb = _tail_from_stress(ipa_b)
    if not ta or not tb:
        return 0.0
    if not _stress_rhyme_compatible(ipa_a, ipa_b):
        return 0.0

    ratio = SequenceMatcher(None, ta, tb).ratio()
    # Общий каркас от ударной: «ат…» в распятого / богатыми.
    common = 0
    for ca, cb in zip(ta, tb):
        if ca == cb:
            common += 1
        else:
            break
    if common >= 2:
        ratio = max(ratio, min(1.0, ratio + 0.15))
    return ratio


def best_adjacent_match(line_a: Line, line_b: Line) -> AdjacentPhraseMatch | None:
    """Лучшее созвучие концов соседних строк (включая асимметричные окна)."""
    if line_b.index != line_a.index + 1:
        return None
    # Разрыв схемы: не связываем куплет 1–4 с 5–8 из-за ложной 3↔1 фразы.
    if is_rhyme_boundary(line_a, line_b):
        return None

    best: AdjacentPhraseMatch | None = None
    for n_a, n_b in _ADJACENT_WINDOWS:
        tail_a = _rhyme_tail_tokens(line_a, n_a)
        tail_b = _rhyme_tail_tokens(line_b, n_b)
        if not tail_a or not tail_b:
            continue
        eff_a, eff_b = len(tail_a), len(tail_b)
        score = end_zone_similarity(line_a, n_a, line_b, n_b)
        if score < CONSECUTIVE_PHRASE_THRESHOLD:
            continue
        match = AdjacentPhraseMatch(
            line_a=line_a,
            line_b=line_b,
            unit_a=phrase_unit_text(line_a, n_a),
            unit_b=phrase_unit_text(line_b, n_b),
            n_words_a=eff_a,
            n_words_b=eff_b,
            score=score,
        )
        if best is None or score > best.score:
            best = match
    return best


def multisyllable_zone_similarity(ipa_a: str, ipa_b: str) -> float:
    """Похожесть многосложных концов по зоне последних гласных."""
    za = extract_multisyllable_zone(ipa_a, _VOWELS_FROM_END)
    zb = extract_multisyllable_zone(ipa_b, _VOWELS_FROM_END)
    if not za or not zb:
        return 0.0
    # Хотя бы одна общая гласная в зоне (и/ы совместимы).
    classes_a = {ch for ch in za if ch in "aeiouy"}
    classes_b = {ch for ch in zb if ch in "aeiouy"}
    if not classes_a or not classes_b:
        return 0.0
    if not any(_vowels_compatible(a, b) for a in classes_a for b in classes_b):
        return 0.0
    return SequenceMatcher(None, za, zb).ratio()


def consecutive_phrase_similarity(line_a: Line, line_b: Line) -> float:
    """Созвучие концовок соседних строк (симметричные и асимметричные окна)."""
    match = best_adjacent_match(line_a, line_b)
    return match.score if match else 0.0


def find_adjacent_phrase_matches(blocks: list[Block]) -> list[AdjacentPhraseMatch]:
    """Соседние строки с похожими концовками и конкретными unit для разметки."""
    lines: list[Line] = [line for block in blocks for line in block.lines]
    by_index = {line.index: line for line in lines}
    matches: list[AdjacentPhraseMatch] = []

    for line in lines:
        nxt = by_index.get(line.index + 1)
        if nxt is None:
            continue
        match = best_adjacent_match(line, nxt)
        if match is not None:
            matches.append(match)
    return matches


def find_adjacent_phrase_pairs(blocks: list[Block]) -> list[tuple[Line, Line, float]]:
    """Пары соседних строк с похожими концовками (совместимость со старым API)."""
    return [(m.line_a, m.line_b, m.score) for m in find_adjacent_phrase_matches(blocks)]


def skip_line_similarity(line_a: Line, line_b: Line) -> float:
    """Оценка рифмы концов двух строк через одну заглушку."""
    words_a = line_a.words()
    words_b = line_b.words()
    if not words_a or not words_b:
        return 0.0

    last_a, last_b = words_a[-1], words_b[-1]
    coda = _coda_assonance_similarity(last_a.ipa, last_b.ipa)
    if not _stress_rhyme_compatible(last_a.ipa, last_b.ipa):
        return coda

    score = max(
        multisyllable_zone_similarity(last_a.ipa, last_b.ipa),
        _stressed_tail_similarity(last_a.ipa, last_b.ipa),
        coda,
    )

    # Фраза в хвосте строки (2 слова) иногда лучше ловит «кашей манной».
    if len(words_a) >= 2:
        phrase_a = _line_end_phrase_ipa(line_a, 2)
        za = extract_multisyllable_zone(phrase_a, _PHRASE_VOWELS_FROM_END)
        zb = extract_multisyllable_zone(last_b.ipa, _VOWELS_FROM_END)
        if za and zb:
            phrase_score = SequenceMatcher(None, za, zb).ratio()
            score = max(score, phrase_score)

    return score


def find_skip_line_pairs(blocks: list[Block]) -> list[tuple[Line, Line, float]]:
    """Пары строк (i, i+2) с похожими концами — кандидаты на рифму через заглушку."""
    lines: list[Line] = [line for block in blocks for line in block.lines]
    by_index = {line.index: line for line in lines}
    pairs: list[tuple[Line, Line, float]] = []

    for line in lines:
        partner = by_index.get(line.index + SKIP_LINE_GAP)
        if partner is None:
            continue
        score = skip_line_similarity(line, partner)
        if score >= _SKIP_LINE_THRESHOLD:
            pairs.append((line, partner, score))

    return pairs


def skip_line_hints(blocks: list[Block]) -> list[str]:
    """Текстовые подсказки для LLM-промпта."""
    hints: list[str] = []
    for match in find_adjacent_phrase_matches(blocks):
        if match.asymmetric:
            label = f"{match.n_words_a} слово ↔ {match.n_words_b}"
            hints.append(
                f"строка {match.line_a.no} «{match.unit_a}» ↔ "
                f"строка {match.line_b.no} «{match.unit_b}» "
                f"(соседние, {label}, ассонанс {match.score:.0%}; "
                f"запятая между словами может не быть паузой) — одна цепочка"
            )
        else:
            hints.append(
                f"строка {match.line_a.no} «…{match.unit_a}» ↔ "
                f"строка {match.line_b.no} «…{match.unit_b}» "
                f"(соседние концовки, ассонанс {match.score:.0%}) — включи в одну цепочку"
            )
    for line_a, line_b, score in find_skip_line_pairs(blocks):
        end_a = phrase_unit_text(line_a, 2) if len(line_a.words()) >= 2 else line_a.words()[-1].display
        end_b = line_b.words()[-1].display
        hints.append(
            f"строка {line_a.no} «…{end_a}» ↔ строка {line_b.no} «{end_b}» "
            f"(через заглушку, фон. {score:.0%})"
        )
    for match in find_internal_cross_line_matches(blocks):
        hints.append(
            f"строка {match.line_a.no} «{match.unit_a}» ↔ "
            f"строка {match.line_b.no} «{match.unit_b}» "
            f"(внутренняя между строками, фон. {match.score:.0%}) — одна цепочка"
        )
    for match in find_intra_line_rhyme_matches(blocks):
        hints.append(
            f"строка {match.line.no} «{match.unit_a}» ↔ «{match.unit_b}» "
            f"(внутренняя в строке, фон. {match.score:.0%}) — одна цепочка"
        )
    return hints


def last_word_tokens(blocks: list[Block]) -> dict[int, Token]:
    """Последнее слово каждой строки по line.index."""
    result: dict[int, Token] = {}
    for block in blocks:
        for line in block.lines:
            words = line.words()
            if words:
                result[line.index] = words[-1]
    return result
