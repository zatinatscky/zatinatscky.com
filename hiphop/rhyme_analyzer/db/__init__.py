"""Слой PostgreSQL / SQLite для сервиса rhyme_analyzer.

Таблицы:
  visitor_sessions  — анонимные сессии браузера (cookie)
  texts / text_blocks — канонические тексты песен (дедуп по text_hash)
  analysis_runs     — прогоны анализа (замена output/journal/)
  analysis_requests — аудит HTTP/API-запросов
  activity_logs     — технические события пайплайна и сервера
  user_events       — продуктовая аналитика (действия в UI)
"""

from .config import database_enabled, default_sqlite_path, get_engine
from .init_db import init_db

__all__ = [
    "database_enabled",
    "default_sqlite_path",
    "get_engine",
    "init_db",
]
