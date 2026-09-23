"""
Хранение рядов индексов.

Две таблицы:
- index_meta        — по строке на индекс: описание + результат последней синхронизации;
- index_observation — «длинный» формат (index_id, date_utc, value), одна точка на день.

Длинный формат выбран сознательно: у индексов разная частота (дневная у бирж,
месячная у CPI/PMI/GSCPI) и разная глубина истории, поэтому ни широкая таблица,
ни отдельная таблица на индекс не подходят.

date_utc храним строкой ISO 'YYYY-MM-DD' одинаково в Postgres и SQLite — это
избавляет от расхождений в типах дат между диалектами при чтении в pandas.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .registry import SPECS, IndexSpec, meta_dict

_log = logging.getLogger(__name__)

# Точка ряда: ISO-дата (UTC) и значение.
Point = tuple[str, float]


_DDL_META = """
CREATE TABLE IF NOT EXISTS index_meta (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT,
    sub TEXT,
    country TEXT,
    source TEXT,
    url TEXT,
    unit TEXT,
    pre TEXT,
    dec_places INTEGER,
    pct INTEGER,
    gauge INTEGER,
    measures TEXT,
    method TEXT,
    behaviour TEXT,
    reading TEXT,
    last_sync_utc TEXT,
    last_error TEXT,
    point_count INTEGER,
    last_observation TEXT
)
"""

_DDL_OBS = """
CREATE TABLE IF NOT EXISTS index_observation (
    index_id TEXT NOT NULL,
    date_utc TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION,
    PRIMARY KEY (index_id, date_utc)
)
"""

# Первичный ключ (index_id, date_utc) уже покрывает выборку «ряд за период»,
# но явный индекс нужен для ORDER BY date_utc DESC при поиске последней точки.
_DDL_OBS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_index_observation_id_date
    ON index_observation (index_id, date_utc DESC)
"""


def init_db(engine: Engine) -> None:
    """Создаёт таблицы индексов, если их ещё нет. Идемпотентно."""
    with engine.begin() as conn:
        conn.execute(text(_DDL_META))
        conn.execute(text(_DDL_OBS))
        conn.execute(text(_DDL_OBS_INDEX))
    _ensure_columns(engine)


# Столбцы, добавленные после первого релиза схемы: CREATE TABLE IF NOT EXISTS их
# не подтянет на уже существующей таблице, поэтому досоздаём отдельно.
_ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("index_observation", "volume", "DOUBLE PRECISION"),
    ("index_meta", "behaviour", "TEXT"),
    ("index_meta", "reading", "TEXT"),
    ("index_meta", "last_observation", "TEXT"),
)


def _ensure_columns(engine: Engine) -> None:
    """Мягкая миграция: добавляет недостающие столбцы в уже созданные таблицы."""
    insp = inspect(engine)
    for table, column, coltype in _ADDED_COLUMNS:
        if not insp.has_table(table):
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        if column in existing:
            continue
        _log.info("Миграция: добавляю %s.%s", table, column)
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))


def _excluded(engine: Engine) -> str:
    """Псевдотаблица конфликтующей строки: EXCLUDED в Postgres, excluded в SQLite."""
    return "EXCLUDED" if engine.dialect.name == "postgresql" else "excluded"


def upsert_meta(engine: Engine, specs: tuple[IndexSpec, ...] = SPECS) -> int:
    """Синхронизирует справочник index_meta с registry.py, не затирая статусы синхронизации."""
    init_db(engine)
    ex = _excluded(engine)
    sql = text(
        f"""
        INSERT INTO index_meta (
            id, name, domain, sub, country, source, url,
            unit, pre, dec_places, pct, gauge, measures, method, behaviour, reading
        ) VALUES (
            :id, :name, :domain, :sub, :country, :source, :url,
            :unit, :pre, :dec_places, :pct, :gauge, :measures, :method, :behaviour, :reading
        )
        ON CONFLICT (id) DO UPDATE SET
            name = {ex}.name,
            domain = {ex}.domain,
            sub = {ex}.sub,
            country = {ex}.country,
            source = {ex}.source,
            url = {ex}.url,
            unit = {ex}.unit,
            pre = {ex}.pre,
            dec_places = {ex}.dec_places,
            pct = {ex}.pct,
            gauge = {ex}.gauge,
            measures = {ex}.measures,
            method = {ex}.method,
            behaviour = {ex}.behaviour,
            reading = {ex}.reading
        """
    )
    with engine.begin() as conn:
        for spec in specs:
            m = meta_dict(spec)
            conn.execute(
                sql,
                {
                    "id": m["id"],
                    "name": m["name"],
                    "domain": m["domain"],
                    "sub": m["sub"],
                    "country": m["country"],
                    "source": m["source"],
                    "url": m["url"],
                    "unit": m["unit"],
                    "pre": m["pre"],
                    "dec_places": m["dec"],
                    "pct": 1 if m["pct"] else 0,
                    "gauge": 1 if m["gauge"] else 0,
                    "measures": m["measures"],
                    "method": m["method"],
                    "behaviour": m["behaviour"],
                    "reading": m["reading"],
                },
            )
    return len(specs)


def upsert_points(
    engine: Engine,
    index_id: str,
    points: list[Point],
    volumes: dict[str, float] | None = None,
) -> int:
    """
    Пишет точки ряда одного индекса. Повторный запуск обновляет значения,
    поэтому ревизии данных на стороне источника подхватываются сами.

    volumes — оборот рынка по дням (см. indices/volumes.py). Пишется в ту же
    строку, что и значение индекса, поэтому объём в БД всегда сопоставлен
    конкретной дате конкретного индекса, а не лежит отдельным глобальным рядом.
    """
    if not points:
        return 0

    vol = volumes or {}
    ex = _excluded(engine)
    sql = text(
        f"""
        INSERT INTO index_observation (index_id, date_utc, value, volume)
        VALUES (:index_id, :date_utc, :value, :volume)
        ON CONFLICT (index_id, date_utc) DO UPDATE SET
            value = {ex}.value,
            volume = {ex}.volume
        """
    )
    rows = [
        {
            "index_id": index_id,
            "date_utc": d,
            "value": float(v),
            "volume": vol.get(d),
        }
        for d, v in points
        if v is not None
    ]
    if not rows:
        return 0

    with engine.begin() as conn:
        # executemany: на 1500 точек это один round-trip вместо полутора тысяч.
        conn.execute(sql, rows)
    return len(rows)


def mark_sync(
    engine: Engine,
    index_id: str,
    error: str | None,
    point_count: int,
    last_observation: str | None = None,
) -> None:
    """
    Фиксирует результат синхронизации индекса.

    Хранится в БД, а не в логах, чтобы состояние ежедневного джоба можно было
    проверить одним запросом (или через /api/indexes/status).
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE index_meta
                   SET last_sync_utc = :ts,
                       last_error = :err,
                       point_count = :n,
                       last_observation = :last_obs
                 WHERE id = :id
                """
            ),
            {
                "ts": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
                "err": error,
                "n": point_count,
                "last_obs": last_observation,
                "id": index_id,
            },
        )


def load_points(engine: Engine, index_id: str, since: str | None = None) -> list[Point]:
    """Читает ряд индекса по возрастанию даты; since — нижняя граница включительно."""
    sql = "SELECT date_utc, value FROM index_observation WHERE index_id = :id"
    params: dict[str, object] = {"id": index_id}
    if since:
        sql += " AND date_utc >= :since"
        params["since"] = since
    sql += " ORDER BY date_utc"

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    return [(str(r[0])[:10], float(r[1])) for r in rows]


def load_all_points(
    engine: Engine, since: str | None = None
) -> tuple[dict[str, list[Point]], dict[str, list[Point]]]:
    """
    Читает ряды всех индексов одним запросом.

    Возвращает (значения, объёмы): отдельный SELECT на каждый индекс — лишние
    round-trip'ы к БД на каждый заход на страницу. В объёмы попадают только те
    индексы, у которых он вообще есть (столбец volume не NULL).
    """
    sql = "SELECT index_id, date_utc, value, volume FROM index_observation"
    params: dict[str, object] = {}
    if since:
        sql += " WHERE date_utc >= :since"
        params["since"] = since
    sql += " ORDER BY index_id, date_utc"

    values: dict[str, list[Point]] = {}
    volumes: dict[str, list[Point]] = {}
    with engine.connect() as conn:
        for index_id, date_utc, value, volume in conn.execute(text(sql), params):
            key, day = str(index_id), str(date_utc)[:10]
            values.setdefault(key, []).append((day, float(value)))
            if volume is not None:
                volumes.setdefault(key, []).append((day, float(volume)))
    return values, volumes


def load_sync_status(engine: Engine) -> dict[str, dict]:
    """Статус последней синхронизации по индексам — для отладки и /api/indexes/status."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, last_sync_utc, last_error, point_count, last_observation
                  FROM index_meta ORDER BY id
                """
            )
        ).fetchall()
    return {
        str(r[0]): {
            "last_sync_utc": r[1],
            "last_error": r[2],
            "point_count": r[3],
            "last_observation": r[4],
        }
        for r in rows
    }


def coverage(engine: Engine) -> list[tuple[str, int, str, str, int]]:
    """
    (index_id, точек, первая дата, последняя дата, точек с объёмом).

    Последнее поле показывает, у скольких значений индекса есть сопоставленный
    оборот рынка — по нему видно, что объём лёг именно на те даты, что и ряд.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT index_id,
                       COUNT(*),
                       MIN(date_utc),
                       MAX(date_utc),
                       COUNT(volume)
                  FROM index_observation
                 GROUP BY index_id
                """
            )
        ).fetchall()
    return [
        (str(r[0]), int(r[1]), str(r[2])[:10], str(r[3])[:10], int(r[4])) for r in rows
    ]
