"""
Хранение пользователей, OAuth-связок и watchlist.

Схема:
- users            — профиль (имя, email, аватар);
- oauth_identity   — привязка провайдера (google / telegram) к пользователю;
- user_watchlist   — сохранённые индексы: одна строка на (user_id, index_id).

Сессии в БД не храним: cookie подписывается SECRET_KEY (см. auth/session.py).
Этого достаточно для v1 — при компрометации SECRET_KEY все сессии сбрасываются
сменой ключа.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)

_DDL_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT,
    display_name TEXT,
    avatar_url TEXT,
    created_at TEXT NOT NULL,
    last_login_at TEXT
)
"""

_DDL_OAUTH = """
CREATE TABLE IF NOT EXISTS oauth_identity (
    provider TEXT NOT NULL,
    provider_user_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    raw_profile TEXT,
    PRIMARY KEY (provider, provider_user_id)
)
"""

_DDL_WATCHLIST = """
CREATE TABLE IF NOT EXISTS user_watchlist (
    user_id TEXT NOT NULL,
    index_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, index_id)
)
"""

_DDL_WATCHLIST_IDX = """
CREATE INDEX IF NOT EXISTS idx_user_watchlist_user
    ON user_watchlist (user_id)
"""


def init_auth_db(engine: Engine) -> None:
    """Создаёт таблицы авторизации, если их ещё нет."""
    with engine.begin() as conn:
        conn.execute(text(_DDL_USERS))
        conn.execute(text(_DDL_OAUTH))
        conn.execute(text(_DDL_WATCHLIST))
        conn.execute(text(_DDL_WATCHLIST_IDX))


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def find_user_by_oauth(engine: Engine, provider: str, provider_user_id: str) -> dict | None:
    """Находит пользователя по связке провайдера."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT u.id, u.email, u.display_name, u.avatar_url
                  FROM oauth_identity o
                  JOIN users u ON u.id = o.user_id
                 WHERE o.provider = :p AND o.provider_user_id = :pid
                """
            ),
            {"p": provider, "pid": str(provider_user_id)},
        ).mappings().first()
    return dict(row) if row else None


def get_user(engine: Engine, user_id: str) -> dict | None:
    """Профиль пользователя по id."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, email, display_name, avatar_url, created_at, last_login_at
                  FROM users WHERE id = :id
                """
            ),
            {"id": user_id},
        ).mappings().first()
    return dict(row) if row else None


def upsert_oauth_user(
    engine: Engine,
    *,
    provider: str,
    provider_user_id: str,
    email: str | None,
    display_name: str | None,
    avatar_url: str | None,
    user_id: str,
    raw_profile: str | None = None,
) -> dict:
    """
    Создаёт пользователя при первом входе или обновляет профиль при повторном.

    user_id генерирует вызывающий (uuid4), чтобы не зависеть от диалекта БД.
    """
    init_auth_db(engine)
    existing = find_user_by_oauth(engine, provider, provider_user_id)
    now = _now()

    if existing:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE users
                       SET email = COALESCE(:email, email),
                           display_name = COALESCE(:name, display_name),
                           avatar_url = COALESCE(:avatar, avatar_url),
                           last_login_at = :now
                     WHERE id = :id
                    """
                ),
                {
                    "email": email,
                    "name": display_name,
                    "avatar": avatar_url,
                    "now": now,
                    "id": existing["id"],
                },
            )
            if raw_profile is not None:
                conn.execute(
                    text(
                        """
                        UPDATE oauth_identity
                           SET raw_profile = :raw
                         WHERE provider = :p AND provider_user_id = :pid
                        """
                    ),
                    {
                        "raw": raw_profile,
                        "p": provider,
                        "pid": str(provider_user_id),
                    },
                )
        user = get_user(engine, existing["id"])
        assert user is not None
        return user

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO users (id, email, display_name, avatar_url, created_at, last_login_at)
                VALUES (:id, :email, :name, :avatar, :now, :now)
                """
            ),
            {
                "id": user_id,
                "email": email,
                "name": display_name,
                "avatar": avatar_url,
                "now": now,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO oauth_identity (provider, provider_user_id, user_id, raw_profile)
                VALUES (:p, :pid, :uid, :raw)
                """
            ),
            {
                "p": provider,
                "pid": str(provider_user_id),
                "uid": user_id,
                "raw": raw_profile,
            },
        )
    _log.info("Новый пользователь %s через %s", user_id, provider)
    user = get_user(engine, user_id)
    assert user is not None
    return user


def get_watchlist(engine: Engine, user_id: str) -> list[str]:
    """Список id индексов в watchlist пользователя, в порядке добавления."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT index_id FROM user_watchlist
                 WHERE user_id = :uid
                 ORDER BY created_at
                """
            ),
            {"uid": user_id},
        ).fetchall()
    return [str(r[0]) for r in rows]


def set_watchlist(engine: Engine, user_id: str, index_ids: list[str]) -> list[str]:
    """
    Полная замена watchlist пользователя.

    Фронтенд шлёт актуальный список после каждого изменения — проще, чем
    отдельные add/remove, и не создаёт гонок при слиянии с localStorage.
    """
    # Дедупликация с сохранением порядка.
    seen: set[str] = set()
    clean: list[str] = []
    for iid in index_ids:
        key = str(iid).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        clean.append(key)

    now = _now()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM user_watchlist WHERE user_id = :uid"), {"uid": user_id})
        for iid in clean:
            conn.execute(
                text(
                    """
                    INSERT INTO user_watchlist (user_id, index_id, created_at)
                    VALUES (:uid, :iid, :now)
                    """
                ),
                {"uid": user_id, "iid": iid, "now": now},
            )
    return clean


def merge_watchlist(engine: Engine, user_id: str, local_ids: list[str]) -> list[str]:
    """
    Сливает локальный watchlist с серверным при первом входе.

    Правило: объединение множеств, порядок — сначала серверные, потом новые
    локальные. Так звёздочки, поставленные до логина, не теряются.
    """
    server = get_watchlist(engine, user_id)
    merged = list(server)
    have = set(server)
    for iid in local_ids:
        key = str(iid).strip()
        if key and key not in have:
            merged.append(key)
            have.add(key)
    return set_watchlist(engine, user_id, merged)
