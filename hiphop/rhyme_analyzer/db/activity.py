"""Запись activity_logs из пайплайна (в т.ч. из фонового потока SSE)."""

from __future__ import annotations

from typing import Any

from .config import database_enabled
from .context import request_id_var, run_id_var, session_id_var
from .repository import log_activity
from .session import session_scope


class ActivityRecorder:
    """Пишет progress-события в activity_logs параллельно с SSE."""

    def __init__(
        self,
        *,
        analysis_run_id: str | None = None,
        session_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.analysis_run_id = analysis_run_id or run_id_var.get()
        self.session_id = session_id or session_id_var.get()
        self.request_id = request_id or request_id_var.get()

    def record(
        self,
        *,
        message: str,
        level: str = "info",
        category: str = "pipeline",
        stage: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if not database_enabled():
            return
        try:
            with session_scope() as db:
                log_activity(
                    db,
                    message=message,
                    level=level,
                    category=category,
                    stage=stage,
                    payload=payload,
                    session_id=self.session_id,
                    analysis_run_id=self.analysis_run_id,
                    request_id=self.request_id,
                )
        except Exception:
            # Логирование не должно ломать анализ.
            pass

    def on_progress(self, event: dict[str, Any]) -> None:
        """Колбэк для ProgressReporter: дублирует SSE в БД."""
        self.record(
            message=str(event.get("log") or event.get("hint") or ""),
            stage=str(event.get("stage") or ""),
            payload={
                "percent": event.get("percent"),
                "hint": event.get("hint"),
            },
        )
