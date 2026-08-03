"""
Deribit DVOL — 30-дневная подразумеваемая волатильность BTC (крипто-аналог VIX).

Публичный JSON-RPC без ключа:

    /api/v2/public/get_volatility_index_data?currency=BTC&resolution=1D
        &start_timestamp=<ms>&end_timestamp=<ms>

Ответ — массив свечей [open_time_ms, open, high, low, close]; берём close.
Deribit ограничивает окно одного запроса, поэтому история тянется чанками
по DAYS_PER_REQUEST дней назад от сегодняшнего дня.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from .http import get_json

_log = logging.getLogger(__name__)

DVOL_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
# Индекс DVOL публикуется с 2021 года — глубже тянуть нечего.
HISTORY_START = "2021-03-24"
# Размер чанка: с запасом влезает в лимит ответа Deribit на 1D-разрешении.
DAYS_PER_REQUEST = 720

Point = tuple[str, float]


def fetch_series(currency: str = "BTC") -> list[Point]:
    """Дневной DVOL как [(YYYY-MM-DD, close)] за всю доступную историю."""
    start = datetime.fromisoformat(HISTORY_START).replace(tzinfo=timezone.utc)
    now = datetime.now(tz=timezone.utc)

    by_day: dict[str, float] = {}
    cursor = start
    while cursor < now:
        chunk_end = min(cursor + timedelta(days=DAYS_PER_REQUEST), now)
        payload = get_json(
            DVOL_URL,
            params={
                "currency": currency,
                "resolution": "1D",
                "start_timestamp": int(cursor.timestamp() * 1000),
                "end_timestamp": int(chunk_end.timestamp() * 1000),
            },
        )
        rows = ((payload or {}).get("result") or {}).get("data") or []
        for row in rows:
            if len(row) < 5:
                continue
            day = datetime.fromtimestamp(int(row[0]) / 1000.0, tz=timezone.utc).date().isoformat()
            by_day[day] = float(row[4])

        _log.info(
            "Deribit DVOL %s: чанк %s … %s → %s свечей",
            currency,
            cursor.date(),
            chunk_end.date(),
            len(rows),
        )
        cursor = chunk_end
        # Публичный API без ключа — не давим частыми запросами.
        if cursor < now:
            time.sleep(0.3)

    if not by_day:
        raise RuntimeError(f"Deribit DVOL {currency}: пустой ряд")

    points = sorted(by_day.items())
    _log.info("Deribit DVOL %s: всего %s точек, последняя %s", currency, len(points), points[-1])
    return points
