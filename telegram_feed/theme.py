"""Палитра light-темы IVAN Terminal — те же токены, что в ivan/js/lib.js."""

from __future__ import annotations

# Light theme (telegram_feed всегда светлый: в канале читается днём и ночью).
BG = "#EBEBEB"
BG2 = "#F7F6F4"
TEXT = "#013547"
TEXT_DIM = "#6C6F6E"
TEXT_FAINT = "#8b9aa0"
ACCENT = "#DDBA9B"
GRID = (1, 53, 71, 20)  # rgba ~8%
UP = "#2e7d5f"
DOWN = "#bf5b41"
HAIRLINE = (1, 53, 71, 33)

# Размер карточки: удобно в ленте Telegram (почти 16:9).
WIDTH = 1200
HEIGHT = 675

# Сколько календарных дней на графике.
CHART_DAYS = 14
# Запас истории для Δ 30d и зоны «vs 52w».
HISTORY_DAYS = 370

# Индексы, которые не постим в дневной канал (пусто = все 14 индексов).
EXCLUDED_IDS: frozenset[str] = frozenset()

DOMAIN_EMOJI = {
    "Crypto": "🟠",
    "Equities": "📊",
    "Commodities": "🛢️",
    "Macro": "🏛️",
    "FX": "💱",
}
