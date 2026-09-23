"""
Тонкая обёртка над Telegram Bot API для постинга в каналы.

Нужны:
  TELEGRAM_BOT_TOKEN — бот (админ каждого канала)
  каналы индексов    — см. telegram_feed/channels.py
"""

from __future__ import annotations

import os
from typing import Any

import requests

API = "https://api.telegram.org"


class TelegramBotError(RuntimeError):
    pass


def _token() -> str:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise TelegramBotError("TELEGRAM_BOT_TOKEN не задан")
    return token


def _call(method: str, *, files: dict | None = None, data: dict | None = None) -> dict[str, Any]:
    url = f"{API}/bot{_token()}/{method}"
    resp = requests.post(url, data=data or {}, files=files, timeout=60)
    try:
        payload = resp.json()
    except ValueError as exc:
        raise TelegramBotError(f"Telegram non-JSON ({resp.status_code}): {resp.text[:200]}") from exc
    if not payload.get("ok"):
        raise TelegramBotError(f"Telegram {method} failed: {payload.get('description') or payload}")
    return payload.get("result") or {}


def send_photo(
    png: bytes,
    caption: str,
    *,
    chat_id: str,
    filename: str = "ivan.png",
) -> str | None:
    """Отправляет фото с подписью в указанный канал. Возвращает message_id."""
    result = _call(
        "sendPhoto",
        data={
            "chat_id": chat_id,
            "caption": caption[:1024],
            "disable_notification": "false",
        },
        files={"photo": (filename, png, "image/png")},
    )
    mid = result.get("message_id")
    return str(mid) if mid is not None else None


def send_message(text: str, *, chat_id: str) -> str | None:
    """Текстовый пост (summary) в указанный канал."""
    result = _call(
        "sendMessage",
        data={
            "chat_id": chat_id,
            "text": text[:4096],
            "disable_web_page_preview": "true",
        },
    )
    mid = result.get("message_id")
    return str(mid) if mid is not None else None
