"""
CLI: сгенерировать дневной Telegram-фид (картинки + FEED.md).

Примеры:
  python -m telegram_feed                         # все индексы, сегодня UTC
  python -m telegram_feed --out /tmp/ivan-feed
  python -m telegram_feed vix spx brent           # только указанные
  python -m telegram_feed --as-of 2026-08-03
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from telegram_feed.card import feed_index_ids, render_day_feed
from telegram_feed.from_api import render_day_feed_from_api
from telegram_feed.theme import EXCLUDED_IDS


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Render IVAN Telegram daily feed cards")
    p.add_argument(
        "indexes",
        nargs="*",
        help="id индексов (по умолчанию все)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("telegram_feed/out"),
        help="каталог для png / txt / FEED.md",
    )
    p.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="дата YYYY-MM-DD (UTC), по умолчанию сегодня (только режим БД)",
    )
    p.add_argument(
        "--from-api",
        action="store_true",
        help="взять ряды с публичного /api/indexes (без Postgres)",
    )
    p.add_argument(
        "--api-base",
        default="https://ivan.zatinatscky.com",
        help="база для --from-api",
    )
    args = p.parse_args(argv)

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    only = args.indexes or None
    if only:
        bad = [i for i in only if i in EXCLUDED_IDS]
        if bad:
            print(f"Пропуск исключённых: {', '.join(bad)}", file=sys.stderr)
            only = [i for i in only if i not in EXCLUDED_IDS]
        if not only:
            print("Нечего рендерить.", file=sys.stderr)
            return 2

    if args.from_api:
        if as_of:
            print("Замечание: --as-of игнорируется в режиме --from-api", file=sys.stderr)
        cards = render_day_feed_from_api(args.out, base_url=args.api_base, only=only)
    else:
        from fng_data import get_engine

        cards = render_day_feed(get_engine(), args.out, as_of=as_of, only=only)
    print(f"Rendered {len(cards)} cards → {args.out.resolve()}")
    for c in cards:
        print(f"  {c.index_id:12}  caption {c.caption_len}/250  as_of={c.as_of}")
    if not cards:
        print("No cards. Check DB / sync.", file=sys.stderr)
        print("Available:", ", ".join(feed_index_ids()))
        return 1
    print(f"Review: {args.out.resolve() / 'FEED.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
