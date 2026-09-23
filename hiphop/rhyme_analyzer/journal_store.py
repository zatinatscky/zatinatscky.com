"""Единый фасад журнала: БД (по умолчанию) или файлы (DISABLE_DATABASE=1)."""

from __future__ import annotations

from typing import Any

from .from_blocks import BlockSubmission
from .journal import JournalEntry, entry_to_api as _file_entry_to_api
from .db.config import database_enabled

if database_enabled():
    from .db import journal_db as _backend
else:
    from . import journal as _backend  # type: ignore[no-redef]


def is_db_journal() -> bool:
    return database_enabled()


def begin_run(
    *,
    song: str,
    lang: str,
    blocks: list[BlockSubmission],
    model: str,
    session_id: str | None = None,
    parent_run_id: str | None = None,
    source: str = "web-form",
    dual_mode: bool = False,
    model_secondary: str | None = None,
) -> str | None:
    if not database_enabled():
        return None
    return _backend.begin_run(
        song=song,
        lang=lang,
        blocks=blocks,
        model=model,
        session_id=session_id,
        parent_run_id=parent_run_id,
        source=source,
        dual_mode=dual_mode,
        model_secondary=model_secondary,
    )


def mark_run_failed(
    *,
    run_id: str,
    error_kind: str,
    errors: list[str],
    duration_ms: int | None = None,
) -> None:
    if database_enabled():
        _backend.mark_run_failed(
            run_id=run_id,
            error_kind=error_kind,
            errors=errors,
            duration_ms=duration_ms,
        )


def save_run(
    *,
    song: str,
    lang: str,
    blocks: list[BlockSubmission],
    report: dict[str, Any],
    meta: dict[str, Any],
    session_id: str | None = None,
    parent_run_id: str | None = None,
    source: str = "web-form",
    run_id: str | None = None,
    dual_mode: bool = False,
    model_secondary: str | None = None,
    duration_ms: int | None = None,
) -> JournalEntry:
    kwargs: dict[str, Any] = {
        "song": song,
        "lang": lang,
        "blocks": blocks,
        "report": report,
        "meta": meta,
    }
    if database_enabled():
        kwargs.update(
            session_id=session_id,
            parent_run_id=parent_run_id,
            source=source,
            run_id=run_id,
            dual_mode=dual_mode,
            model_secondary=model_secondary,
            duration_ms=duration_ms,
        )
    return _backend.save_run(**kwargs)


def list_entries(*, limit: int = 100) -> list[JournalEntry]:
    return _backend.list_entries(limit=limit)


def get_entry(entry_id: str) -> JournalEntry | None:
    return _backend.get_entry(entry_id)


def delete_entry(entry_id: str) -> bool:
    return _backend.delete_entry(entry_id)


def rename_entry(entry_id: str, song: str) -> JournalEntry | None:
    return _backend.rename_entry(entry_id, song)


def find_by_text(blocks: list[BlockSubmission]) -> list[JournalEntry]:
    return _backend.find_by_text(blocks)


def has_input_snapshot(entry_id: str) -> bool:
    return _backend.has_input_snapshot(entry_id)


def load_input_snapshot(entry_id: str) -> dict[str, Any] | None:
    return _backend.load_input_snapshot(entry_id)


def load_report_data(entry: JournalEntry) -> dict[str, Any]:
    return _backend.load_report_data(entry)


def report_path(entry: JournalEntry):
    """Legacy: путь к HTML-файлу (только файловый журнал)."""
    if database_enabled():
        raise ValueError("отчёт хранится в БД, используйте load_report_data")
    from .journal import report_path as file_report_path

    return file_report_path(entry)


def entry_to_api(entry: JournalEntry) -> dict[str, Any]:
    """Сериализация записи для API; can_rerun — через активный бэкенд (БД или файлы)."""
    data = _file_entry_to_api(entry)
    # Файловый entry_to_api ищет снимок в output/journal/inputs/ — при БД там пусто.
    data["can_rerun"] = has_input_snapshot(entry.id)
    return data
