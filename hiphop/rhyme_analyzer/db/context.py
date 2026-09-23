"""Контекст запроса: session_id и request_id для логов в middleware и пайплайне."""

from __future__ import annotations

from contextvars import ContextVar

# UUID сессии visitor_sessions (не cookie-токен).
session_id_var: ContextVar[str | None] = ContextVar("session_id", default=None)
# UUID текущего analysis_requests.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
# ID прогона analysis_runs (8 hex) — выставляется при старте анализа.
run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)

SESSION_COOKIE = "rhyme_sid"
