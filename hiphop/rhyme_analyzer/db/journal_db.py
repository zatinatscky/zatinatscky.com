"""Журнал разборов в PostgreSQL / SQLite (замена output/journal/ при включённой БД)."""

from __future__ import annotations

from typing import Any

from ..from_blocks import BlockSubmission
from ..journal import JournalEntry, entry_to_api, normalize_input_text, text_hash, text_preview
from .config import database_enabled
from .models import AnalysisRun
from .repository import (
    complete_run,
    create_run_pending,
    delete_run,
    fail_run,
    find_runs_by_text,
    get_run,
    list_runs,
    new_run_id,
    rename_run,
    run_to_journal_entry,
    text_blocks_as_dicts,
    upsert_text,
)
from .session import session_scope


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
) -> str:
    """Создаёт прогон со статусом running; возвращает run_id (8 hex)."""
    rid = new_run_id()
    with session_scope() as db:
        text_row = upsert_text(db, blocks=blocks, lang=lang)
        create_run_pending(
            db,
            run_id=rid,
            text_row=text_row,
            song=song,
            lang=lang,
            model=model,
            session_id=session_id,
            parent_run_id=parent_run_id,
            source=source,
            dual_mode=dual_mode,
            model_secondary=model_secondary,
        )
    return rid


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
    """Завершает прогон (или создаёт новый, если run_id не передан)."""
    rid = run_id or new_run_id()
    model = str(meta.get("model", ""))

    with session_scope() as db:
        text_row = upsert_text(db, blocks=blocks, lang=lang)
        run = db.get(AnalysisRun, rid)
        if run is None:
            run = create_run_pending(
                db,
                run_id=rid,
                text_row=text_row,
                song=song,
                lang=lang,
                model=model,
                session_id=session_id,
                parent_run_id=parent_run_id,
                source=source,
                dual_mode=dual_mode,
                model_secondary=model_secondary,
            )
        complete_run(db, run, report=report, meta=meta, duration_ms=duration_ms)
        return run_to_journal_entry(run, text_row)


def mark_run_failed(
    *,
    run_id: str,
    error_kind: str,
    errors: list[str],
    duration_ms: int | None = None,
) -> None:
    """Помечает прогон failed (если begin_run уже был вызван)."""
    with session_scope() as db:
        run = db.get(AnalysisRun, run_id)
        if run is None:
            return
        fail_run(db, run, error_kind=error_kind, errors=errors, duration_ms=duration_ms)


def list_entries(*, limit: int = 100) -> list[JournalEntry]:
    with session_scope() as db:
        pairs = list_runs(db, limit=limit)
        return [run_to_journal_entry(run, text) for run, text in pairs]


def get_entry(entry_id: str) -> JournalEntry | None:
    with session_scope() as db:
        pair = get_run(db, entry_id)
        if pair is None:
            return None
        run, text = pair
        return run_to_journal_entry(run, text)


def delete_entry(entry_id: str) -> bool:
    with session_scope() as db:
        return delete_run(db, entry_id)


def rename_entry(entry_id: str, song: str) -> JournalEntry | None:
    with session_scope() as db:
        pair = rename_run(db, entry_id, song)
        if pair is None:
            return None
        run, text = pair
        return run_to_journal_entry(run, text)


def find_by_text(blocks: list[BlockSubmission]) -> list[JournalEntry]:
    with session_scope() as db:
        pairs = find_runs_by_text(db, blocks)
        return [run_to_journal_entry(run, text) for run, text in pairs]


def has_input_snapshot(entry_id: str) -> bool:
    with session_scope() as db:
        pair = get_run(db, entry_id)
        if pair is None:
            return False
        _run, text = pair
        return bool(text.blocks)


def load_input_snapshot(entry_id: str) -> dict[str, Any] | None:
    with session_scope() as db:
        pair = get_run(db, entry_id)
        if pair is None:
            return None
        run, text = pair
        blocks = text_blocks_as_dicts(text)
        if not blocks:
            return None
        return {
            "entry_id": run.id,
            "song": run.song,
            "lang": run.lang,
            "model": run.model,
            "blocks": blocks,
        }


def load_report_data(entry: JournalEntry) -> dict[str, Any]:
    with session_scope() as db:
        pair = get_run(db, entry.id)
        if pair is None:
            raise FileNotFoundError("запись не найдена")
        run, _text = pair
        if run.report_json is None:
            raise FileNotFoundError("отчёт не найден")
        return run.report_json


def entry_to_api_db(entry: JournalEntry) -> dict[str, Any]:
    """API-обёртка — те же URL, что у файлового журнала."""
    return entry_to_api(entry)
