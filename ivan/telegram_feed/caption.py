"""
Короткая подпись Telegram (≤250 символов) + футер.

Формат:
  🟠 Name · value · Zone
  📉 −x (1d) · 📈 +y (7d) · ➡️ z (30d)
  → https://ivan.zatinatscky.com/i/<id>
  ——
  IVAN · as of YYYY-MM-DD UTC · NFA
  ivan.zatinatscky.com
"""

from __future__ import annotations

from telegram_feed.theme import DOMAIN_EMOJI

MAX_CAPTION = 250
SITE = "https://ivan.zatinatscky.com"


def _fmt_value(value: float, *, pre: str, unit: str, dec: int) -> str:
    if dec <= 0:
        body = f"{value:.0f}"
    else:
        body = f"{value:.{dec}f}"
    return f"{pre}{body}{unit}"


def _delta_emoji(delta: float, eps: float) -> str:
    if delta > eps:
        return "📈"
    if delta < -eps:
        return "📉"
    return "➡️"


def _fmt_delta(
    cur: float,
    prev: float | None,
    *,
    pct: bool,
    dec: int,
    label: str,
) -> str:
    """Один сегмент вида '📉 −1.2 (1d)'."""
    if prev is None or prev == 0 and pct:
        return f"➡️ n/a ({label})"
    if prev is None:
        return f"➡️ n/a ({label})"

    if pct:
        ch = (cur / prev - 1.0) * 100.0
        eps = 0.05
        if abs(ch) <= eps:
            body = "0.00%"
        else:
            body = f"{ch:+.2f}%"
    else:
        ch = cur - prev
        eps = 10 ** (-max(dec, 0)) / 2
        if abs(ch) <= eps:
            body = f"{0:.{max(dec, 0)}f}" if dec > 0 else "0"
        elif dec <= 0:
            body = f"{ch:+.0f}"
        else:
            body = f"{ch:+.{dec}f}"
    return f"{_delta_emoji(ch, eps)} {body} ({label})"


def build_caption(
    *,
    index_id: str,
    name: str,
    domain: str,
    value: float,
    pre: str,
    unit: str,
    dec: int,
    pct: bool,
    zone_label: str | None,
    series: list[float],
    as_of: str,
) -> str:
    """
    Собирает подпись. Если вылезаем за MAX_CAPTION — укорачиваем имя и зону.
    series: полный ряд (нужны точки -2, -8, -31 для дельт).
    """
    emoji = DOMAIN_EMOJI.get(domain, "▪️")
    n = len(series)
    cur = series[-1] if n else value

    d1 = _fmt_delta(cur, series[-2] if n >= 2 else None, pct=pct, dec=dec, label="1d")
    d7 = _fmt_delta(cur, series[-8] if n >= 8 else None, pct=pct, dec=dec, label="7d")
    d30 = _fmt_delta(cur, series[-31] if n >= 31 else None, pct=pct, dec=dec, label="30d")

    val_s = _fmt_value(cur, pre=pre, unit=unit, dec=dec)
    link = f"{SITE}/i/{index_id}"
    footer = f"——\nIVAN · as of {as_of} UTC · NFA\nivan.zatinatscky.com"

    def assemble(nm: str, zone: str | None) -> str:
        head = f"{emoji} {nm} · {val_s}"
        if zone:
            head += f" · {zone}"
        return f"{head}\n{d1} · {d7} · {d30}\n→ {link}\n{footer}"

    text = assemble(name, zone_label)
    if len(text) <= MAX_CAPTION:
        return text

    # Ужимаем: без зоны, короткое имя.
    short = name
    if len(short) > 22:
        short = short[:20].rstrip() + "…"
    text = assemble(short, None)
    if len(text) <= MAX_CAPTION:
        return text

    # Крайний случай — режем дельту 30d.
    head = f"{emoji} {short} · {val_s}"
    return f"{head}\n{d1} · {d7}\n→ {link}\n{footer}"[:MAX_CAPTION]
