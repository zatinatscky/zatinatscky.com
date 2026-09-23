"""
Telegram Login Widget.

Виджет на фронте (https://core.telegram.org/widgets/login) после авторизации
POST'ит данные на /api/auth/telegram. Мы проверяем HMAC-подпись по bot token
и создаём/находим пользователя.

Нужны env:
  TELEGRAM_BOT_TOKEN   — токен бота от @BotFather
  TELEGRAM_BOT_USERNAME — username бота без @ (для data-telegram-login на фронте)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time

_log = logging.getLogger(__name__)

# Данные от виджета старше этого окна считаем протухшими (защита от replay).
MAX_AUTH_AGE_SEC = 60 * 60 * 24  # 24 часа — как рекомендует Telegram docs


def configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_BOT_USERNAME"))


def bot_username() -> str | None:
    name = (os.environ.get("TELEGRAM_BOT_USERNAME") or "").lstrip("@").strip()
    return name or None


def verify_login(payload: dict) -> dict:
    """
    Проверяет подпись Telegram Login Widget и возвращает нормализованный профиль.

    Ожидаемые поля payload: id, first_name, auth_date, hash, опционально
    last_name, username, photo_url.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")

    check_hash = str(payload.get("hash") or "")
    if not check_hash:
        raise ValueError("Нет hash в данных Telegram")

    # Собираем data-check-string: все поля кроме hash, отсортированные.
    pairs = []
    for key in sorted(payload.keys()):
        if key == "hash":
            continue
        val = payload.get(key)
        if val is None or val == "":
            continue
        pairs.append(f"{key}={val}")
    data_check = "\n".join(pairs)

    secret_key = hashlib.sha256(token.encode("utf-8")).digest()
    computed = hmac.new(secret_key, data_check.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, check_hash):
        raise ValueError("Неверная подпись Telegram")

    try:
        auth_date = int(payload.get("auth_date") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Некорректный auth_date") from exc
    if auth_date <= 0 or abs(time.time() - auth_date) > MAX_AUTH_AGE_SEC:
        raise ValueError("Данные Telegram протухли")

    tg_id = str(payload.get("id") or "")
    if not tg_id:
        raise ValueError("Нет id пользователя Telegram")

    first = str(payload.get("first_name") or "").strip()
    last = str(payload.get("last_name") or "").strip()
    username = str(payload.get("username") or "").strip()
    display = " ".join(p for p in (first, last) if p).strip()
    if not display:
        display = f"@{username}" if username else f"Telegram {tg_id}"

    return {
        "id": tg_id,
        "display_name": display,
        "username": username or None,
        "avatar_url": payload.get("photo_url") or None,
        "raw": json.dumps(payload, ensure_ascii=False, sort_keys=True),
    }
