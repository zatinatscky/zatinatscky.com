"""
Ежедневный постинг карточек индексов в Telegram — по одному каналу на индекс.

План:
1. После indices.sync выбрать индексы со свежим наблюдением (ещё не пощенные).
2. Для каждого с настроенным TELEGRAM_CHANNEL_<ID> — PNG + caption в свой канал.
3. Опционально summary в TELEGRAM_SUMMARY_CHANNEL_ID / TELEGRAM_CHANNEL_ID.
4. Идемпотентность через telegram_post_log.

Запуск:
  python -m telegram_feed.publish
  python -m telegram_feed.publish --dry-run
  python -m telegram_feed.publish vix spx
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy.engine import Engine

from indices.registry import BY_ID
from indices.store import load_points
from telegram_feed import bot
from telegram_feed.card import FeedCard, build_card, feed_index_ids
from telegram_feed.channels import (
    channel_for_index,
    feed_configured,
    mapped_channels,
    missing_index_channels,
    summary_channel,
)
from telegram_feed.log import SUMMARY_ID, already_posted, init_post_log, mark_posted
from telegram_feed.theme import DOMAIN_EMOJI, EXCLUDED_IDS

_log = logging.getLogger(__name__)

POST_PAUSE_SEC = 2.5
FRESH_MAX_AGE_DAYS = 3


@dataclass(frozen=True)
class PublishItem:
    index_id: str
    observation_date: str
    card: FeedCard
    delta_1d: float | None
    pct: bool
    chat_id: str


def _env_enabled() -> bool:
    raw = (os.environ.get("TELEGRAM_FEED_ENABLED") or "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def latest_observation(engine: Engine, index_id: str) -> tuple[str, float] | None:
    points = load_points(engine, index_id, since=None)
    if not points:
        return None
    return points[-1]


def is_fresh(observation_date: str, as_of: date) -> bool:
    try:
        obs = date.fromisoformat(observation_date)
    except ValueError:
        return False
    return (as_of - obs).days <= FRESH_MAX_AGE_DAYS


def select_to_publish(
    engine: Engine,
    *,
    as_of: date,
    only: list[str] | None = None,
    force: bool = False,
) -> list[PublishItem]:
    """Индексы со свежим непостилленным наблюдением и настроенным каналом."""
    init_post_log(engine)
    ids = only or feed_index_ids()
    items: list[PublishItem] = []

    for iid in ids:
        if iid in EXCLUDED_IDS:
            continue
        if iid not in BY_ID:
            _log.warning("Неизвестный индекс %s — пропуск", iid)
            continue

        chat = channel_for_index(iid)
        if not chat:
            _log.warning("%s: канал не задан (TELEGRAM_CHANNEL_%s) — пропуск", iid, iid.upper())
            continue

        latest = latest_observation(engine, iid)
        if not latest:
            _log.info("%s: нет точек в БД", iid)
            continue
        obs_date, _ = latest
        if not is_fresh(obs_date, as_of):
            _log.info("%s: последнее наблюдение %s устарело (as_of=%s)", iid, obs_date, as_of)
            continue
        if not force and already_posted(engine, iid, obs_date):
            _log.info("%s: %s уже опубликован", iid, obs_date)
            continue
        try:
            card = build_card(engine, iid, as_of=as_of)
        except Exception:  # noqa: BLE001
            _log.exception("%s: не удалось собрать карточку", iid)
            continue

        spec = BY_ID[iid]
        series_pts = load_points(engine, iid, since=None)
        d1 = None
        if len(series_pts) >= 2:
            cur, prev = series_pts[-1][1], series_pts[-2][1]
            if spec.pct:
                d1 = (cur / prev - 1.0) * 100.0 if prev else None
            else:
                d1 = cur - prev

        items.append(
            PublishItem(
                index_id=iid,
                observation_date=obs_date,
                card=card,
                delta_1d=d1,
                pct=spec.pct,
                chat_id=chat,
            )
        )
    return items


def _fmt_mover(item: PublishItem) -> str:
    emoji = DOMAIN_EMOJI.get(item.card.domain, "▪️")
    d = item.delta_1d
    if d is None:
        arrow, body = "➡️", "n/a"
    elif abs(d) < 1e-12:
        arrow, body = "➡️", "0"
    else:
        arrow = "📈" if d > 0 else "📉"
        body = f"{d:+.2f}%" if item.pct else f"{d:+.2f}"
    return f"{arrow} {emoji} {item.card.name}: {body}"


def build_summary(items: list[PublishItem], *, as_of: date) -> str:
    n = len(items)
    lines = [f"IVAN sync done · {n} index{'es' if n != 1 else ''} updated"]
    movers = [i for i in items if i.delta_1d is not None]
    movers.sort(key=lambda i: abs(i.delta_1d or 0), reverse=True)
    top = movers[:5]
    if top:
        lines.append("Movers:")
        lines.extend(_fmt_mover(i) for i in top)
    lines += [
        "Full board → https://ivan.zatinatscky.com/",
        "——",
        f"IVAN · as of {as_of.isoformat()} UTC · NFA",
    ]
    return "\n".join(lines)


def publish_daily(
    engine: Engine,
    *,
    as_of: date | None = None,
    only: list[str] | None = None,
    dry_run: bool = False,
    force: bool = False,
    pause_sec: float = POST_PAUSE_SEC,
) -> int:
    """Публикует карточки: каждый индекс → свой канал. Возвращает число постов."""
    day = as_of or datetime.now(tz=timezone.utc).date()

    if not _env_enabled():
        _log.info("TELEGRAM_FEED_ENABLED выключен — выход")
        return 0
    if not dry_run and not feed_configured():
        _log.warning(
            "Telegram feed пропущен: нужен TELEGRAM_BOT_TOKEN и хотя бы один "
            "TELEGRAM_CHANNEL_<ID> (сейчас каналов: %s)",
            len(mapped_channels()),
        )
        return 0

    missing = missing_index_channels(only)
    if missing:
        _log.warning("Без канала (не будут поститься): %s", ", ".join(missing))

    items = select_to_publish(engine, as_of=day, only=only, force=force)
    if not items:
        _log.info("Нечего постить за %s", day.isoformat())
        return 0

    _log.info(
        "К публикации: %s — %s",
        len(items),
        ", ".join(f"{i.index_id}→{i.chat_id}" for i in items),
    )
    posted = 0

    for i, item in enumerate(items):
        card = item.card
        _log.info(
            "[%s/%s] %s → %s obs=%s caption=%s/250",
            i + 1,
            len(items),
            item.index_id,
            item.chat_id,
            item.observation_date,
            card.caption_len,
        )
        if dry_run:
            _log.info("dry-run caption:\n%s", card.caption)
            posted += 1
        else:
            try:
                mid = bot.send_photo(
                    card.image_png,
                    card.caption,
                    chat_id=item.chat_id,
                    filename=f"{item.index_id}.png",
                )
                mark_posted(engine, item.index_id, item.observation_date, tg_message_id=mid)
                posted += 1
            except Exception:  # noqa: BLE001
                _log.exception("Не удалось отправить %s → %s", item.index_id, item.chat_id)

        if i < len(items) - 1 and pause_sec > 0:
            time.sleep(pause_sec)

    # Summary — только если задан отдельный/legacy канал.
    hub = summary_channel()
    summary = build_summary(items, as_of=day)
    if not hub:
        _log.info("Summary пропущен: TELEGRAM_SUMMARY_CHANNEL_ID / TELEGRAM_CHANNEL_ID не задан")
    elif dry_run:
        _log.info("dry-run summary → %s:\n%s", hub, summary)
    elif not already_posted(engine, SUMMARY_ID, day.isoformat()) or force:
        try:
            if pause_sec > 0:
                time.sleep(pause_sec)
            mid = bot.send_message(summary, chat_id=hub)
            mark_posted(engine, SUMMARY_ID, day.isoformat(), tg_message_id=mid)
            _log.info("Summary → %s", hub)
        except Exception:  # noqa: BLE001
            _log.exception("Не удалось отправить summary → %s", hub)
    else:
        _log.info("Summary за %s уже был", day.isoformat())

    return posted


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    p = argparse.ArgumentParser(description="Publish IVAN daily index cards to per-index Telegram channels")
    p.add_argument("indexes", nargs="*", help="только эти id (по умолчанию все с настроенным каналом)")
    p.add_argument("--as-of", type=str, default=None, help="YYYY-MM-DD UTC")
    p.add_argument("--dry-run", action="store_true", help="собрать карточки, не слать в Telegram")
    p.add_argument("--force", action="store_true", help="игнорировать telegram_post_log (репост)")
    p.add_argument("--pause", type=float, default=POST_PAUSE_SEC, help="пауза между постами, сек")
    p.add_argument(
        "--list-channels",
        action="store_true",
        help="показать маппинг индекс→канал и выйти",
    )
    args = p.parse_args(argv)

    if args.list_channels:
        mapped = mapped_channels()
        print(f"Mapped {len(mapped)}/14 channels:")
        for iid in feed_index_ids():
            chat = mapped.get(iid)
            print(f"  {iid:12}  {chat or '(missing)'}")
        hub = summary_channel()
        print(f"Summary channel: {hub or '(none)'}")
        return 0

    only = args.indexes or None
    if only:
        only = [i for i in only if i not in EXCLUDED_IDS]
        if not only:
            print("Нечего постить (все id исключены).", file=sys.stderr)
            return 2

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    from fng_data import get_engine

    n = publish_daily(
        get_engine(),
        as_of=as_of,
        only=only,
        dry_run=args.dry_run,
        force=args.force,
        pause_sec=args.pause,
    )
    print(f"Published cards: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
