"""
Alternative.me — Crypto Fear & Greed Index.

    GET https://api.alternative.me/fng/?limit=0&format=json

limit=0 отдаёт всю историю с 2018 года. Ключ не нужен.

Этот же источник уже используется дашбордом /fng/ через fng_data.fetch_all_points();
здесь он переиспользуется, чтобы ряд в index_observation и таблица
fear_greed_index не разъезжались.
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

Point = tuple[str, float]


def fetch_series() -> list[Point]:
    """Дневной Crypto Fear & Greed как [(YYYY-MM-DD, value)]."""
    # Импорт внутри функции: fng_data тянет pandas, а он нужен не всем фетчерам.
    from fng_data import fetch_all_points

    raw = fetch_all_points()
    if not raw:
        raise RuntimeError("Alternative.me F&G: пустой ряд")

    # У API бывают дубли по дате — оставляем последнее значение за день.
    by_day = {p.date_utc: float(p.value) for p in raw}
    points = sorted(by_day.items())
    _log.info("Alternative.me F&G: %s точек, %s … %s", len(points), points[0][0], points[-1][0])
    return points
