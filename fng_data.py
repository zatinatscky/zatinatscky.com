"""
Утилиты для загрузки и хранения индекса Fear & Greed (crypto).

Хранение: PostgreSQL через переменную окружения DATABASE_URL (как на Render).
Локально без DATABASE_URL используется SQLite в ./data/ — удобно для быстрых тестов.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# Публичное API индекса Fear & Greed.
FNG_API_URL = "https://api.alternative.me/fng/"

# Кэш движка на процесс (gunicorn — по одному на воркер).
_engine: Engine | None = None


@dataclass(frozen=True)
class FngPoint:
    """Одна точка временного ряда индекса."""

    ts: int
    date_utc: str
    value: int
    classification: str


def default_sqlite_path() -> Path:
    """Путь к локальной SQLite при отсутствии DATABASE_URL."""
    return Path(__file__).resolve().parent / "data" / "fear_greed.db"


def utc_date_from_ts(ts: int) -> str:
    """Преобразует UNIX timestamp в дату формата YYYY-MM-DD (UTC)."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()


def _normalize_database_url(url: str) -> str:
    """
    - Render иногда отдаёт postgres://... → приводим к postgresql://...
    - Для драйвера psycopg v3 SQLAlchemy ожидает префикс postgresql+psycopg://
      (иначе по умолчанию тянется psycopg2, на Python 3.14 часто нет колёс).
    """
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    # Уже указан драйвер (postgresql+psycopg, +asyncpg, …) — не трогаем.
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def get_engine() -> Engine:
    """
    Возвращает общий Engine.

    - Если задан DATABASE_URL — подключение к PostgreSQL (или другой БД по URL).
    - Иначе — SQLite файл в ./data/ (только для локальной разработки).
    """
    global _engine
    if _engine is not None:
        return _engine

    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        db_path = default_sqlite_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{db_path.resolve().as_posix()}"
    else:
        url = _normalize_database_url(url)

    # pool_pre_ping — переподключение после idle на Render / облаках
    _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def init_db(engine: Engine) -> None:
    """
    Создаёт таблицу, если её ещё нет.

    Для PostgreSQL date_utc — тип DATE; для SQLite — TEXT (ISO-дата).
    """
    if engine.dialect.name == "postgresql":
        ddl = """
        CREATE TABLE IF NOT EXISTS fear_greed_index (
            ts BIGINT PRIMARY KEY,
            date_utc DATE NOT NULL,
            value INTEGER NOT NULL,
            classification TEXT NOT NULL
        )
        """
    else:
        ddl = """
        CREATE TABLE IF NOT EXISTS fear_greed_index (
            ts INTEGER PRIMARY KEY,
            date_utc TEXT NOT NULL,
            value INTEGER NOT NULL,
            classification TEXT NOT NULL
        )
        """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def fetch_all_points() -> list[FngPoint]:
    """
    Загружает всю доступную историю с alternative.me.

    limit=0 у API возвращает максимум доступных записей.
    """
    response = requests.get(
        FNG_API_URL,
        params={"limit": 0, "format": "json"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    raw_points = payload.get("data", [])

    points: list[FngPoint] = []
    for item in raw_points:
        ts = int(item["timestamp"])
        points.append(
            FngPoint(
                ts=ts,
                date_utc=utc_date_from_ts(ts),
                value=int(item["value"]),
                classification=str(item.get("value_classification", "")),
            )
        )

    points.sort(key=lambda p: p.ts)
    return points


def _upsert_sql(engine: Engine) -> str:
    """
    ON CONFLICT DO UPDATE: в PostgreSQL псевдотаблица EXCLUDED, в SQLite — excluded.
    """
    excluded = "EXCLUDED" if engine.dialect.name == "postgresql" else "excluded"
    return f"""
        INSERT INTO fear_greed_index (ts, date_utc, value, classification)
        VALUES (:ts, :date_utc, :value, :classification)
        ON CONFLICT (ts) DO UPDATE SET
            date_utc = {excluded}.date_utc,
            value = {excluded}.value,
            classification = {excluded}.classification
    """


def upsert_points(engine: Engine, points: Iterable[FngPoint]) -> int:
    """
    Добавляет/обновляет точки в БД.

    Возвращает число обработанных строк.
    """
    rows = list(points)
    if not rows:
        return 0

    sql = text(_upsert_sql(engine))
    with engine.begin() as conn:
        for p in rows:
            conn.execute(
                sql,
                {
                    "ts": p.ts,
                    "date_utc": p.date_utc,
                    "value": p.value,
                    "classification": p.classification,
                },
            )
    return len(rows)


def full_refresh(engine: Engine) -> int:
    """
    Полностью синхронизирует ряд из API в БД (upsert по всем точкам).

    Подходит для ежедневного cron: объём ряда небольшой.
    """
    init_db(engine)
    points = fetch_all_points()
    return upsert_points(engine, points)


def load_fng_dataframe(engine: Engine) -> pd.DataFrame:
    """Читает ряд из БД в DataFrame для графиков Dash."""
    df = pd.read_sql_query(
        """
        SELECT date_utc, value, classification
        FROM fear_greed_index
        ORDER BY date_utc
        """,
        engine,
    )

    if df.empty:
        return df

    df["date_utc"] = pd.to_datetime(df["date_utc"], utc=True)
    df["rolling_30d"] = df["value"].rolling(window=30, min_periods=1).mean()
    return df
