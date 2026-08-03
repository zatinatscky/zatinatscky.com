"""
CBOE — официальная история индекса VIX, CSV без ключа.

    https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv

Формат: DATE,OPEN,HIGH,LOW,CLOSE с датами вида 07/31/2026, история с 1990 года.
Это первоисточник VIX, поэтому используется как резерв к FRED VIXCLS: ряды
совпадают, но у CBOE нет задержки на публикацию в базе ФРБ.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime

from .http import get_text

_log = logging.getLogger(__name__)

VIX_HISTORY_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"

Point = tuple[str, float]


def fetch_vix() -> list[Point]:
    """Дневные закрытия VIX как [(YYYY-MM-DD, close)]."""
    body = get_text(VIX_HISTORY_URL)
    reader = csv.DictReader(io.StringIO(body))

    points: list[Point] = []
    for row in reader:
        raw_date = (row.get("DATE") or "").strip()
        raw_close = (row.get("CLOSE") or "").strip()
        if not raw_date or not raw_close:
            continue
        try:
            day = datetime.strptime(raw_date, "%m/%d/%Y").date().isoformat()
            points.append((day, float(raw_close)))
        except ValueError:
            continue

    if not points:
        raise RuntimeError("CBOE VIX: не удалось разобрать ни одной строки")

    points.sort(key=lambda p: p[0])
    _log.info("CBOE VIX: %s точек, %s … %s", len(points), points[0][0], points[-1][0])
    return points
