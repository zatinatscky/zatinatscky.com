"""Пути выходных файлов: slug из названия песни."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def slugify(name: str, *, max_len: int = 80) -> str:
    """Безопасное имя файла из названия песни."""
    s = name.strip()
    if not s:
        return "song"
    # Пробелы и пунктуация → дефис; буквы/цифры любых алфавитов сохраняем.
    s = re.sub(r"[^\w\s\-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    s = re.sub(r"-+", "-", s)
    return (s[:max_len].strip("-") or "song")


def versioned_path(base: Path, generated_at: datetime) -> Path:
    """stem-YYYYMMDD-HHMMSS.ext рядом с base."""
    stamp = generated_at.astimezone().strftime("%Y%m%d-%H%M%S")
    return base.parent / f"{base.stem}-{stamp}{base.suffix or '.html'}"


def default_html_output(
    song: str,
    *,
    output_dir: Path,
    generated_at: datetime,
    versioned: bool = True,
) -> Path:
    """Путь HTML по умолчанию: output/<slug>-<timestamp>.html."""
    base = output_dir / f"{slugify(song)}.html"
    if versioned:
        return versioned_path(base, generated_at)
    return base
