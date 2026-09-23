"""
bitcoin-data.com — бесплатные on-chain метрики Bitcoin без ключа.

Единственный найденный бесплатный источник для NUPL и MVRV Z-Score: у Glassnode
и CryptoQuant эти метрики закрыты платной подпиской.

    GET https://bitcoin-data.com/v1/nupl          → [{"d":"2026-08-01","nupl":0.1661}, …]
    GET https://bitcoin-data.com/v1/mvrv-zscore   → [{"d":"2026-08-01","mvrvZscore":0.3471}, …]

Глубина истории — около четырёх лет (~1460 точек), для окна терминала в 365 дней
этого более чем достаточно. Имя поля со значением разное у каждой метрики,
поэтому передаётся аргументом value_key.
"""

from __future__ import annotations

import logging
import threading
import time

from .http import get_json

_log = logging.getLogger(__name__)

BASE_URL = "https://bitcoin-data.com/v1"

# С этого хоста за один прогон синхронизации забираются три метрики (nupl,
# mvrv-zscore, market-cap). Подряд без паузы он отвечает 429, поэтому запросы
# разносятся во времени, а на сам 429 отводится длинный backoff.
MIN_INTERVAL_SECONDS = 6.0

_rate_lock = threading.Lock()
_last_request_at = 0.0

Point = tuple[str, float]


def _throttle() -> None:
    """Держит паузу между запросами к bitcoin-data.com."""
    global _last_request_at
    with _rate_lock:
        wait = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def fetch_series(path: str, value_key: str) -> list[Point]:
    """Метрика bitcoin-data.com как [(YYYY-MM-DD, value)]."""
    _throttle()
    payload = get_json(f"{BASE_URL}/{path}", attempts=5, backoff=3.0)
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"bitcoin-data {path}: ожидался непустой массив, получено {type(payload)}")

    points: list[Point] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        day = str(item.get("d") or "")[:10]
        raw = item.get(value_key)
        if not day or raw is None:
            continue
        try:
            points.append((day, float(raw)))
        except (TypeError, ValueError):
            continue

    if not points:
        raise RuntimeError(f"bitcoin-data {path}: нет точек с ключом {value_key!r}")

    points.sort(key=lambda p: p[0])
    _log.info("bitcoin-data %s: %s точек, %s … %s", path, len(points), points[0][0], points[-1][0])
    return points
