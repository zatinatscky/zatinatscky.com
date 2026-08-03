"""
Binance — публичные Spot и Futures эндпоинты без ключа.

Отсюда берутся:
- funding — история ставки финансирования бессрочного контракта BTCUSDT
  (fapi/v1/fundingRate): расчёт происходит трижды в сутки, поэтому усредняем
  в дневное значение и переводим в проценты;
- дневные свечи (api/v3/klines) — сырьё для расчёта Altcoin Season Index
  в sources/computed.py.

Оба эндпоинта отдают максимум 1000 записей за запрос, поэтому история
листается окнами по startTime.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

from .http import get_json

_log = logging.getLogger(__name__)

FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
KLINES_URL = "https://api.binance.com/api/v3/klines"
TICKER_24H_URL = "https://api.binance.com/api/v3/ticker/24hr"

PAGE_LIMIT = 1000
MS_PER_DAY = 86_400_000

Point = tuple[str, float]


def _day_utc(ms: int) -> str:
    """Метка времени в миллисекундах → календарный день UTC."""
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).date().isoformat()


def fetch_funding_rate(symbol: str = "BTCUSDT") -> list[Point]:
    """
    Дневная ставка финансирования в процентах.

    API отдаёт долю (0.0000453 = 0.00453%), поэтому умножаем на 100. За сутки
    обычно три расчёта — берём их среднее, чтобы одна точка = один день.
    """
    # Бессрочные фьючерсы Binance запущены в сентябре 2019 — раньше данных нет.
    cursor_ms = int(datetime(2019, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)
    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)

    per_day: dict[str, list[float]] = defaultdict(list)
    pages = 0

    while cursor_ms < now_ms:
        page = get_json(
            FUNDING_URL,
            params={"symbol": symbol, "startTime": cursor_ms, "limit": PAGE_LIMIT},
        )
        if not page:
            break

        for row in page:
            ts = int(row["fundingTime"])
            per_day[_day_utc(ts)].append(float(row["fundingRate"]) * 100.0)

        pages += 1
        last_ts = int(page[-1]["fundingTime"])
        # Следующая страница начинается сразу после последней записи текущей.
        cursor_ms = last_ts + 1
        if len(page) < PAGE_LIMIT:
            break
        time.sleep(0.15)

    if not per_day:
        raise RuntimeError(f"Binance funding {symbol}: пустой ряд")

    points = sorted((day, sum(vals) / len(vals)) for day, vals in per_day.items())
    _log.info(
        "Binance funding %s: %s дней за %s страниц, последняя %s",
        symbol,
        len(points),
        pages,
        points[-1],
    )
    return points


def fetch_daily_closes(symbol: str, start_ms: int) -> dict[str, float]:
    """Дневные закрытия пары как {день UTC: close}, начиная с start_ms."""
    cursor_ms = start_ms
    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    closes: dict[str, float] = {}

    while cursor_ms <= now_ms:
        page = get_json(
            KLINES_URL,
            params={
                "symbol": symbol,
                "interval": "1d",
                "startTime": cursor_ms,
                "limit": PAGE_LIMIT,
            },
        )
        if not page:
            break

        for row in page:
            closes[_day_utc(int(row[0]))] = float(row[4])

        last_open = int(page[-1][0])
        cursor_ms = last_open + MS_PER_DAY
        if len(page) < PAGE_LIMIT:
            break

    return closes


def tradable_usdt_symbols() -> set[str]:
    """
    Пары к USDT с ненулевым оборотом за сутки.

    Нужно, чтобы не запрашивать klines для монет, которых на Binance нет:
    список топ-50 приходит из CoinGecko и не совпадает с листингом биржи.
    """
    rows = get_json(TICKER_24H_URL)
    symbols = {
        str(r["symbol"])
        for r in rows
        if str(r["symbol"]).endswith("USDT") and float(r.get("quoteVolume") or 0) > 0
    }
    _log.info("Binance: %s активных USDT-пар", len(symbols))
    return symbols
