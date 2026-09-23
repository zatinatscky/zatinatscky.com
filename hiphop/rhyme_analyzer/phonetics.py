"""G2P: перевод нормализованных слов в IPA с ударениями.

Основной движок — phonemizer поверх системного espeak-ng (точный, с ударениями,
поддерживает много языков). Если espeak-ng не установлен, включается приблизительный
fallback на правилах (результат помечается как ненадёжный — см. README).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from .models import Block

# Типичные пути к libespeak-ng (на macOS phonemizer не находит её сам).
_ESPEAK_LIB_CANDIDATES = [
    "/opt/homebrew/lib/libespeak-ng.dylib",  # Homebrew, Apple Silicon
    "/usr/local/lib/libespeak-ng.dylib",  # Homebrew, Intel
    "/opt/homebrew/lib/libespeak-ng.1.dylib",
]
_espeak_configured = False


def _configure_espeak_library() -> None:
    """Подсказывает phonemizer, где лежит libespeak-ng (иначе на macOS не находит)."""
    global _espeak_configured
    if _espeak_configured:
        return
    _espeak_configured = True
    if os.environ.get("PHONEMIZER_ESPEAK_LIBRARY"):
        return  # пользователь задал путь явно
    try:
        from phonemizer.backend.espeak.wrapper import EspeakWrapper
    except Exception:
        return
    for cand in _ESPEAK_LIB_CANDIDATES:
        if Path(cand).exists():
            try:
                EspeakWrapper.set_library(cand)
            except Exception:
                pass
            return

# Множество гласных IPA (нужно и движку, и детектору рифм).
VOWELS = set("aeiouɨəɐɛʊɪʉyœøɞʌɑɒæ")
STRESS_PRIMARY = "ˈ"
STRESS_SECONDARY = "ˌ"


class EspeakTranscriber:
    """Точная транскрипция через phonemizer + espeak-ng."""

    language = "ru"

    def __init__(self, language: str = "ru") -> None:
        _configure_espeak_library()
        from phonemizer.backend import EspeakBackend  # ленивый импорт

        self.language = language
        self.backend = EspeakBackend(language, with_stress=True, language_switch="remove-flags")

    @staticmethod
    def available(language: str = "ru") -> bool:
        try:
            _configure_espeak_library()
            from phonemizer.backend import EspeakBackend

            return EspeakBackend.is_available()
        except Exception:
            return False

    def transcribe(self, words: list[str]) -> list[str]:
        from phonemizer.separator import Separator

        if not words:
            return []
        out = self.backend.phonemize(words, separator=Separator(phone="", word=" "), strip=True)
        return [w.strip() for w in out]


# --- Fallback на правилах (без espeak) ---------------------------------------

_CYR_TO_IPA = {
    "а": "a", "о": "o", "у": "u", "ы": "ɨ", "э": "ɛ", "и": "i",
    "я": "ja", "ю": "ju", "е": "je", "ё": "jo",
    "б": "b", "в": "v", "г": "ɡ", "д": "d", "ж": "ʐ", "з": "z", "й": "j",
    "к": "k", "л": "l", "м": "m", "н": "n", "п": "p", "р": "r", "с": "s",
    "т": "t", "ф": "f", "х": "x", "ц": "ts", "ч": "tɕ", "ш": "ʂ", "щ": "ɕ",
    "ь": "ʲ", "ъ": "",
}
# Оглушение звонких согласных на конце слова.
_FINAL_DEVOICE = {"b": "p", "v": "f", "ɡ": "k", "d": "t", "ʐ": "ʂ", "z": "s"}


class FallbackTranscriber:
    """Грубая транскрипция по правилам. Ударение ставится эвристически
    (на последнюю гласную) — для точного разбора нужен espeak-ng."""

    language = "ru"

    def __init__(self, language: str = "ru") -> None:
        self.language = language

    @staticmethod
    def available(language: str = "ru") -> bool:
        return True

    def _word_to_ipa(self, word: str) -> str:
        ipa = "".join(_CYR_TO_IPA.get(ch, ch) for ch in word.lower())
        # Оглушение последнего согласного.
        if ipa and ipa[-1] in _FINAL_DEVOICE:
            ipa = ipa[:-1] + _FINAL_DEVOICE[ipa[-1]]
        # Эвристическое ударение перед последней гласной.
        idxs = [i for i, c in enumerate(ipa) if c in VOWELS]
        if idxs:
            last = idxs[-1]
            # сдвигаемся к началу слога (перед предшествующими согласными)
            start = last
            while start - 1 >= 0 and ipa[start - 1] not in VOWELS and ipa[start - 1] != STRESS_PRIMARY:
                start -= 1
            ipa = ipa[:start] + STRESS_PRIMARY + ipa[start:]
        return ipa

    def transcribe(self, words: list[str]) -> list[str]:
        return [self._word_to_ipa(w) for w in words]


def get_transcriber(language: str = "ru", force_fallback: bool = False):
    """Выбирает движок: espeak-ng если доступен, иначе fallback (с предупреждением)."""
    if not force_fallback and EspeakTranscriber.available(language):
        return EspeakTranscriber(language)
    if not force_fallback:
        print(
            "[warn] espeak-ng не найден — включён приблизительный режим (рифмы могут быть неточными).\n"
            "       Для точности установите espeak-ng (см. README) и повторите.",
            file=sys.stderr,
        )
    return FallbackTranscriber(language)


def transcribe_blocks(blocks: list[Block], transcriber) -> None:
    """Проставляет .ipa всем словам. Транскрибируем одним батчем ради скорости."""
    words: list = []  # ссылки на токены
    norms: list[str] = []
    for block in blocks:
        for line in block.lines:
            for tok in line.tokens:
                if tok.is_word:
                    words.append(tok)
                    norms.append(tok.norm or tok.display)

    ipas = transcriber.transcribe(norms)
    for tok, ipa in zip(words, ipas):
        tok.ipa = ipa
