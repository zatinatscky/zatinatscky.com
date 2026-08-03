"""
Google OAuth 2.0 (Authorization Code).

Поток:
1. GET /api/auth/google          → редирект на Google;
2. Google возвращает на          → /api/auth/google/callback?code=...&state=...;
3. Обмениваем code на tokens, тянем userinfo, создаём/находим пользователя,
   ставим cookie и редиректим на фронт.

Нужны env:
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET
  PUBLIC_BASE_URL   (например https://ivan.zatinatscky.com)
"""

from __future__ import annotations

import logging
import os
import secrets
from urllib.parse import urlencode

import requests

_log = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# Скоупы: базовая идентификация + email.
SCOPES = "openid email profile"


def configured() -> bool:
    """True, если заданы client id/secret — иначе кнопка Google в UI скрыта."""
    return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))


def redirect_uri() -> str:
    base = (os.environ.get("PUBLIC_BASE_URL") or "http://localhost:8080").rstrip("/")
    return f"{base}/api/auth/google/callback"


def build_authorize_url(state: str) -> str:
    """URL для редиректа пользователя на экран согласия Google."""
    params = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def new_state() -> str:
    return secrets.token_urlsafe(24)


def exchange_code(code: str) -> dict:
    """
    Обменивает authorization code на access_token и возвращает профиль Google.

    Возвращает dict с ключами: sub, email, name, picture.
    """
    token_resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    token_resp.raise_for_status()
    tokens = token_resp.json()
    access = tokens.get("access_token")
    if not access:
        raise RuntimeError("Google не вернул access_token")

    info_resp = requests.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access}"},
        timeout=20,
    )
    info_resp.raise_for_status()
    info = info_resp.json()
    if not info.get("sub"):
        raise RuntimeError("Google userinfo без sub")
    return info
