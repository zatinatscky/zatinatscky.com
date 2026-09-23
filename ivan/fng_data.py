"""
Утилиты для загрузки и хранения индекса Fear & Greed (crypto) и дневных цен BTC/USD.

Хранение: PostgreSQL через переменную окружения DATABASE_URL (как на Render).
Локально без DATABASE_URL используется SQLite в ./data/ — удобно для быстрых тестов.

Цены и объёмы BTC: публичный Spot API Binance `GET /api/v3/klines` (пара BTCUSDT, интервал 1d, UTC).
Ключ не нужен; close в USDT трактуем как USD для графика рядом с индексом F&G.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)

# Публичное API индекса Fear & Greed.
FNG_API_URL = "https://api.alternative.me/fng/"

# Публичные дневные свечи BTC/USDT (UTC-день по open time свечи).
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_BTC_SYMBOL = "BTCUSDT"
# Binance отдаёт максимум 1000 свечей за один запрос — листаем окнами.
BINANCE_KLINE_LIMIT = 1000
MS_PER_DAY = 86400000

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

    _init_btc_table(engine)


def _init_btc_table(engine: Engine) -> None:
    """
    Таблица дневных данных BTC (UTC-день по открытию свечи Binance).

    close_usd — цена закрытия пары BTCUSDT (USDT ~ USD для визуализации).
    volume_btc / quote_volume_usdt — объёмы за сутки с биржи (base и quote).
    """
    ddl = """
    CREATE TABLE IF NOT EXISTS btc_usd_daily (
        day_utc TEXT PRIMARY KEY,
        close_usd REAL NOT NULL,
        volume_btc REAL,
        quote_volume_usdt REAL
    )
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))
    _ensure_btc_extra_columns(engine)


def _ensure_btc_extra_columns(engine: Engine) -> None:
    """Миграция: у старых БД были только day_utc и close_usd — добавляем столбцы объёма."""
    insp = inspect(engine)
    if not insp.has_table("btc_usd_daily"):
        return
    names = {c["name"] for c in insp.get_columns("btc_usd_daily")}
    alters: list[str] = []
    if "volume_btc" not in names:
        alters.append("ALTER TABLE btc_usd_daily ADD COLUMN volume_btc REAL")
    if "quote_volume_usdt" not in names:
        alters.append("ALTER TABLE btc_usd_daily ADD COLUMN quote_volume_usdt REAL")
    if not alters:
        return
    with engine.begin() as conn:
        for stmt in alters:
            conn.execute(text(stmt))


def _btc_upsert_sql(engine: Engine) -> str:
    excluded = "EXCLUDED" if engine.dialect.name == "postgresql" else "excluded"
    return f"""
        INSERT INTO btc_usd_daily (day_utc, close_usd, volume_btc, quote_volume_usdt)
        VALUES (:day_utc, :close_usd, :volume_btc, :quote_volume_usdt)
        ON CONFLICT(day_utc) DO UPDATE SET
            close_usd = {excluded}.close_usd,
            volume_btc = {excluded}.volume_btc,
            quote_volume_usdt = {excluded}.quote_volume_usdt
    """


def _parse_binance_daily_kline(row: list) -> tuple[str, float, float, float]:
    """
    Одна свеча Binance (формат массива) → день UTC, close, объём в BTC, объём в USDT.

    Индексы полей: https://binance-docs.github.io/apidocs/spot/en/#kline-candlestick-data
    """
    open_time_ms = int(row[0])
    day_str = datetime.fromtimestamp(open_time_ms / 1000.0, tz=timezone.utc).date().isoformat()
    close_usdt = float(row[4])
    vol_base = float(row[5])
    quote_vol = float(row[7])
    return day_str, close_usdt, vol_base, quote_vol


def _fetch_binance_daily_klines_page(start_time_ms: int, limit: int = BINANCE_KLINE_LIMIT) -> list[list]:
    """Одна страница дневных свечей BTCUSDT, начиная с start_time_ms (включительно)."""
    response = requests.get(
        BINANCE_KLINES_URL,
        params={
            "symbol": BINANCE_BTC_SYMBOL,
            "interval": "1d",
            "startTime": start_time_ms,
            "limit": limit,
        },
        headers={"Accept": "application/json", "User-Agent": "zatinatscky-site/1.0"},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        raise RuntimeError(f"Binance API error: {payload}")
    return payload


def sync_btc_prices(engine: Engine) -> int:
    """
    Подтягивает дневные BTCUSDT (close + объёмы) за период ряда fear_greed_index (+ «сегодня»).

    Источник: публичный REST Binance, без API-ключа; листание страницами по BINANCE_KLINE_LIMIT свечей.
    """
    _init_btc_table(engine)

    # Диапазон времени берём по ряду F&G: BTC подтягиваем за тот же горизонт (+ «сегодня»).
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT MIN(ts) AS mn, MAX(ts) AS mx FROM fear_greed_index"),
        ).mappings().one()

    mn, mx = row["mn"], row["mx"]
    if mn is None or mx is None:
        _log.info("BTC sync skipped: fear_greed_index is empty.")
        return 0

    now_ts = int(datetime.now(tz=timezone.utc).timestamp())
    to_ts = max(int(mx), now_ts)
    from_ts = int(mn)

    span_days = max(1, (to_ts - from_ts) // 86400)
    # Верхняя оценка числа HTTP-запросов (каждый до BINANCE_KLINE_LIMIT дней).
    est_chunks = max(1, (span_days + BINANCE_KLINE_LIMIT - 1) // BINANCE_KLINE_LIMIT)

    _log.info(
        "BTC sync started (Binance /api/v3/klines, %s, 1d). Unix from=%s to=%s (~%s days, up to ~%s HTTP pages).",
        BINANCE_BTC_SYMBOL,
        from_ts,
        to_ts,
        span_days,
        est_chunks,
    )

    end_ms = to_ts * 1000
    from_ms = from_ts * 1000
    cursor_ms = from_ms
    # day_utc -> (close, vol_btc, quote_usdt); при перекрытии страниц последняя запись побеждает.
    all_days: dict[str, tuple[float, float, float]] = {}
    chunk_no = 0
    max_iters = est_chunks + 8
    it = 0

    while cursor_ms <= end_ms and it < max_iters:
        it += 1
        chunk_no += 1
        _log.info("BTC Binance klines page %s: startTime_ms=%s", chunk_no, cursor_ms)
        page = _fetch_binance_daily_klines_page(cursor_ms, BINANCE_KLINE_LIMIT)
        _log.info("  -> Binance returned %s daily candles (this page).", len(page))
        if not page:
            _log.warning("Binance returned empty klines page at startTime_ms=%s", cursor_ms)
            break

        for row in page:
            open_ms = int(row[0])
            if open_ms < from_ms or open_ms > end_ms:
                continue
            day_str, close_px, vb, vq = _parse_binance_daily_kline(row)
            all_days[day_str] = (close_px, vb, vq)

        last_open_ms = int(page[-1][0])
        # Следующая страница — со следующего календарного дня после последней свечи.
        cursor_ms = last_open_ms + MS_PER_DAY
        if len(page) < BINANCE_KLINE_LIMIT:
            break
        time.sleep(0.12)

    if cursor_ms <= end_ms and it >= max_iters:
        _log.warning(
            "BTC sync hit iteration cap (%s pages); some tail dates may be missing.",
            max_iters,
        )

    if not all_days:
        _log.warning("BTC sync: no rows after Binance pagination; check API or date range.")
        return 0

    _log.info(
        "BTC: merged %s UTC days from Binance; writing close + volumes to database…",
        len(all_days),
    )

    sql = text(_btc_upsert_sql(engine))
    n = 0
    with engine.begin() as conn:
        for day_str in sorted(all_days.keys()):
            close_px, vb, vq = all_days[day_str]
            conn.execute(
                sql,
                {
                    "day_utc": day_str,
                    "close_usd": close_px,
                    "volume_btc": vb,
                    "quote_volume_usdt": vq,
                },
            )
            n += 1
    _log.info("BTC sync finished: upserted %s rows into btc_usd_daily.", n)
    return n


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
    Полностью синхронизирует ряд F&G из API, затем подтягивает BTC/USD за тот же период.

    Подходит для ежедневного cron: объём ряда F&G небольшой; BTC тянется постранично с Binance.
    """
    init_db(engine)
    points = fetch_all_points()
    n = upsert_points(engine, points)
    _log.info("Fear & Greed upsert finished: %s rows.", n)
    try:
        btc_rows = sync_btc_prices(engine)
        _log.info("BTC pipeline reported %s daily rows upserted.", btc_rows)
    except Exception as exc:
        _log.warning(
            "BTC/USD sync failed (dashboard may show index without BTC line): %s",
            exc,
            exc_info=True,
        )
    return n


def load_fng_dataframe(engine: Engine) -> pd.DataFrame:
    """Читает ряд F&G из БД и подмешивает дневной BTC/USD по дате (UTC)."""
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

    try:
        btc = pd.read_sql_query(
            """
            SELECT day_utc, close_usd, volume_btc, quote_volume_usdt
            FROM btc_usd_daily
            """,
            engine,
        )
    except Exception:
        btc = pd.DataFrame(columns=["day_utc", "close_usd", "volume_btc", "quote_volume_usdt"])

    if not btc.empty:
        btc = btc.rename(
            columns={
                "close_usd": "btc_usd",
                "volume_btc": "btc_volume_btc",
                "quote_volume_usdt": "btc_quote_usdt",
            }
        )
        btc["day_merge"] = pd.to_datetime(btc["day_utc"], utc=True).dt.normalize()
        df["day_merge"] = df["date_utc"].dt.normalize()
        df = df.merge(
            btc[["day_merge", "btc_usd", "btc_volume_btc", "btc_quote_usdt"]],
            on="day_merge",
            how="left",
        )
        df = df.drop(columns=["day_merge"])
    else:
        df["btc_usd"] = pd.NA
        df["btc_volume_btc"] = pd.NA
        df["btc_quote_usdt"] = pd.NA

    return df
