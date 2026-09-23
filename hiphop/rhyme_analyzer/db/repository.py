"""CRUD-операции: тексты, прогоны, запросы, логи, события, сессии."""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..from_blocks import BlockSubmission
from ..journal import JournalEntry, normalize_input_text, text_hash, text_preview
from .models import (
    ActivityLog,
    AnalysisRequest,
    AnalysisRun,
    SongText,
    TextBlock,
    UserEvent,
    VisitorSession,
)

# Поля формы, которые не пишем в request_body (PII / объём).
_SENSITIVE_BODY_KEYS = frozenset({"api_key", "openai_api_key", "deepseek_api_key"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _count_stats(norm_text: str, blocks: list[BlockSubmission]) -> tuple[int, int, int, int]:
    """block_count, line_count, word_count, char_count."""
    lines = [ln for ln in norm_text.splitlines() if ln.strip()]
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+(?:[''ʼ][A-Za-zА-Яа-яЁё0-9]+)?", norm_text)
    return len(blocks), len(lines), len(words), len(norm_text)


def sanitize_request_body(body: dict[str, Any] | None) -> dict[str, Any] | None:
    """Убирает секреты; для блоков текста сохраняем только метаданные."""
    if not body:
        return None
    out: dict[str, Any] = {}
    for key, val in body.items():
        if key in _SENSITIVE_BODY_KEYS:
            continue
        if key == "blocks" and isinstance(val, list):
            out["blocks"] = [
                {
                    "kind": b.get("kind") if isinstance(b, dict) else getattr(b, "kind", ""),
                    "title": b.get("title") if isinstance(b, dict) else getattr(b, "title", None),
                    "char_count": len(str(b.get("text", "") if isinstance(b, dict) else getattr(b, "text", ""))),
                    "line_count": len(
                        [
                            ln
                            for ln in str(b.get("text", "") if isinstance(b, dict) else getattr(b, "text", "")).splitlines()
                            if ln.strip()
                        ]
                    ),
                }
                for b in val
            ]
        else:
            out[key] = val
    return out


# --- Сессии ---


def get_or_create_session(
    db: Session,
    *,
    token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> VisitorSession:
    """Находит сессию по cookie-токену или создаёт новую."""
    row = db.scalar(select(VisitorSession).where(VisitorSession.token == token))
    if row:
        row.last_seen_at = _utcnow()
        if ip_address:
            row.ip_address = ip_address
        if user_agent:
            row.user_agent = user_agent
        return row

    row = VisitorSession(
        id=str(uuid.uuid4()),
        token=token,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(row)
    db.flush()
    return row


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


# --- Тексты ---


def upsert_text(
    db: Session,
    *,
    blocks: list[BlockSubmission],
    lang: str | None = None,
) -> SongText:
    """Создаёт или обновляет канонический текст и его блоки."""
    norm = normalize_input_text(blocks)
    th = text_hash(norm)
    stats = _count_stats(norm, blocks)

    row = db.scalar(select(SongText).where(SongText.text_hash == th).options(selectinload(SongText.blocks)))
    if row is None:
        row = SongText(
            id=str(uuid.uuid4()),
            text_hash=th,
            normalized_text=norm,
            preview=text_preview(norm),
            lang=lang,
            block_count=stats[0],
            line_count=stats[1],
            word_count=stats[2],
            char_count=stats[3],
        )
        db.add(row)
        db.flush()
    else:
        row.last_seen_at = _utcnow()
        row.preview = text_preview(norm)
        if lang:
            row.lang = lang
        row.block_count, row.line_count, row.word_count, row.char_count = stats
        # Перезаписываем блоки при изменении структуры.
        row.blocks.clear()
        db.flush()

    for i, block in enumerate(blocks):
        if not block.text.strip():
            continue
        row.blocks.append(
            TextBlock(
                ordinal=i,
                kind=block.kind,
                title=block.title,
                raw_text=block.text,
            )
        )
    db.flush()
    return row


def text_blocks_as_dicts(text_row: SongText) -> list[dict[str, Any]]:
    """Блоки текста для API /api/journal/{id}/input."""
    ordered = sorted(text_row.blocks, key=lambda b: b.ordinal)
    return [{"kind": b.kind, "title": b.title, "text": b.raw_text} for b in ordered]


# --- Прогоны анализа (журнал) ---


def new_run_id() -> str:
    return secrets.token_hex(4)


def create_run_pending(
    db: Session,
    *,
    run_id: str,
    text_row: SongText,
    song: str,
    lang: str,
    model: str,
    session_id: str | None = None,
    parent_run_id: str | None = None,
    source: str = "web-form",
    dual_mode: bool = False,
    model_secondary: str | None = None,
) -> AnalysisRun:
    """Создаёт запись прогона со статусом running (до завершения пайплайна)."""
    run = AnalysisRun(
        id=run_id,
        text_id=text_row.id,
        session_id=session_id,
        parent_run_id=parent_run_id,
        song=song.strip(),
        lang=lang,
        model=model,
        model_secondary=model_secondary,
        dual_mode=dual_mode,
        source=source,
        status="running",
    )
    db.add(run)
    db.flush()
    return run


def complete_run(
    db: Session,
    run: AnalysisRun,
    *,
    report: dict[str, Any],
    meta: dict[str, Any],
    duration_ms: int | None = None,
) -> AnalysisRun:
    """Заполняет отчёт и метрики после успешного анализа."""
    run.status = "done"
    run.report_json = report
    run.meta_json = meta
    run.blocks = int(meta.get("blocks", 0))
    run.lines = int(meta.get("lines", 0))
    run.chains = int(meta.get("chains", 0))
    run.completed_at = _utcnow()
    run.duration_ms = duration_ms
    db.flush()
    return run


def fail_run(
    db: Session,
    run: AnalysisRun,
    *,
    error_kind: str,
    errors: list[str],
    duration_ms: int | None = None,
) -> None:
    run.status = "failed"
    run.error_kind = error_kind
    run.errors_json = errors
    run.completed_at = _utcnow()
    run.duration_ms = duration_ms
    db.flush()


def run_to_journal_entry(run: AnalysisRun, text_row: SongText) -> JournalEntry:
    """ORM → dataclass для совместимости с entry_to_api()."""
    created = run.created_at.astimezone().isoformat(timespec="seconds")
    return JournalEntry(
        id=run.id,
        song=run.song,
        created_at=created,
        model=run.model,
        lang=run.lang,
        blocks=run.blocks,
        lines=run.lines,
        chains=run.chains,
        text_hash=text_row.text_hash,
        text_preview=text_row.preview,
        report=f"db://{run.id}",
        report_format="json",
    )


def list_runs(db: Session, *, limit: int = 100) -> list[tuple[AnalysisRun, SongText]]:
    stmt = (
        select(AnalysisRun, SongText)
        .join(SongText, AnalysisRun.text_id == SongText.id)
        .order_by(AnalysisRun.created_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).all())


def get_run(db: Session, run_id: str) -> tuple[AnalysisRun, SongText] | None:
    run_id = run_id.strip().lower()
    stmt = (
        select(AnalysisRun, SongText)
        .join(SongText, AnalysisRun.text_id == SongText.id)
        .where(AnalysisRun.id == run_id)
    )
    row = db.execute(stmt).first()
    return row if row else None


def find_runs_by_text(db: Session, blocks: list[BlockSubmission]) -> list[tuple[AnalysisRun, SongText]]:
    norm = normalize_input_text(blocks)
    if not norm:
        return []
    th = text_hash(norm)
    stmt = (
        select(AnalysisRun, SongText)
        .join(SongText, AnalysisRun.text_id == SongText.id)
        .where(SongText.text_hash == th, AnalysisRun.status == "done")
        .order_by(AnalysisRun.created_at.desc())
    )
    return list(db.execute(stmt).all())


def delete_run(db: Session, run_id: str) -> bool:
    run_id = run_id.strip().lower()
    run = db.get(AnalysisRun, run_id)
    if run is None:
        return False
    db.delete(run)
    db.flush()
    return True


def rename_run(db: Session, run_id: str, song: str) -> tuple[AnalysisRun, SongText] | None:
    pair = get_run(db, run_id)
    if pair is None:
        return None
    run, _text = pair
    new_song = song.strip()
    if not new_song:
        return None
    run.song = new_song
    if run.report_json and isinstance(run.report_json, dict):
        run.report_json = {**run.report_json, "song": new_song}
    db.flush()
    return get_run(db, run_id)


# --- Запросы ---


def log_request(
    db: Session,
    *,
    request_type: str,
    method: str,
    path: str,
    session_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_body: dict[str, Any] | None = None,
    response_status: int | None = None,
    response_summary: dict[str, Any] | None = None,
    duration_ms: int | None = None,
    estimated_cost_usd: float | None = None,
    analysis_run_id: str | None = None,
) -> AnalysisRequest:
    row = AnalysisRequest(
        id=str(uuid.uuid4()),
        session_id=session_id,
        analysis_run_id=analysis_run_id,
        request_type=request_type,
        method=method,
        path=path,
        ip_address=ip_address,
        user_agent=user_agent,
        request_body=sanitize_request_body(request_body),
        response_status=response_status,
        response_summary=response_summary,
        duration_ms=duration_ms,
        estimated_cost_usd=estimated_cost_usd,
    )
    db.add(row)
    db.flush()
    return row


def attach_run_to_request(db: Session, request_id: str, run_id: str) -> None:
    row = db.get(AnalysisRequest, request_id)
    if row:
        row.analysis_run_id = run_id
        db.flush()


# --- Activity logs ---


def log_activity(
    db: Session,
    *,
    message: str,
    level: str = "info",
    category: str = "pipeline",
    stage: str | None = None,
    payload: dict[str, Any] | None = None,
    session_id: str | None = None,
    analysis_run_id: str | None = None,
    request_id: str | None = None,
) -> None:
    db.add(
        ActivityLog(
            session_id=session_id,
            analysis_run_id=analysis_run_id,
            request_id=request_id,
            level=level,
            category=category,
            stage=stage,
            message=message,
            payload=payload,
        )
    )
    db.flush()


# --- User events ---


def record_user_events(
    db: Session,
    *,
    session_id: str | None,
    events: list[dict[str, Any]],
) -> int:
    """Пакетная запись событий из фронтенда. Возвращает число записанных."""
    count = 0
    for ev in events:
        name = str(ev.get("event_name") or ev.get("name") or "").strip()
        if not name:
            continue
        db.add(
            UserEvent(
                session_id=session_id,
                event_name=name[:64],
                properties=ev.get("properties") if isinstance(ev.get("properties"), dict) else None,
                page_path=str(ev.get("page_path") or "/")[:256],
            )
        )
        count += 1
    db.flush()
    return count
