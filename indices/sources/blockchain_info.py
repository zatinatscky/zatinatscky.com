"""
blockchain.info — дневная эмиссия Bitcoin (число монет в обращении).

    GET https://api.blockchain.info/charts/total-bitcoins?timespan=5years&format=json

Бесплатно, без ключа, дневное разрешение (~1500 точек за 5 лет, около 50 КБ).

Нужно для расчёта капитализации BTC: капитализация = цена × эмиссия. Цена берётся
из дневных свечей Binance (sources/binance.py). Такая пара источников надёжнее,
чем готовая капитализация с bitcoin-data.com: тот же хост уже отдаёт NUPL и MVRV,
и третий тяжёлый запрос за прогон упирается в его лимиты.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .http import TOOL_UA, get_json

_log = logging.getLogger(__name__)

TOTAL_BITCOINS_URL = "https://api.blockchain.info/charts/total-bitcoins"


def circulating_supply(timespan: str = "5years") -> dict[str, float]:
    """Число BTC в обращении по дням как {день UTC: supply}."""
    payload = get_json(
        TOTAL_BITCOINS_URL,
        params={"timespan": timespan, "format": "json"},
        headers={"User-Agent": TOOL_UA},
    )
    values = (payload or {}).get("values") or []
    if not values:
        raise RuntimeError("blockchain.info: пустой ряд total-bitcoins")

    by_day: dict[str, float] = {}
    for point in values:
        ts, supply = point.get("x"), point.get("y")
        if ts is None or not supply:
            continue
        day = datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
        by_day[day] = float(supply)

    if not by_day:
        raise RuntimeError("blockchain.info: не удалось разобрать ни одной точки")

    days = sorted(by_day)
    _log.info("blockchain.info эмиссия BTC: %s дней, %s … %s", len(days), days[0], days[-1])
    return by_day
