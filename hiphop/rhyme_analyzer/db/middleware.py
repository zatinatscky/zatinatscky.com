"""FastAPI middleware: cookie-сессия, аудит запросов, контекст для логов."""

from __future__ import annotations

import json
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import database_enabled
from .context import SESSION_COOKIE, request_id_var, session_id_var
from .repository import get_or_create_session, log_request, new_session_token
from .session import session_scope


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _classify_request(path: str, method: str) -> str | None:
    """Тип запроса для analysis_requests; None — не логируем."""
    if not path.startswith("/api/"):
        return None
    if path == "/api/analyze" or path == "/api/analyze/stream":
        return "analyze"
    if path == "/api/estimate":
        return "estimate"
    if path == "/api/journal/match":
        return "match"
    if path == "/api/events":
        return "events"
    if path.startswith("/api/journal/") and path.endswith("/rerun/stream"):
        return "rerun"
    if path == "/api/journal":
        return "journal_list"
    if "/input" in path:
        return "journal_input"
    if "/data" in path:
        return "journal_data"
    if "/export.html" in path:
        return "journal_export"
    if method == "DELETE" and path.startswith("/api/journal/"):
        return "journal_delete"
    if method == "PATCH" and path.startswith("/api/journal/"):
        return "journal_rename"
    return "api_other"


async def _read_json_body(request: Request) -> tuple[dict[str, Any] | None, bytes]:
    """Читает тело запроса и возвращает (parsed_json, raw_bytes) для повторной отдачи роуту."""
    if request.method not in ("POST", "PATCH", "PUT"):
        return None, b""
    raw = await request.body()
    if not raw:
        return None, raw
    try:
        data = json.loads(raw)
        parsed = data if isinstance(data, dict) else {"_raw_type": type(data).__name__}
        return parsed, raw
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, raw


def _request_with_body(request: Request, body: bytes) -> Request:
    """Новый Request с тем же scope, но телом можно прочитать повторно."""
    if not body:
        return request

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(request.scope, receive)


class DatabaseMiddleware(BaseHTTPMiddleware):
    """Сессия + аудит API-запросов в analysis_requests."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if not database_enabled():
            return await call_next(request)

        token = request.cookies.get(SESSION_COOKIE)
        new_cookie = False
        if not token:
            token = new_session_token()
            new_cookie = True

        ip = _client_ip(request)
        ua = request.headers.get("user-agent")

        session_uuid: str | None = None
        with session_scope() as db:
            session_row = get_or_create_session(db, token=token, ip_address=ip, user_agent=ua)
            session_uuid = session_row.id

        session_token = session_id_var.set(session_uuid)
        req_type = _classify_request(request.url.path, request.method)
        body_json, raw_body = await _read_json_body(request) if req_type else (None, b"")
        if raw_body:
            request = _request_with_body(request, raw_body)

        # Логируем запрос сразу — request_id нужен пайплайну до завершения ответа (SSE).
        request_uuid: str | None = None
        req_token = None
        if req_type:
            with session_scope() as db:
                req_row = log_request(
                    db,
                    request_type=req_type,
                    method=request.method,
                    path=str(request.url.path),
                    session_id=session_uuid,
                    ip_address=ip,
                    user_agent=ua,
                    request_body=body_json,
                )
                request_uuid = req_row.id
            req_token = request_id_var.set(request_uuid)

        started = time.perf_counter()
        response: Response | None = None
        error_summary: dict[str, Any] | None = None

        try:
            response = await call_next(request)
        except Exception as exc:
            error_summary = {"error": str(exc)}
            raise
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            if req_type and request_uuid:
                summary: dict[str, Any] | None = error_summary
                if summary is None and response is not None:
                    summary = {"status": response.status_code}
                with session_scope() as db:
                    from .models import AnalysisRequest

                    row = db.get(AnalysisRequest, request_uuid)
                    if row:
                        row.response_status = response.status_code if response else 500
                        row.response_summary = summary
                        row.duration_ms = duration_ms
                        db.flush()

            if req_token is not None:
                request_id_var.reset(req_token)
            session_id_var.reset(session_token)

        if new_cookie and response is not None:
            response.set_cookie(
                SESSION_COOKIE,
                token,
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                samesite="lax",
            )
        return response
