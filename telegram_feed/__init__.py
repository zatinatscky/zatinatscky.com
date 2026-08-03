"""
Карточки для Telegram-канала IVAN: PNG-график 14d + короткая подпись + автопост.

Рендер в стиле терминала (цвета light-темы), без Plotly.
Публикация: `python -m telegram_feed.publish` (см. FORMAT.md).
"""

from telegram_feed.card import build_card, render_day_feed
from telegram_feed.chart import render_chart_png

__all__ = ["build_card", "render_day_feed", "render_chart_png"]
