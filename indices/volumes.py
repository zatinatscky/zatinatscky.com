"""
Объёмы биржевой торговли, сопоставленные индексам.

Раньше на графике каждого индекса рисовались одни и те же столбики объёма из
мок-генератора: под индексом делового климата и доходностью гособлигаций стоял
оборот биткоина. Это вводило в заблуждение, поэтому объём теперь привязан
к индексу и появляется только там, где он осмыслен.

Правило: объём показывается, если индекс описывает конкретный торгуемый рынок
и дневной оборот этого рынка доступен бесплатно.

- BTC spot (`btc_spot`) — для индексов вокруг рынка биткоина: Fear & Greed,
  DVOL, NUPL, MVRV Z-Score, Stablecoin Supply Ratio. Базовый актив у всех один,
  и оборот спота показывает активность именно в нём.
- BTC perpetual (`btc_perp`) — для ставки финансирования: она рассчитывается по
  тому самому бессрочному контракту, поэтому оборот берётся с fapi, а не со спота.

Объёма нет:
- `altseason` — индекс широты по 50 монетам, единого рынка за ним нет;
- `spx`, `nikkei`, `brent` — рынки торгуемые, но бесплатного дневного оборота
  для них нет (FRED объёмы не публикует, Yahoo отвечает 429 при регулярных
  обращениях). Это ограничение доступности данных, а не смысла;
- `vix`, `cnnfng`, `us10y`, `dxy` — не торгуемые инструменты: расчётный индекс
  волатильности, композит настроений, доходность и котировочная корзина.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

_log = logging.getLogger(__name__)

Point = tuple[str, float]

# Идентификаторы рынков и подписи для интерфейса.
BTC_SPOT = "btc_spot"
BTC_PERP = "btc_perp"

MARKET_LABELS: dict[str, str] = {
    BTC_SPOT: "BTC spot volume",
    BTC_PERP: "BTC perp volume",
}

# Глубина истории объёмов: чуть больше окна терминала.
HISTORY_DAYS = 420

# Кэш на процесс: BTC spot нужен пяти индексам, и тянуть его пять раз не нужно.
_cache: dict[str, list[Point]] = {}


def label(market: str | None) -> str | None:
    """Подпись рынка для легенды графика."""
    return MARKET_LABELS.get(market) if market else None


def _fetch(market: str) -> list[Point]:
    """Ряд дневного оборота указанного рынка."""
    # Импорт внутри функции: registry.py берёт отсюда только константы рынков,
    # и незачем тянуть в него сетевой слой целиком.
    from .sources import binance

    start = datetime.now(tz=timezone.utc) - timedelta(days=HISTORY_DAYS)
    start_ms = int(start.timestamp() * 1000)

    if market == BTC_SPOT:
        return binance.fetch_daily_quote_volumes("BTCUSDT", start_ms)
    if market == BTC_PERP:
        return binance.fetch_daily_quote_volumes("BTCUSDT", start_ms, futures=True)
    raise KeyError(f"Неизвестный рынок объёма: {market!r}")


def series_for(market: str | None) -> list[Point]:
    """
    Оборот рынка как [(YYYY-MM-DD, volume)]; пустой список, если рынка нет.

    Результат кэшируется на время прогона синхронизации.
    """
    if not market:
        return []
    if market not in _cache:
        _cache[market] = _fetch(market)
    return _cache[market]


def reset_cache() -> None:
    """Сбрасывает кэш — нужен, если синхронизация запускается несколько раз в процессе."""
    _cache.clear()
