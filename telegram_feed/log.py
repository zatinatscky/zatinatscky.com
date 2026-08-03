"""
Журнал опубликованных постов — чтобы повторный cron не слал то же наблюдение дважды.

Таблица telegram_post_log:
  index_id         — id индекса или '__summary__'
  observation_date — дата точки данных (YYYY-MM-DD), которую запостили
  posted_at        — когда отправили (UTC ISO)
  tg_message_id    — id сообщения в канале (если API вернул)
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

SUMMARY_ID = "__summary__"

_DDL = """
CREATE TABLE IF NOT EXISTS telegram_post_log (
    index_id TEXT NOT NULL,
    observation_date TEXT NOT NULL,
    posted_at TEXT NOT NULL,
    tg_message_id TEXT,
    PRIMARY KEY (index_id, observation_date)
)
"""


def init_post_log(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(_DDL))


def already_posted(engine: Engine, index_id: str, observation_date: str) -> bool:
    init_post_log(engine)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT 1 FROM telegram_post_log
                 WHERE index_id = :id AND observation_date = :d
                """
            ),
            {"id": index_id, "d": observation_date},
        ).first()
    return row is not None


def mark_posted(
    engine: Engine,
    index_id: str,
    observation_date: str,
    *,
    tg_message_id: str | None = None,
) -> None:
    init_post_log(engine)
    now = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO telegram_post_log (index_id, observation_date, posted_at, tg_message_id)
                VALUES (:id, :d, :ts, :mid)
                ON CONFLICT (index_id, observation_date) DO UPDATE SET
                    posted_at = EXCLUDED.posted_at,
                    tg_message_id = COALESCE(EXCLUDED.tg_message_id, telegram_post_log.tg_message_id)
                """
            ),
            {"id": index_id, "d": observation_date, "ts": now, "mid": tg_message_id},
        )
