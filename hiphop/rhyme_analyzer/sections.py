"""Распознавание секций песни (куплет, припев, hook…) на разных языках.

Поддерживаются маркеры в скобках ([Verse 1], [Припев], [Coro]) и отдельные
строки-заголовки (Chorus:, Куплет 2, Hook — без скобок).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- Заголовок в квадратных скобках: [Verse 1], [Припев], [Coro] ---
BRACKET_SECTION_RE = re.compile(r"^\s*\[(?P<title>[^\]]+)\]\s*$")

# Ключевые слова заголовков (EN / RU / ES и типичные выгрузки Genius).
_STANDALONE_WORDS = (
    "post-chorus",
    "pre-chorus",
    "instrumental",
    "interlude",
    "introducción",
    "introduccion",
    "estribillo",
    "transition",
    "transición",
    "transicion",
    "prologue",
    "epilogue",
    "instrumental",
    "refrain",
    "bridge",
    "chorus",
    "куплет",
    "припев",
    "проигрыш",
    "рефрен",
    "бридж",
    "estrofa",
    "intro",
    "outro",
    "interlude",
    "skit",
    "verse",
    "vers",
    "hook",
    "coro",
    "puente",
    "verso",
    "интро",
    "аутро",
)

# Длинные фразы первыми, чтобы «pre-chorus» не резался как «chorus».
_STANDALONE_ALT = "|".join(
    re.escape(w) for w in sorted(set(_STANDALONE_WORDS), key=len, reverse=True)
)

STANDALONE_SECTION_RE = re.compile(
    rf"^\s*(?:#{{1,3}}\s*)?(?:[-–—*]\s*)?"
    rf"(?P<label>{_STANDALONE_ALT})"
    rf"(?:\s*(?P<num>\d+))?"
    rf"\s*:?\s*(?:[-–—*]\s*)?$",
    re.IGNORECASE | re.UNICODE,
)


@dataclass(frozen=True)
class SectionHeader:
    """Распознанный заголовок секции."""

    title: str  # как показывать в HTML (Verse 1, Припев, …)
    kind: str  # verse | chorus | hook | bridge | intro | outro | other
    raw: str  # исходная строка


def _kind_from_text(text: str) -> str:
    """Определяет тип секции по ключевым словам (мультиязычно)."""
    t = text.lower().replace("ё", "е")

    if re.search(r"\boutro\b|\bаутро\b", t):
        return "outro"
    if re.search(
        r"\b(intro|interlude|skit|instrumental|prologue|epilogue|"
        r"интро|проигрыш|introduccion|introducción)\b",
        t,
    ):
        return "intro"

    if re.search(r"\bhook\b", t):
        return "hook"
    if re.search(
        r"\b(chorus|refrain|post[- ]?chorus|pre[- ]?chorus|"
        r"припев|рефрен|coro|estribillo)\b",
        t,
    ):
        return "chorus"

    if re.search(r"\b(verse|vers|v\.|куplet|куплет|strofa|estrofa|verso)\b", t):
        return "verse"

    if re.search(r"\b(bridge|бридж|puente|transicion|transition|transición)\b", t):
        return "bridge"

    return "other"


def _format_standalone_title(label: str, num: str | None) -> str:
    """Красивый заголовок из standalone-метки."""
    label = label.strip()
    if re.match(r"^[a-zA-Z]", label):
        label = label[0].upper() + label[1:].lower()
    if num:
        return f"{label} {num}"
    return label


def parse_section_header(line: str) -> SectionHeader | None:
    """Если строка — заголовок секции, возвращает SectionHeader; иначе None."""
    stripped = line.strip()
    if not stripped:
        return None

    m = BRACKET_SECTION_RE.match(stripped)
    if m:
        title = m.group("title").strip()
        return SectionHeader(title=title, kind=_kind_from_text(title), raw=stripped)

    m = STANDALONE_SECTION_RE.match(stripped)
    if m:
        title = _format_standalone_title(m.group("label"), m.group("num"))
        return SectionHeader(title=title, kind=_kind_from_text(title), raw=stripped)

    return None
