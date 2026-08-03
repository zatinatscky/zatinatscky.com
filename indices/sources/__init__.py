"""
Фетчеры внешних источников.

Каждый фетчер — функция, которая принимает params из IndexSpec (registry.py) и
возвращает список точек [(YYYY-MM-DD, float)], отсортированный по дате. Записи в
БД внутри фетчеров нет: этим занимается sync.py, поэтому любой источник можно
проверить в изоляции, не поднимая базу.

Все источники здесь дают дневной ряд и пригодны для регулярной синхронизации раз
в сутки. Неофициальный эндпоинт Yahoo Finance убран сознательно: он отвечает
429 при регулярных обращениях, поэтому индексы, у которых он был единственным
источником (EURO STOXX 50, спот золота, BCOM), в терминал не вошли.

Ключ в FETCHERS = поле IndexSpec.fetcher.
"""

from __future__ import annotations

import logging
from typing import Callable

from . import (
    alternative_me,
    bitcoindata,
    binance,
    cboe,
    cnn,
    computed,
    deribit,
    ecb,
    fred,
)

_log = logging.getLogger(__name__)

Point = tuple[str, float]
Fetcher = Callable[..., list[Point]]


def _fred_series(series_id: str) -> list[Point]:
    """
    Ряд FRED; для VIX при сбое берём первоисточник — CSV самой CBOE.

    FRED публикует с задержкой в один-два рабочих дня и периодически отвечает
    таймаутом, поэтому там, где есть равноценный официальный источник, он
    прописан резервом.
    """
    try:
        return fred.fetch_series(series_id)
    except Exception as exc:
        if series_id != "VIXCLS":
            raise
        _log.warning("FRED VIXCLS недоступен (%s), берём CSV CBOE", exc)
        return cboe.fetch_vix()


FETCHERS: dict[str, Fetcher] = {
    # Прямые источники
    "alternative_me_fng": lambda: alternative_me.fetch_series(),
    "fred": _fred_series,
    "deribit_dvol": lambda currency="BTC": deribit.fetch_series(currency),
    "bitcoin_data": lambda path, value_key: bitcoindata.fetch_series(path, value_key),
    "binance_funding": lambda symbol="BTCUSDT": binance.fetch_funding_rate(symbol),
    "cnn_fng": lambda: cnn.fetch_series(),
    # Расчётные индексы: формула открыта, входные данные бесплатны и дневные.
    "dxy_from_ecb": lambda: ecb.fetch_dxy(),
    "stablecoin_supply_ratio": lambda: computed.stablecoin_supply_ratio(),
    "altseason": lambda: computed.altseason_index(),
}


def fetch(fetcher: str, params: dict | None = None) -> list[Point]:
    """Вызывает фетчер по ключу из registry."""
    fn = FETCHERS.get(fetcher)
    if fn is None:
        raise KeyError(f"Неизвестный фетчер {fetcher!r}; доступны: {sorted(FETCHERS)}")
    return fn(**(params or {}))
