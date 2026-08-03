"""
Тонкая обёртка над Telegram Bot API для постинга в канал.

Нужны:
  TELEGRAM_BOT_TOKEN  — тот же бот, что для Login Widget (или отдельный)
  TELEGRAM_CHANNEL_ID — @channel_username или числовой id (-100…)

Бот должен быть админом канала с правом публиковать сообщения.
"""

from __future__ import annotations

import os
from typing import Any

import requests

API = "https://api.telegram.org"


class TelegramBotError(RuntimeError):
    pass


def configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHANNEL_ID"))


def _token() -> str:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise TelegramBotError("TELEGRAM_BOT_TOKEN не задан")
    return token


def _chat_id() -> str:
    chat = (os.environ.get("TELEGRAM_CHANNEL_ID") or "").strip()
    if not chat:
        raise TelegramBotError("TELEGRAM_CHANNEL_ID не задан")
    return chat


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


def send_photo(png: bytes, caption: str, *, filename: str = "ivan.png") -> str | None:
    """Отправляет фото с подписью. Возвращает message_id или None."""
    # Лимит caption у sendPhoto — 1024; наш формат ≤250.
    result = _call(
        "sendPhoto",
        data={
            "chat_id": _chat_id(),
            "caption": caption[:1024],
            "disable_notification": "false",
        },
        files={"photo": (filename, png, "image/png")},
    )
    mid = result.get("message_id")
    return str(mid) if mid is not None else None


def send_message(text: str) -> str | None:
    """Текстовый пост (summary) без картинки."""
    result = _call(
        "sendMessage",
        data={
            "chat_id": _chat_id(),
            "text": text[:4096],
            "disable_web_page_preview": "true",
        },
    )
    mid = result.get("message_id")
    return str(mid) if mid is not None else None
