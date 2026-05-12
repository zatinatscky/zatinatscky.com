#!/usr/bin/env python3
"""
CLI-скрипт синхронизации индекса Fear & Greed в БД.

На Render: задайте DATABASE_URL (PostgreSQL).
Локально без DATABASE_URL: данные пишутся в SQLite ./data/fear_greed.db.
"""

from __future__ import annotations

from fng_data import full_refresh, get_engine


def main() -> None:
    engine = get_engine()
    count = full_refresh(engine)
    dialect = engine.dialect.name
    print(f"Fear & Greed sync done. Upserted rows: {count}. Backend: {dialect}")


if __name__ == "__main__":
    main()
