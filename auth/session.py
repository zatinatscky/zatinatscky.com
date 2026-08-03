"""
Подписанная cookie-сессия (itsdangerous).

Формат payload: {"uid": "<user_id>", "iat": <unix_ts>}.
Cookie HttpOnly + SameSite=Lax; Secure включается, если PUBLIC_BASE_URL — https.
"""

from __future__ import annotations

import os
import time
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# Имя cookie в браузере.
COOKIE_NAME = "ivan_session"

# Срок жизни сессии: 30 дней.
MAX_AGE_SEC = 60 * 60 * 24 * 30


def _serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("SECRET_KEY") or "dev-only-change-me"
    return URLSafeTimedSerializer(secret, salt="ivan-auth-session-v1")


def issue_session_token(user_id: str) -> str:
    """Создаёт подписанный токен для cookie."""
    return _serializer().dumps({"uid": user_id, "iat": int(time.time())})


def parse_session_token(token: str) -> str | None:
    """Возвращает user_id из cookie или None, если токен битый/просрочен."""
    try:
        data: dict[str, Any] = _serializer().loads(token, max_age=MAX_AGE_SEC)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid")
    return str(uid) if uid else None


def cookie_secure() -> bool:
    """Secure-флаг cookie: только по HTTPS (прод), на localhost — выкл."""
    base = (os.environ.get("PUBLIC_BASE_URL") or "").lower()
    return base.startswith("https://")
