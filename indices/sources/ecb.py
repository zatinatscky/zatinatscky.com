"""
Индекс доллара DXY, посчитанный из дневных референсных курсов ЕЦБ.

Почему считаем сами: биржевой тикер DXY бесплатно отдавал только неофициальный
эндпоинт Yahoo Finance (429 при регулярных обращениях), а у FRED ближайший
аналог DTWEXBGS — другая, более широкая корзина, и публикуется с недельным лагом.

Формула DXY открыта, а курсы ЕЦБ бесплатны, обновляются каждый рабочий день
и не требуют ключа — так что индекс воспроизводится точно:

    DXY = 50.14348112
          × EURUSD^-0.576 × USDJPY^0.136 × GBPUSD^-0.119
          × USDCAD^0.091  × USDSEK^0.042 × USDCHF^0.036

Проверка: на курсах ЕЦБ за 2026-08-03 формула даёт 99.71 против 99.66
у биржевого тикера — расхождение только из-за времени фиксинга.

Источник курсов — api.frankfurter.dev, бесплатная обёртка над публикацией ЕЦБ.
"""

from __future__ import annotations

import logging

from .http import TOOL_UA, get_json

_log = logging.getLogger(__name__)

FRANKFURTER_URL = "https://api.frankfurter.dev/v1/{start}.."

# Множитель, приводящий индекс к базе марта 1973 = 100.
DXY_BASE = 50.14348112

# Вес каждой валюты и направление котировки.
# quoted_per_usd=True  → в ответе курс «сколько валюты за 1 USD» (USDJPY, USDCAD…);
#   такие валюты входят в произведение с положительным показателем.
# quoted_per_usd=False → курс нужно перевернуть, чтобы получить EURUSD / GBPUSD;
#   они входят с отрицательным показателем, так как рост EURUSD ослабляет доллар.
DXY_COMPONENTS: tuple[tuple[str, float, bool], ...] = (
    ("EUR", -0.576, False),
    ("JPY", 0.136, True),
    ("GBP", -0.119, False),
    ("CAD", 0.091, True),
    ("SEK", 0.042, True),
    ("CHF", 0.036, True),
)

# Ряд нужен только на окно терминала плюс запас на выходные и праздники.
HISTORY_START = "2023-01-01"

Point = tuple[str, float]


def fetch_dxy(start: str = HISTORY_START) -> list[Point]:
    """Дневной DXY как [(YYYY-MM-DD, value)], посчитанный из курсов ЕЦБ."""
    symbols = ",".join(code for code, _, _ in DXY_COMPONENTS)
    payload = get_json(
        FRANKFURTER_URL.format(start=start),
        params={"base": "USD", "symbols": symbols},
        headers={"User-Agent": TOOL_UA},
    )

    rates_by_day = (payload or {}).get("rates") or {}
    if not rates_by_day:
        raise RuntimeError("ECB/Frankfurter: в ответе нет курсов")

    points: list[Point] = []
    for day, rates in rates_by_day.items():
        value = DXY_BASE
        complete = True

        for code, weight, quoted_per_usd in DXY_COMPONENTS:
            rate = rates.get(code)
            if not rate:
                # Пропускаем день целиком: индекс по неполной корзине не считается.
                complete = False
                break
            # ЕЦБ отдаёт «валюты за 1 USD»; для EUR и GBP нужна обратная котировка.
            quote = float(rate) if quoted_per_usd else 1.0 / float(rate)
            value *= quote**weight

        if complete:
            points.append((day[:10], value))

    if not points:
        raise RuntimeError("ECB/Frankfurter: не удалось посчитать ни одного дня")

    points.sort(key=lambda p: p[0])
    _log.info("DXY из курсов ЕЦБ: %s точек, %s … %s", len(points), points[0][0], points[-1][0])
    return points
