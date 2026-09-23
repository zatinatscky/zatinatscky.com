"""
CoinGecko — бесплатный публичный API без ключа.

Используется ровно для одной задачи: получить состав топа монет по
капитализации для корзины Altcoin Season Index. Это один запрос в сутки, что
надёжно укладывается в лимиты бесплатного тарифа (около 5–15 запросов в минуту).

Исторические ряды (market_chart по каждой монете) здесь сознательно не берутся:
на бесплатном тарифе серия таких запросов упирается в 429 уже на втором десятке,
из-за чего ежедневная выгрузка становилась ненадёжной. Капитализация BTC берётся
из bitcoin-data.com (см. sources/bitcoindata.py).
"""

from __future__ import annotations

import logging

from .http import get_json

_log = logging.getLogger(__name__)

BASE_URL = "https://api.coingecko.com/api/v3"


def top_coins(per_page: int = 100) -> list[dict]:
    """Топ монет по капитализации: id, symbol, market_cap — одним запросом."""
    rows = get_json(
        f"{BASE_URL}/coins/markets",
        params={
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": 1,
            "sparkline": "false",
        },
    )
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("CoinGecko: пустой ответ coins/markets")
    _log.info("CoinGecko: получено %s монет из топа по капитализации", len(rows))
    return rows
