"""
HTTP-роуты авторизации и sync watchlist.

Подключается из app.py: register_auth_routes(app, engine).
"""

from __future__ import annotations

import json
import logging
import uuid
from functools import wraps
from typing import Any, Callable
import os

from flask import Flask, jsonify, redirect, request, make_response
from sqlalchemy.engine import Engine

from auth import google as google_auth
from auth import session as sess
from auth import store
from auth import telegram as tg_auth

_log = logging.getLogger(__name__)

# Cookie с state для CSRF в Google OAuth (короткоживущая).
_GOOGLE_STATE_COOKIE = "ivan_oauth_state"


def _public_front_url(path: str = "/") -> str:
    """Куда редиректить после логина/логаута (терминал на том же хосте)."""
    base = (os.environ.get("PUBLIC_BASE_URL") or request.host_url).rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def _set_session_cookie(resp, user_id: str):
    token = sess.issue_session_token(user_id)
    resp.set_cookie(
        sess.COOKIE_NAME,
        token,
        max_age=sess.MAX_AGE_SEC,
        httponly=True,
        samesite="Lax",
        secure=sess.cookie_secure(),
        path="/",
    )
    return resp


def _clear_session_cookie(resp):
    resp.set_cookie(
        sess.COOKIE_NAME,
        "",
        max_age=0,
        httponly=True,
        samesite="Lax",
        secure=sess.cookie_secure(),
        path="/",
    )
    return resp


def _current_user_id() -> str | None:
    raw = request.cookies.get(sess.COOKIE_NAME)
    if not raw:
        return None
    return sess.parse_session_token(raw)


def register_auth_routes(app: Flask, engine: Engine) -> None:
    """Регистрирует все /api/auth/* и /api/me* на Flask-приложении."""
    store.init_auth_db(engine)

    def require_user(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            uid = _current_user_id()
            if not uid:
                return jsonify({"error": "unauthorized"}), 401
            user = store.get_user(engine, uid)
            if not user:
                return jsonify({"error": "unauthorized"}), 401
            return fn(user, *args, **kwargs)

        return wrapper

    @app.get("/api/auth/providers")
    def auth_providers():
        """Какие провайдеры настроены — фронт прячет недоступные кнопки."""
        return jsonify(
            {
                "google": google_auth.configured(),
                "telegram": tg_auth.configured(),
                "telegramBotUsername": tg_auth.bot_username(),
            }
        )

    @app.get("/api/me")
    def api_me():
        uid = _current_user_id()
        if not uid:
            return jsonify({"user": None})
        user = store.get_user(engine, uid)
        if not user:
            return jsonify({"user": None})
        return jsonify(
            {
                "user": {
                    "id": user["id"],
                    "email": user.get("email"),
                    "displayName": user.get("display_name"),
                    "avatarUrl": user.get("avatar_url"),
                }
            }
        )

    # ── Google ──────────────────────────────────────────────────────────────

    @app.get("/api/auth/google")
    def auth_google_start():
        if not google_auth.configured():
            return jsonify({"error": "Google OAuth не настроен"}), 503
        state = google_auth.new_state()
        # next= — куда вернуть пользователя после логина (относительный путь).
        nxt = (request.args.get("next") or "/").strip()
        if not nxt.startswith("/") or nxt.startswith("//"):
            nxt = "/"
        url = google_auth.build_authorize_url(state)
        resp = make_response(redirect(url))
        # state + next в cookie, чтобы callback мог проверить CSRF и вернуть на страницу.
        resp.set_cookie(
            _GOOGLE_STATE_COOKIE,
            json.dumps({"state": state, "next": nxt}),
            max_age=600,
            httponly=True,
            samesite="Lax",
            secure=sess.cookie_secure(),
            path="/",
        )
        return resp

    @app.get("/api/auth/google/callback")
    def auth_google_callback():
        if not google_auth.configured():
            return jsonify({"error": "Google OAuth не настроен"}), 503

        err = request.args.get("error")
        if err:
            _log.warning("Google OAuth error: %s", err)
            return redirect(_public_front_url("/?auth=error&provider=google"))

        code = request.args.get("code")
        state = request.args.get("state")
        raw_cookie = request.cookies.get(_GOOGLE_STATE_COOKIE) or ""
        try:
            cookie_data = json.loads(raw_cookie) if raw_cookie else {}
        except json.JSONDecodeError:
            cookie_data = {}
        expected = cookie_data.get("state")
        nxt = cookie_data.get("next") or "/"
        if not code or not state or not expected or state != expected:
            return redirect(_public_front_url("/?auth=error&provider=google&reason=state"))

        try:
            info = google_auth.exchange_code(code)
        except Exception as exc:  # noqa: BLE001 — отдаём дружественный редирект
            _log.exception("Google exchange failed: %s", exc)
            return redirect(_public_front_url("/?auth=error&provider=google&reason=exchange"))

        user = store.upsert_oauth_user(
            engine,
            provider="google",
            provider_user_id=str(info["sub"]),
            email=info.get("email"),
            display_name=info.get("name") or info.get("email"),
            avatar_url=info.get("picture"),
            user_id=str(uuid.uuid4()),
            raw_profile=json.dumps(info, ensure_ascii=False, sort_keys=True),
        )

        # next с query ?auth=ok — фронт подхватит и сделает merge watchlist.
        sep = "&" if "?" in nxt else "?"
        dest = _public_front_url(f"{nxt}{sep}auth=ok&provider=google")
        resp = make_response(redirect(dest))
        _set_session_cookie(resp, user["id"])
        resp.set_cookie(_GOOGLE_STATE_COOKIE, "", max_age=0, path="/")
        return resp

    # ── Telegram ────────────────────────────────────────────────────────────

    @app.post("/api/auth/telegram")
    def auth_telegram():
        if not tg_auth.configured():
            return jsonify({"error": "Telegram Login не настроен"}), 503
        payload = request.get_json(silent=True) or {}
        try:
            profile = tg_auth.verify_login(payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # noqa: BLE001
            _log.exception("Telegram verify failed: %s", exc)
            return jsonify({"error": "telegram verification failed"}), 500

        user = store.upsert_oauth_user(
            engine,
            provider="telegram",
            provider_user_id=profile["id"],
            email=None,
            display_name=profile["display_name"],
            avatar_url=profile.get("avatar_url"),
            user_id=str(uuid.uuid4()),
            raw_profile=profile.get("raw"),
        )
        body = {
            "user": {
                "id": user["id"],
                "email": user.get("email"),
                "displayName": user.get("display_name"),
                "avatarUrl": user.get("avatar_url"),
            }
        }
        resp = make_response(jsonify(body))
        _set_session_cookie(resp, user["id"])
        return resp

    # ── Logout ──────────────────────────────────────────────────────────────

    @app.post("/api/auth/logout")
    def auth_logout():
        resp = make_response(jsonify({"ok": True}))
        _clear_session_cookie(resp)
        return resp

    # ── Watchlist ───────────────────────────────────────────────────────────

    @app.get("/api/me/watchlist")
    @require_user
    def get_me_watchlist(user: dict[str, Any]):
        ids = store.get_watchlist(engine, user["id"])
        return jsonify({"ids": ids})

    @app.put("/api/me/watchlist")
    @require_user
    def put_me_watchlist(user: dict[str, Any]):
        body = request.get_json(silent=True) or {}
        ids = body.get("ids")
        if not isinstance(ids, list):
            return jsonify({"error": "ids must be a list"}), 400
        saved = store.set_watchlist(engine, user["id"], [str(x) for x in ids])
        return jsonify({"ids": saved})

    @app.post("/api/me/watchlist/merge")
    @require_user
    def merge_me_watchlist(user: dict[str, Any]):
        """Сливает локальный список с серверным после логина."""
        body = request.get_json(silent=True) or {}
        local = body.get("ids")
        if not isinstance(local, list):
            return jsonify({"error": "ids must be a list"}), 400
        merged = store.merge_watchlist(engine, user["id"], [str(x) for x in local])
        return jsonify({"ids": merged})
