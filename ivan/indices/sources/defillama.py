"""
DefiLlama — совокупное предложение стейблкоинов. Бесплатно, без ключа.

    GET https://stablecoins.llama.fi/stablecoincharts/all

Отдаёт дневной ряд с 2017 года: totalCirculatingUSD.peggedUSD — суммарная
капитализация стейблкоинов, привязанных к доллару. Используется знаменателем
в Stablecoin Supply Ratio (см. sources/computed.py).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .http import get_json

_log = logging.getLogger(__name__)

STABLECOIN_CHART_URL = "https://stablecoins.llama.fi/stablecoincharts/all"


def stablecoin_supply() -> dict[str, float]:
    """Дневное предложение USD-стейблкоинов как {день UTC: supply_usd}."""
    rows = get_json(STABLECOIN_CHART_URL)
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("DefiLlama: пустой ответ stablecoincharts")

    by_day: dict[str, float] = {}
    for row in rows:
        ts = row.get("date")
        total = (row.get("totalCirculatingUSD") or {}).get("peggedUSD")
        if ts is None or not total:
            continue
        day = datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()
        by_day[day] = float(total)

    if not by_day:
        raise RuntimeError("DefiLlama: не удалось разобрать ни одной точки")

    days = sorted(by_day)
    _log.info("DefiLlama stablecoins: %s дней, %s … %s", len(days), days[0], days[-1])
    return by_day
