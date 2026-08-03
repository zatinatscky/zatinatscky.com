"""
Ежедневный постинг карточек индексов в Telegram-канал.

План:
1. После indices.sync выбрать индексы (все из реестра), у которых есть свежее
   наблюдение и его ещё не постили.
2. Для каждого — PNG + caption, sendPhoto, пауза 2–3 с.
3. В конце — короткий summary без картинки (сколько обновлено, топ movers).
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
from telegram_feed.log import SUMMARY_ID, already_posted, init_post_log, mark_posted
from telegram_feed.theme import DOMAIN_EMOJI, EXCLUDED_IDS

_log = logging.getLogger(__name__)

# Пауза между постами — не упираемся в flood limits Telegram.
POST_PAUSE_SEC = 2.5
# Наблюдение считается «свежим», если его дата не старше N дней от as_of
# (выходные/лаги FRED: пятничное закрытие в субботнем синке — ок).
FRESH_MAX_AGE_DAYS = 3


@dataclass(frozen=True)
class PublishItem:
    index_id: str
    observation_date: str
    card: FeedCard
    delta_1d: float | None
    pct: bool


def _env_enabled() -> bool:
    """TELEGRAM_FEED_ENABLED=false полностью глушит постинг (даже при наличии токена)."""
    raw = (os.environ.get("TELEGRAM_FEED_ENABLED") or "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def latest_observation(engine: Engine, index_id: str) -> tuple[str, float] | None:
    """Последняя РЕАЛЬНАЯ точка в БД (не forward-fill)."""
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
    """Индексы со свежим непостилленным наблюдением."""
    init_post_log(engine)
    ids = only or feed_index_ids()
    items: list[PublishItem] = []

    for iid in ids:
        if iid in EXCLUDED_IDS:
            continue
        if iid not in BY_ID:
            _log.warning("Неизвестный индекс %s — пропуск", iid)
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
            _log.info("%s: %s уже в канале", iid, obs_date)
            continue
        try:
            card = build_card(engine, iid, as_of=as_of)
        except Exception:  # noqa: BLE001
            _log.exception("%s: не удалось собрать карточку", iid)
            continue
        spec = BY_ID[iid]
        # Дельта 1d из полного ряда карточки (через caption-логику / series).
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
            )
        )
    return items


def _fmt_mover(item: PublishItem) -> str:
    emoji = DOMAIN_EMOJI.get(item.card.domain, "▪️")
    d = item.delta_1d
    if d is None:
        arrow = "➡️"
        body = "n/a"
    elif abs(d) < 1e-12:
        arrow = "➡️"
        body = "0"
    else:
        arrow = "📈" if d > 0 else "📉"
        if item.pct:
            body = f"{d:+.2f}%"
        else:
            body = f"{d:+.2f}"
    return f"{arrow} {emoji} {item.card.name}: {body}"


def build_summary(items: list[PublishItem], *, as_of: date) -> str:
    """Короткий итог дня без картинки."""
    n = len(items)
    lines = [
        f"IVAN sync done · {n} index{'es' if n != 1 else ''} updated",
    ]
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
    """
    Публикует дневной фид. Возвращает число успешно отправленных карточек
    (summary не считается).
    """
    day = as_of or datetime.now(tz=timezone.utc).date()

    if not _env_enabled():
        _log.info("TELEGRAM_FEED_ENABLED выключен — выход")
        return 0
    if not dry_run and not bot.configured():
        _log.warning(
            "Telegram feed пропущен: задайте TELEGRAM_BOT_TOKEN и TELEGRAM_CHANNEL_ID"
        )
        return 0

    items = select_to_publish(engine, as_of=day, only=only, force=force)
    if not items:
        _log.info("Нечего постить за %s", day.isoformat())
        return 0

    _log.info("К публикации: %s (%s)", len(items), ", ".join(i.index_id for i in items))
    posted = 0

    for i, item in enumerate(items):
        card = item.card
        _log.info(
            "[%s/%s] %s obs=%s caption=%s/250",
            i + 1,
            len(items),
            item.index_id,
            item.observation_date,
            card.caption_len,
        )
        if dry_run:
            _log.info("dry-run caption:\n%s", card.caption)
            posted += 1
            continue
        try:
            mid = bot.send_photo(card.image_png, card.caption, filename=f"{item.index_id}.png")
            mark_posted(engine, item.index_id, item.observation_date, tg_message_id=mid)
            posted += 1
        except Exception:  # noqa: BLE001 — один индекс не валит весь прогон
            _log.exception("Не удалось отправить %s", item.index_id)
        if i < len(items) - 1 and pause_sec > 0:
            time.sleep(pause_sec)

    # Summary один раз на календарный день as_of.
    summary = build_summary(items, as_of=day)
    if dry_run:
        _log.info("dry-run summary:\n%s", summary)
    elif not already_posted(engine, SUMMARY_ID, day.isoformat()) or force:
        try:
            if pause_sec > 0:
                time.sleep(pause_sec)
            mid = bot.send_message(summary)
            mark_posted(engine, SUMMARY_ID, day.isoformat(), tg_message_id=mid)
            _log.info("Summary отправлен")
        except Exception:  # noqa: BLE001
            _log.exception("Не удалось отправить summary")
    else:
        _log.info("Summary за %s уже был", day.isoformat())

    return posted


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    p = argparse.ArgumentParser(description="Publish IVAN daily index cards to Telegram")
    p.add_argument("indexes", nargs="*", help="только эти id (по умолчанию все индексы)")
    p.add_argument("--as-of", type=str, default=None, help="YYYY-MM-DD UTC")
    p.add_argument("--dry-run", action="store_true", help="собрать карточки, не слать в Telegram")
    p.add_argument(
        "--force",
        action="store_true",
        help="игнорировать telegram_post_log (репост)",
    )
    p.add_argument("--pause", type=float, default=POST_PAUSE_SEC, help="пауза между постами, сек")
    args = p.parse_args(argv)

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
    return 0 if n or args.dry_run else 0


if __name__ == "__main__":
    raise SystemExit(main())
