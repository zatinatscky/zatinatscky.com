"""
Сборка дневных рядов для фронтенда.

Задача модуля — привести ряды к одному календарю. Фронтенд (ivan/js/app.js)
обращается к рядам по индексу: s[s.length - 2] для суточного изменения,
s[s.length - 31] для месячного, s.slice(-90) для среднего. Значит все ряды должны
быть одной длины и выровнены по общему массиву дат, иначе даты на графике
разъедутся со значениями.

Все индексы в реестре обновляются раз в сутки, но календари у них всё равно
разные: биржи, FRED и ЕЦБ не публикуют данные в выходные и праздники, тогда как
крипта торгуется без перерывов. Поэтому ряд переносится на непрерывный календарь
методом forward-fill — последнее известное значение держится до появления нового.
Так пятничное закрытие S&P 500 корректно стоит на субботе и воскресенье.

Дни до первого наблюдения заполняются первым известным значением, чтобы ряд был
цельным: charts.js рисует полилинию и не умеет разрывать её на null.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .registry import SPECS, IndexSpec, meta_dict
from .store import load_all_points

_log = logging.getLogger(__name__)

Point = tuple[str, float]

# Запас истории перед началом окна: с него начинается forward-fill, если
# последнее наблюдение старше первой даты окна (длинные праздники, лаг FRED).
LOOKBEHIND_DAYS = 60


def calendar_days(days: int, end: date | None = None) -> list[str]:
    """Список ISO-дат последних `days` календарных дней UTC, по возрастанию."""
    last = end or datetime.now(tz=timezone.utc).date()
    return [(last - timedelta(days=days - 1 - i)).isoformat() for i in range(days)]


def forward_fill(points: list[Point], days_list: list[str]) -> list[float] | None:
    """
    Переносит ряд на календарь days_list методом forward-fill.

    points должен быть отсортирован по дате. Возвращает None для пустого ряда —
    такой индекс в выдачу не попадает.
    """
    if not points:
        return None

    series: list[float] = []
    # Оба списка отсортированы, поэтому проходим их за O(n + m) одним курсором.
    cursor = 0
    # До первого наблюдения показываем самое раннее известное значение.
    current = points[0][1]

    for day in days_list:
        while cursor < len(points) and points[cursor][0] <= day:
            current = points[cursor][1]
            cursor += 1
        series.append(current)

    return series


def _load_btc_daily(engine: Engine, since: str) -> tuple[list[Point], list[Point]]:
    """
    Дневные цена и объём BTC из btc_usd_daily как два ряда точек.

    Таблицу наполняет fng_data.sync_btc_prices() для дашборда /fng/; здесь она
    переиспользуется, чтобы на графике индекса можно было наложить цену BTC.
    """
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT day_utc, close_usd, quote_volume_usdt
                      FROM btc_usd_daily
                     WHERE day_utc >= :since
                     ORDER BY day_utc
                    """
                ),
                {"since": since},
            ).fetchall()
    except Exception as exc:
        _log.warning("btc_usd_daily недоступна (%s) — график пойдёт без цены BTC", exc)
        return [], []

    price = [(str(r[0])[:10], float(r[1])) for r in rows if r[1] is not None]
    volume = [(str(r[0])[:10], float(r[2])) for r in rows if r[2] is not None]
    return price, volume


def build_index_payload(
    engine: Engine,
    days: int = 365,
    specs: tuple[IndexSpec, ...] = SPECS,
) -> dict:
    """
    Собирает ответ /api/indexes: общий календарь дат, цену BTC и ряды индексов.

    Индексы без данных в БД пропускаются — фронтенд просто не покажет карточку,
    вместо того чтобы падать на пустом массиве.
    """
    days_list = calendar_days(days)

    # Один SELECT на все индексы вместо запроса на каждый.
    since = (date.fromisoformat(days_list[0]) - timedelta(days=LOOKBEHIND_DAYS)).isoformat()
    raw = load_all_points(engine, since=since)

    indexes: list[dict] = []
    skipped: list[str] = []

    for spec in specs:
        points = raw.get(spec.id) or []
        series = forward_fill(points, days_list)
        if series is None:
            skipped.append(spec.id)
            continue

        meta = meta_dict(spec)
        meta["series"] = series
        indexes.append(meta)

    if skipped:
        _log.warning("Нет данных в БД для индексов: %s", ", ".join(skipped))

    # Цена и объём BTC — для режима сравнения на странице индекса.
    btc_points, vol_points = _load_btc_daily(engine, since)
    btc = forward_fill(btc_points, days_list) or []
    vol = forward_fill(vol_points, days_list) or []

    return {
        "asOf": days_list[-1],
        "days": days,
        "dates": days_list,
        "btc": btc,
        "vol": vol,
        "indexes": indexes,
    }
