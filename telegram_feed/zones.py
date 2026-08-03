"""Зоны/ярлыки — та же логика, что IVAN.zoneOf во фронтенде."""

from __future__ import annotations


def fng_zone(v: float) -> tuple[str, str]:
    if v < 25:
        return "Extreme Fear", "#c05b3d"
    if v < 48:
        return "Fear", "#cf8a58"
    if v < 53:
        return "Neutral", "#b3a26b"
    if v < 75:
        return "Greed", "#5d9c85"
    return "Extreme Greed", "#2f8268"


def zone_of(index_id: str, value: float, series: list[float], gauge: bool) -> tuple[str, str] | None:
    """
    Возвращает (label, color_hex) или None, если ярлык не нужен.

    Для обычных рядов — перцентиль относительно переданного series (лучше ≥1y).
    """
    if index_id == "fng" or (gauge and index_id == "cnnfng"):
        return fng_zone(value)
    if index_id == "altseason":
        if value < 25:
            return "Bitcoin Season", "#cf8a58"
        if value > 75:
            return "Altcoin Season", "#2f8268"
        return "Transition", "#b3a26b"
    if gauge:
        return fng_zone(value)
    if not series:
        return None
    below = sum(1 for x in series if x <= value)
    pct = (below / len(series)) * 100
    if pct >= 82:
        return "Very high vs 52w", "#013547"
    if pct >= 60:
        return "High vs 52w", "#6C6F6E"
    if pct >= 40:
        return "Mid vs 52w", "#6C6F6E"
    if pct >= 18:
        return "Low vs 52w", "#6C6F6E"
    return "Very low vs 52w", "#013547"
