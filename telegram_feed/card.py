"""
Сборка карточки индекса: данные из БД → PNG + caption.

В дневной фид входят все индексы реестра (включая Crypto Fear & Greed).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.engine import Engine

from indices.registry import BY_ID, SPECS, IndexSpec
from indices.series import LOOKBEHIND_DAYS, calendar_days, forward_fill
from indices.store import load_points
from telegram_feed.caption import build_caption
from telegram_feed.chart import render_chart_png
from telegram_feed.theme import CHART_DAYS, EXCLUDED_IDS, HISTORY_DAYS
from telegram_feed.zones import zone_of


@dataclass(frozen=True)
class FeedCard:
    index_id: str
    name: str
    domain: str
    as_of: str
    caption: str
    image_png: bytes
    caption_len: int


def _delta(cur: float, prev: float | None, *, pct: bool) -> float | None:
    if prev is None:
        return None
    if pct:
        if prev == 0:
            return None
        return (cur / prev - 1.0) * 100.0
    return cur - prev


def _load_filled(engine: Engine, spec: IndexSpec, days: int, end: date) -> tuple[list[str], list[float]] | None:
    days_list = calendar_days(days, end=end)
    # Lookbehind: чтобы forward-fill имел точку до начала окна (праздники, лаг FRED).
    since = (end - timedelta(days=days + LOOKBEHIND_DAYS - 1)).isoformat()
    points = load_points(engine, spec.id, since=since)
    if not points:
        points = load_points(engine, spec.id, since=None)
    filled = forward_fill(points, days_list)
    if not filled:
        return None
    return days_list, filled


def build_card(
    engine: Engine,
    index_id: str,
    *,
    as_of: date | None = None,
) -> FeedCard:
    """Собирает карточку одного индекса на дату as_of (по умолчанию сегодня UTC)."""
    if index_id in EXCLUDED_IDS:
        raise ValueError(f"Индекс {index_id} исключён из дневного Telegram-фида")

    spec = BY_ID.get(index_id)
    if spec is None:
        raise KeyError(f"Неизвестный индекс: {index_id}")

    end = as_of or datetime.now(tz=timezone.utc).date()
    loaded = _load_filled(engine, spec, HISTORY_DAYS, end)
    if not loaded:
        raise RuntimeError(f"Нет данных для {index_id}")

    dates_full, series_full = loaded
    cur = series_full[-1]
    as_of_s = dates_full[-1]

    # Окно графика — последние 14 календарных дней.
    dates_c = dates_full[-CHART_DAYS:]
    series_c = series_full[-CHART_DAYS:]

    zone = zone_of(spec.id, cur, series_full, spec.gauge)
    zone_label = zone[0] if zone else None
    zone_color = zone[1] if zone else None

    d1 = _delta(cur, series_full[-2] if len(series_full) >= 2 else None, pct=spec.pct)
    d7 = _delta(cur, series_full[-8] if len(series_full) >= 8 else None, pct=spec.pct)
    d30 = _delta(cur, series_full[-31] if len(series_full) >= 31 else None, pct=spec.pct)

    png = render_chart_png(
        name=spec.name,
        dates=dates_c,
        series=series_c,
        value=cur,
        pre=spec.pre,
        unit=spec.unit,
        dec=spec.dec,
        pct=spec.pct,
        zone_label=zone_label,
        zone_color=zone_color,
        delta_1d=d1,
        delta_7d=d7,
        delta_30d=d30,
        as_of=as_of_s,
    )
    caption = build_caption(
        index_id=spec.id,
        name=spec.name,
        domain=spec.domain,
        value=cur,
        pre=spec.pre,
        unit=spec.unit,
        dec=spec.dec,
        pct=spec.pct,
        zone_label=zone_label,
        series=series_full,
        as_of=as_of_s,
    )
    return FeedCard(
        index_id=spec.id,
        name=spec.name,
        domain=spec.domain,
        as_of=as_of_s,
        caption=caption,
        image_png=png,
        caption_len=len(caption),
    )


def feed_index_ids() -> list[str]:
    """Все индексы терминала для канала (минус EXCLUDED_IDS, если заданы)."""
    return [s.id for s in SPECS if s.id not in EXCLUDED_IDS]


def render_day_feed(
    engine: Engine,
    out_dir: Path,
    *,
    as_of: date | None = None,
    only: list[str] | None = None,
) -> list[FeedCard]:
    """
    Рендерит карточки за день в out_dir:
      <id>.png
      <id>.txt   — caption
      FEED.md    — примеры постов для ревью
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = only or feed_index_ids()
    cards: list[FeedCard] = []
    errors: list[str] = []

    for iid in ids:
        if iid in EXCLUDED_IDS:
            continue
        try:
            card = build_card(engine, iid, as_of=as_of)
        except Exception as exc:  # noqa: BLE001 — один индекс не валит весь фид
            errors.append(f"- `{iid}`: {exc}")
            continue
        cards.append(card)
        (out_dir / f"{card.index_id}.png").write_bytes(card.image_png)
        (out_dir / f"{card.index_id}.txt").write_text(card.caption + "\n", encoding="utf-8")

    md = _feed_markdown(cards, errors, as_of=as_of)
    (out_dir / "FEED.md").write_text(md, encoding="utf-8")
    return cards


def _feed_markdown(cards: list[FeedCard], errors: list[str], *, as_of: date | None) -> str:
    day = (as_of or datetime.now(tz=timezone.utc).date()).isoformat()
    lines = [
        f"# IVAN Telegram feed · {day}",
        "",
        "Черновик дневных постов (без Crypto Fear & Greed).",
        "Картинка — 14 дней, подпись ≤250 символов, футер только на ivan.zatinatscky.com.",
        "",
    ]
    if errors:
        lines += ["## Errors", ""] + errors + [""]

    for card in cards:
        lines += [
            f"## {card.name} (`{card.index_id}`)",
            "",
            f"![chart]({card.index_id}.png)",
            "",
            f"Caption length: {card.caption_len}/250",
            "",
            "```",
            card.caption,
            "```",
            "",
            "---",
            "",
        ]
    return "\n".join(lines)
