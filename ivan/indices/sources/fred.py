"""
FRED (Federal Reserve Bank of St. Louis) — CSV без API-ключа.

Официальный REST (api.stlouisfed.org) требует ключ, но графиковый эндпоинт
fredgraph.csv отдаёт полную историю ряда анонимно:

    https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10

Формат ответа — CSV с двумя колонками, где пропуск (выходной/праздник)
обозначен точкой:

    observation_date,DGS10
    2026-07-29,4.67
    2026-07-30,4.68

Покрывает: vix (VIXCLS), spx (SP500), nikkei (NIKKEI225), brent (DCOILBRENTEU),
us10y (DGS10), uscpi (CPIAUCSL → YoY).
"""

from __future__ import annotations

import csv
import io
import logging

from .http import TOOL_UA, get_text

_log = logging.getLogger(__name__)

FREDGRAPH_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# FRED ведёт себя противоположно Yahoo и CNN: на браузерный User-Agent запрос
# висит до таймаута, а на утилитный CSV приходит за секунду. Поэтому здесь
# общий браузерный UA из http.py перебивается явно.
FRED_HEADERS = {"User-Agent": TOOL_UA, "Accept": "text/csv, */*"}

Point = tuple[str, float]


def fetch_series(series_id: str) -> list[Point]:
    """Вся доступная история ряда FRED как [(YYYY-MM-DD, value)]."""
    body = get_text(FREDGRAPH_CSV, params={"id": series_id}, headers=FRED_HEADERS)
    reader = csv.reader(io.StringIO(body))

    header = next(reader, None)
    if not header or len(header) < 2:
        raise RuntimeError(f"FRED {series_id}: неожиданный CSV-заголовок {header!r}")

    points: list[Point] = []
    for row in reader:
        if len(row) < 2:
            continue
        day, raw = row[0].strip(), row[1].strip()
        # FRED ставит '.' там, где наблюдения нет (выходной, праздник, разрыв ряда).
        if not day or raw in ("", "."):
            continue
        try:
            points.append((day[:10], float(raw)))
        except ValueError:
            continue

    if not points:
        raise RuntimeError(f"FRED {series_id}: пустой ряд")

    points.sort(key=lambda p: p[0])
    _log.info("FRED %s: %s точек, %s … %s", series_id, len(points), points[0][0], points[-1][0])
    return points


def fetch_yoy(series_id: str) -> list[Point]:
    """
    Ряд год-к-году в процентах из уровневого ряда (например, CPIAUCSL → US CPI YoY).

    FRED умеет считать YoY сам через units=pc1, но только в REST с ключом, поэтому
    считаем локально: ищем наблюдение ровно на 12 месяцев раньше по календарной
    метке (ряды CPI помечены первым числом месяца, так что сдвиг однозначный).
    """
    levels = fetch_series(series_id)
    by_day = dict(levels)

    points: list[Point] = []
    for day, value in levels:
        year, month, rest = int(day[:4]), int(day[5:7]), day[7:]
        prev_key = f"{year - 1:04d}-{month:02d}{rest}"
        prev = by_day.get(prev_key)
        if prev is None or prev == 0:
            continue
        points.append((day, (value / prev - 1.0) * 100.0))

    if not points:
        raise RuntimeError(f"FRED {series_id}: не удалось посчитать YoY")

    _log.info("FRED %s YoY: %s точек, последняя %s", series_id, len(points), points[-1])
    return points
