"""Подключение к БД: PostgreSQL через DATABASE_URL или локальный SQLite."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.engine import Engine

# Кэш движка на процесс (uvicorn reload — новый процесс).
_engine: Engine | None = None

# Явное отключение БД (только файловый журнал).
_DISABLE_ENV = "DISABLE_DATABASE"


def default_sqlite_path() -> Path:
    """Локальная SQLite, если DATABASE_URL не задан."""
    root = Path(__file__).resolve().parent.parent.parent
    return root / "data" / "hiphop.db"


def _normalize_database_url(url: str) -> str:
    """Приводит URL к формату SQLAlchemy + psycopg v3."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def database_enabled() -> bool:
    """БД включена, если не выставлен DISABLE_DATABASE=1."""
    return os.getenv(_DISABLE_ENV, "").strip().lower() not in ("1", "true", "yes")


def get_database_url() -> str:
    """Строка подключения: POSTGRES_* (Docker), DATABASE_URL или sqlite:///data/hiphop.db."""
    user = os.getenv("POSTGRES_USER", "").strip()
    password = os.getenv("POSTGRES_PASSWORD", "").strip()
    db_name = os.getenv("POSTGRES_DB", "").strip()
    host = os.getenv("POSTGRES_HOST", "").strip()

    # Docker Compose: POSTGRES_HOST задаётся только в web-сервисе — пароль из того же .env, что и db.
    if host and user and password and db_name:
        from urllib.parse import quote_plus

        port = os.getenv("POSTGRES_PORT", "5432").strip() or "5432"
        return (
            f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(password)}"
            f"@{host}:{port}/{quote_plus(db_name)}"
        )

    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return _normalize_database_url(explicit)

    db_path = default_sqlite_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.resolve().as_posix()}"


def get_engine() -> Engine:
    """Общий SQLAlchemy Engine с pool_pre_ping для облачных деплоев."""
    global _engine
    if _engine is not None:
        return _engine

    from sqlalchemy import create_engine

    url = get_database_url()
    connect_args: dict = {}
    if url.startswith("sqlite:"):
        # SQLite: один writer — безопаснее для FastAPI + фоновые потоки.
        connect_args["check_same_thread"] = False

    _engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    return _engine


def reset_engine() -> None:
    """Сброс кэша (тесты / смена DATABASE_URL)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
