"""
CNN Business Fear & Greed Index — индикатор настроений рынка акций США.

Эндпоинт, который питает виджет на сайте CNN:

    GET https://production.dataviz.cnn.io/index/fearandgreed/graphdata

Официально не документирован и закрыт фильтром ботов: без заголовков реального
браузера (Origin/Referer на cnn.com) отвечает «I'm a teapot. You're a bot.».
Отдаёт ~250 дневных точек — примерно год истории, чего хватает на окно терминала.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .http import get_json

_log = logging.getLogger(__name__)

GRAPHDATA_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

# Без Origin/Referer запрос отбивается фильтром ботов.
CNN_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://edition.cnn.com",
    "Referer": "https://edition.cnn.com/markets/fear-and-greed",
}

Point = tuple[str, float]


def fetch_series() -> list[Point]:
    """История индекса CNN Fear & Greed как [(YYYY-MM-DD, score)]."""
    payload = get_json(GRAPHDATA_URL, headers=CNN_HEADERS)

    historical = (payload or {}).get("fear_and_greed_historical") or {}
    rows = historical.get("data") or []
    if not rows:
        raise RuntimeError("CNN F&G: в ответе нет fear_and_greed_historical.data")

    # x — метка времени в миллисекундах, y — значение 0–100.
    by_day: dict[str, float] = {}
    for row in rows:
        ts, value = row.get("x"), row.get("y")
        if ts is None or value is None:
            continue
        day = datetime.fromtimestamp(float(ts) / 1000.0, tz=timezone.utc).date().isoformat()
        by_day[day] = float(value)

    if not by_day:
        raise RuntimeError("CNN F&G: не удалось разобрать ни одной точки")

    points = sorted(by_day.items())
    _log.info("CNN F&G: %s точек, %s … %s", len(points), points[0][0], points[-1][0])
    return points
