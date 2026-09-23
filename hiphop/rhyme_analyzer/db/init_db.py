"""Создание таблиц при старте сервиса."""

from __future__ import annotations

from sqlalchemy.engine import Engine

from .config import get_engine
from .models import Base


def init_db(engine: Engine | None = None) -> None:
    """CREATE TABLE IF NOT EXISTS для всех моделей."""
    eng = engine or get_engine()
    Base.metadata.create_all(bind=eng)
