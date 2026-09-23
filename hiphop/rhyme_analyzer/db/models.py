"""ORM-модели: тексты, прогоны, запросы, логи, поведение пользователя."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text as SqlText,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class VisitorSession(Base):
    """Анонимная браузерная сессия (cookie rhyme_sid)."""

    __tablename__ = "visitor_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(SqlText, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    requests: Mapped[list["AnalysisRequest"]] = relationship(back_populates="session")
    runs: Mapped[list["AnalysisRun"]] = relationship(back_populates="session")
    events: Mapped[list["UserEvent"]] = relationship(back_populates="session")


class SongText(Base):
    """Канонический текст песни (дедупликация по text_hash)."""

    __tablename__ = "texts"
    __table_args__ = (UniqueConstraint("text_hash", name="uq_texts_hash"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    text_hash: Mapped[str] = mapped_column(String(16), index=True)
    normalized_text: Mapped[str] = mapped_column(SqlText)
    preview: Mapped[str] = mapped_column(String(72), default="")
    lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    block_count: Mapped[int] = mapped_column(Integer, default=0)
    line_count: Mapped[int] = mapped_column(Integer, default=0)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    blocks: Mapped[list["TextBlock"]] = relationship(back_populates="text", cascade="all, delete-orphan")
    runs: Mapped[list["AnalysisRun"]] = relationship(back_populates="text")


class TextBlock(Base):
    """Один блок текста (куплет / припев / hook) внутри texts."""

    __tablename__ = "text_blocks"
    __table_args__ = (Index("ix_text_blocks_text_ordinal", "text_id", "ordinal"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text_id: Mapped[str] = mapped_column(String(36), ForeignKey("texts.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_text: Mapped[str] = mapped_column(SqlText)

    text: Mapped["SongText"] = relationship(back_populates="blocks")


class AnalysisRun(Base):
    """Один прогон анализа — аналог записи output/journal/index.json."""

    __tablename__ = "analysis_runs"
    __table_args__ = (
        Index("ix_runs_created", "created_at"),
        Index("ix_runs_text", "text_id"),
    )

    id: Mapped[str] = mapped_column(String(8), primary_key=True)  # 8 hex, как в файловом журнале
    text_id: Mapped[str] = mapped_column(String(36), ForeignKey("texts.id", ondelete="RESTRICT"))
    session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("visitor_sessions.id", ondelete="SET NULL"), nullable=True
    )
    parent_run_id: Mapped[str | None] = mapped_column(
        String(8), ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True
    )

    song: Mapped[str] = mapped_column(String(200))
    lang: Mapped[str] = mapped_column(String(8), default="ru")
    model: Mapped[str] = mapped_column(String(64), default="")
    model_secondary: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dual_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(32), default="web-form")  # web-form | cli | rerun

    status: Mapped[str] = mapped_column(String(16), default="done")  # pending | running | done | failed
    blocks: Mapped[int] = mapped_column(Integer, default=0)
    lines: Mapped[int] = mapped_column(Integer, default=0)
    chains: Mapped[int] = mapped_column(Integer, default=0)

    report_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    errors_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    text: Mapped["SongText"] = relationship(back_populates="runs")
    session: Mapped["VisitorSession | None"] = relationship(back_populates="runs")
    parent_run: Mapped["AnalysisRun | None"] = relationship(remote_side="AnalysisRun.id")


class AnalysisRequest(Base):
    """Аудит HTTP/API-запроса (даже неудачного)."""

    __tablename__ = "analysis_requests"
    __table_args__ = (Index("ix_requests_created", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("visitor_sessions.id", ondelete="SET NULL"), nullable=True
    )
    analysis_run_id: Mapped[str | None] = mapped_column(
        String(8), ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True
    )

    request_type: Mapped[str] = mapped_column(String(32))  # analyze | estimate | match | journal_* | ...
    method: Mapped[str] = mapped_column(String(8), default="GET")
    path: Mapped[str] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(SqlText, nullable=True)

    request_body: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped["VisitorSession | None"] = relationship(back_populates="requests")
    activity_logs: Mapped[list["ActivityLog"]] = relationship(back_populates="request")


class ActivityLog(Base):
    """Технический лог: этапы пайплайна, ошибки, системные события."""

    __tablename__ = "activity_logs"
    __table_args__ = (Index("ix_activity_created", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("visitor_sessions.id", ondelete="SET NULL"), nullable=True
    )
    analysis_run_id: Mapped[str | None] = mapped_column(
        String(8), ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True
    )
    request_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("analysis_requests.id", ondelete="SET NULL"), nullable=True
    )

    level: Mapped[str] = mapped_column(String(8), default="info")  # info | warn | error
    category: Mapped[str] = mapped_column(String(16), default="pipeline")  # pipeline | http | journal | system
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str] = mapped_column(SqlText)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    request: Mapped["AnalysisRequest | None"] = relationship(back_populates="activity_logs")


class UserEvent(Base):
    """Продуктовая аналитика: действия пользователя в UI."""

    __tablename__ = "user_events"
    __table_args__ = (Index("ix_user_events_session", "session_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("visitor_sessions.id", ondelete="SET NULL"), nullable=True
    )
    event_name: Mapped[str] = mapped_column(String(64), index=True)
    properties: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    page_path: Mapped[str] = mapped_column(String(256), default="/")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    session: Mapped["VisitorSession | None"] = relationship(back_populates="events")
