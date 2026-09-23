"""
Маппинг индекс → Telegram-канал.

Приоритет для каждого index_id:
1. TELEGRAM_CHANNEL_<ID>     (например TELEGRAM_CHANNEL_VIX=@ivan_vix)
2. JSON TELEGRAM_CHANNELS    ({"vix":"@ivan_vix","fng":"@ivan_fng",...})

Summary (дайджест дня):
1. TELEGRAM_SUMMARY_CHANNEL_ID
2. TELEGRAM_CHANNEL_ID       (старый единый канал — только для summary)

Бот должен быть админом каждого канала.
"""

from __future__ import annotations

import json
import logging
import os

from indices.registry import INDEX_IDS

_log = logging.getLogger(__name__)


def _normalize_chat(raw: str | None) -> str | None:
    if not raw:
        return None
    chat = raw.strip()
    return chat or None


def _channels_from_json() -> dict[str, str]:
    raw = (os.environ.get("TELEGRAM_CHANNELS") or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        _log.error("TELEGRAM_CHANNELS: невалидный JSON")
        return {}
    if not isinstance(data, dict):
        _log.error("TELEGRAM_CHANNELS: ожидается объект {index_id: chat_id}")
        return {}
    out: dict[str, str] = {}
    for key, val in data.items():
        chat = _normalize_chat(str(val) if val is not None else None)
        if chat:
            out[str(key).strip().lower()] = chat
    return out


def channel_for_index(index_id: str) -> str | None:
    """Chat id канала для индекса или None, если не настроен."""
    env_key = f"TELEGRAM_CHANNEL_{index_id.upper()}"
    chat = _normalize_chat(os.environ.get(env_key))
    if chat:
        return chat
    return _channels_from_json().get(index_id.lower())


def summary_channel() -> str | None:
    """Куда слать дневной summary; None — summary не отправлять."""
    return _normalize_chat(os.environ.get("TELEGRAM_SUMMARY_CHANNEL_ID")) or _normalize_chat(
        os.environ.get("TELEGRAM_CHANNEL_ID")
    )


def mapped_channels() -> dict[str, str]:
    """Все настроенные пары index_id → chat_id (только известные индексы)."""
    from_json = _channels_from_json()
    out: dict[str, str] = {}
    for iid in INDEX_IDS:
        chat = _normalize_chat(os.environ.get(f"TELEGRAM_CHANNEL_{iid.upper()}")) or from_json.get(iid)
        if chat:
            out[iid] = chat
    return out


def feed_configured() -> bool:
    """Токен бота + хотя бы один канал индекса."""
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    return bool(token and mapped_channels())


def missing_index_channels(index_ids: list[str] | None = None) -> list[str]:
    """id индексов без канала — для диагностики."""
    ids = list(index_ids) if index_ids is not None else list(INDEX_IDS)
    return [iid for iid in ids if not channel_for_index(iid)]
