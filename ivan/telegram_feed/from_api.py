"""
Сборка карточек из публичного /api/indexes — для локального рендера без Postgres.

Используется так же, как card.build_card, но источник — JSON терминала.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import requests

from indices.registry import BY_ID
from telegram_feed.caption import build_caption
from telegram_feed.card import FeedCard, _delta, _feed_markdown
from telegram_feed.chart import render_chart_png
from telegram_feed.theme import CHART_DAYS, EXCLUDED_IDS, HISTORY_DAYS
from telegram_feed.zones import zone_of


def fetch_indexes_payload(base_url: str = "https://ivan.zatinatscky.com", days: int = HISTORY_DAYS) -> dict:
    url = f"{base_url.rstrip('/')}/api/indexes?days={days}"
    resp = requests.get(url, timeout=60, headers={"Accept": "application/json"})
    resp.raise_for_status()
    return resp.json()


def build_card_from_payload(payload: dict, index_id: str) -> FeedCard:
    if index_id in EXCLUDED_IDS:
        raise ValueError(f"Индекс {index_id} исключён из дневного Telegram-фида")
    spec = BY_ID.get(index_id)
    if spec is None:
        raise KeyError(f"Неизвестный индекс: {index_id}")

    dates = [str(d)[:10] for d in payload.get("dates") or []]
    row = next((x for x in payload.get("indexes") or [] if x.get("id") == index_id), None)
    if not row or not dates:
        raise RuntimeError(f"Нет данных для {index_id} в API")
    series = [float(v) for v in row["series"]]
    if len(series) != len(dates):
        raise RuntimeError(f"Длины dates/series не совпадают для {index_id}")

    cur = series[-1]
    as_of_s = dates[-1]
    dates_c, series_c = dates[-CHART_DAYS:], series[-CHART_DAYS:]
    zone = zone_of(spec.id, cur, series, bool(row.get("gauge") or spec.gauge))
    zone_label = zone[0] if zone else None
    zone_color = zone[1] if zone else None

    d1 = _delta(cur, series[-2] if len(series) >= 2 else None, pct=spec.pct)
    d7 = _delta(cur, series[-8] if len(series) >= 8 else None, pct=spec.pct)
    d30 = _delta(cur, series[-31] if len(series) >= 31 else None, pct=spec.pct)

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
        series=series,
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


def render_day_feed_from_api(
    out_dir: Path,
    *,
    base_url: str = "https://ivan.zatinatscky.com",
    only: list[str] | None = None,
) -> list[FeedCard]:
    payload = fetch_indexes_payload(base_url)
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = only or [s.id for s in BY_ID.values() if s.id not in EXCLUDED_IDS]
    # Сохраняем порядок реестра.
    order = [s.id for s in BY_ID.values() if s.id not in EXCLUDED_IDS]
    ids = [i for i in order if i in set(ids)]

    cards: list[FeedCard] = []
    errors: list[str] = []
    for iid in ids:
        try:
            card = build_card_from_payload(payload, iid)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"- `{iid}`: {exc}")
            continue
        cards.append(card)
        (out_dir / f"{card.index_id}.png").write_bytes(card.image_png)
        (out_dir / f"{card.index_id}.txt").write_text(card.caption + "\n", encoding="utf-8")

    as_of = None
    if cards:
        as_of = date.fromisoformat(cards[0].as_of)
    (out_dir / "FEED.md").write_text(_feed_markdown(cards, errors, as_of=as_of), encoding="utf-8")
    return cards
