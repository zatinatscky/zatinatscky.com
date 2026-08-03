"""
PNG-карточка индекса в стиле IVAN Terminal (Pillow, без Plotly).

Пайплайн render_chart_png:
1. Холст light-темы + шапка (имя, значение, зона, дельты 1d/7d/30d).
2. Плоскость с осями X/Y: деления, подписи масштаба, сетка.
3. Заливка + линия ряда.
4. Маркеры на каждой точке; подписи значений — последний день и каждые 2 дня ранее.
5. Футер IVAN / as-of.

Масштаб Y — линейный по min..max ряда (с небольшим padding).
Ось Y слева с «красивыми» делениями; ось X снизу с датами на тех же
точках, что и подписи значений.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from telegram_feed import theme as T

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/PTSerif.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    str(Path(__file__).resolve().parent / "fonts" / "DejaVuSans.ttf"),
]


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    paths = list(_FONT_CANDIDATES)
    if bold:
        paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", *paths]
    for path in paths:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _hex(c: str) -> tuple[int, int, int]:
    h = c.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _fmt_num(v: float, dec: int, pre: str = "", unit: str = "") -> str:
    if dec <= 0:
        body = f"{v:.0f}"
    else:
        body = f"{v:.{dec}f}"
    return f"{pre}{body}{unit}"


def _short_date(iso: str) -> str:
    """YYYY-MM-DD → 'Aug 3'."""
    try:
        _, m, d = iso.split("-")
        months = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ]
        return f"{months[int(m) - 1]} {int(d)}"
    except Exception:  # noqa: BLE001
        return iso


def label_indices(n: int) -> list[int]:
    """Последний день и каждые 2 дня ранее. Для n=14 → [1,3,5,7,9,11,13]."""
    if n <= 0:
        return []
    out: list[int] = []
    i = n - 1
    while i >= 0:
        out.append(i)
        i -= 2
    out.reverse()
    return out


def nice_ticks(lo: float, hi: float, target: int = 5) -> list[float]:
    """
    «Красивые» деления оси Y между lo и hi (включительно по возможности).

    Алгоритм: шаг = 1/2/5 × 10^k, число тиков около target.
    """
    if not math.isfinite(lo) or not math.isfinite(hi):
        return [0.0, 1.0]
    if hi < lo:
        lo, hi = hi, lo
    if hi == lo:
        # Плоский ряд — искусственный коридор вокруг значения.
        pad = abs(lo) * 0.05 if lo else 1.0
        lo, hi = lo - pad, hi + pad

    span = hi - lo
    raw = span / max(target - 1, 1)
    exp = math.floor(math.log10(raw)) if raw > 0 else 0
    base = 10**exp
    step = base
    for mult in (1, 2, 5, 10):
        cand = mult * base
        if raw <= cand:
            step = cand
            break

    # Нижняя/верхняя граница, кратные step.
    start = math.floor(lo / step) * step
    end = math.ceil(hi / step) * step
    ticks: list[float] = []
    v = start
    # Защита от бесконечного цикла на float-шуме.
    for _ in range(40):
        if v > end + step * 1e-9:
            break
        ticks.append(v)
        v += step
    return ticks if ticks else [lo, hi]


def _axis_dec(ticks: list[float], series_dec: int) -> int:
    """Сколько знаков показывать на оси Y — не грубее данных, но без лишнего."""
    if not ticks:
        return series_dec
    step = min(abs(ticks[i + 1] - ticks[i]) for i in range(len(ticks) - 1)) if len(ticks) > 1 else 1.0
    if step >= 1:
        return max(0, min(series_dec, 0))
    if step >= 0.1:
        return max(1, min(series_dec, 2))
    if step >= 0.01:
        return max(2, min(series_dec, 3))
    return max(series_dec, 3)


def render_chart_png(
    *,
    name: str,
    dates: list[str],
    series: list[float],
    value: float,
    pre: str,
    unit: str,
    dec: int,
    pct: bool,
    zone_label: str | None,
    zone_color: str | None,
    delta_1d: float | None,
    delta_7d: float | None,
    delta_30d: float | None,
    as_of: str,
) -> bytes:
    """Рисует карточку с осями. series/dates — окно графика (обычно 14 дней)."""
    if len(series) != len(dates) or not series:
        raise ValueError("series и dates должны быть непустыми и одной длины")

    n = len(series)
    img = Image.new("RGB", (T.WIDTH, T.HEIGHT), _hex(T.BG2))
    draw = ImageDraw.Draw(img, "RGBA")

    font_title = _load_font(34, bold=True)
    font_value = _load_font(46, bold=True)
    font_meta = _load_font(20)
    font_small = _load_font(14)
    font_label = _load_font(17)
    font_point = _load_font(13, bold=True)
    font_axis = _load_font(13)

    pad_x = 40
    accent = _hex(T.ACCENT)
    text = _hex(T.TEXT)
    dim = _hex(T.TEXT_DIM)
    faint = _hex(T.TEXT_FAINT)
    bg2 = _hex(T.BG2)
    bg = _hex(T.BG)
    axis_col = _hex(T.TEXT_DIM)

    # ── Шапка ──────────────────────────────────────────────────────────────
    draw.text((pad_x, 28), name, fill=text, font=font_title)
    val_s = _fmt_num(value, dec, pre, unit)
    draw.text((pad_x, 78), val_s, fill=text, font=font_value)

    if zone_label:
        zx = pad_x + 10 + int(draw.textlength(val_s, font=font_value))
        zy = 92
        zcol = _hex(zone_color or T.TEXT_DIM)
        tw = int(draw.textlength(zone_label, font=font_label))
        draw.rounded_rectangle((zx, zy, zx + tw + 22, zy + 32), radius=16, fill=(*zcol, 28))
        draw.text((zx + 11, zy + 5), zone_label, fill=zcol, font=font_label)

    def delta_line(label: str, d: float | None, y: int) -> None:
        if d is None:
            txt, col = f"{label}  n/a", faint
        else:
            if pct:
                body = f"{d:+.2f}%"
            elif dec <= 0:
                body = f"{d:+.0f}"
            else:
                body = f"{d:+.{dec}f}"
            arrow = "▲" if d > 0 else ("▼" if d < 0 else "●")
            txt = f"{label}  {arrow} {body}"
            col = _hex(T.UP if d > 0 else (T.DOWN if d < 0 else T.TEXT_FAINT))
        tw = int(draw.textlength(txt, font=font_meta))
        draw.text((T.WIDTH - pad_x - tw, y), txt, fill=col, font=font_meta)

    delta_line("1d", delta_1d, 40)
    delta_line("7d", delta_7d, 70)
    delta_line("30d", delta_30d, 100)

    # ── Масштаб Y (по данным, без «раздувания» оси) ────────────────────────
    data_lo, data_hi = min(series), max(series)
    y_ticks = nice_ticks(data_lo, data_hi, target=5)
    # Видимый диапазон оси = крайние тики (масштаб читается с подписей оси).
    y_min, y_max = y_ticks[0], y_ticks[-1]
    if y_max <= y_min:
        y_max = y_min + 1.0
    y_span = y_max - y_min
    axis_dec = _axis_dec(y_ticks, dec)

    # Ширина колонки подписей Y — по самой длинной метке.
    y_labels = [_fmt_num(t, axis_dec, pre, unit) for t in y_ticks]
    y_label_w = max(int(draw.textlength(lb, font=font_axis)) for lb in y_labels)

    # ── Геометрия плоскости ────────────────────────────────────────────────
    # Слева — ось Y, снизу — ось X с датами, сверху — место под value-labels.
    chart_l = pad_x + y_label_w + 14
    chart_t = 158
    chart_r = T.WIDTH - pad_x
    chart_b = T.HEIGHT - 100
    chart_w = chart_r - chart_l
    chart_h = chart_b - chart_t

    # Фон плоскости (чуть шире осей).
    draw.rounded_rectangle(
        (chart_l - 10, chart_t - 12, chart_r + 10, chart_b + 34),
        radius=16,
        fill=bg,
    )

    def x_at(i: int) -> float:
        return chart_l + (i / max(n - 1, 1)) * chart_w

    def y_at(v: float) -> float:
        return chart_b - ((v - y_min) / y_span) * chart_h

    # Горизонтальная сетка по тикам Y + подписи оси Y.
    for tick, label in zip(y_ticks, y_labels):
        y = y_at(tick)
        draw.line((chart_l, y, chart_r, y), fill=T.GRID, width=1)
        # Засечка на оси
        draw.line((chart_l - 5, y, chart_l, y), fill=axis_col, width=1)
        tw = int(draw.textlength(label, font=font_axis))
        draw.text((chart_l - 10 - tw, y - 7), label, fill=dim, font=font_axis)

    # Вертикальные засечки оси X в позициях подписанных дат.
    x_label_idxs = label_indices(n)
    for i in x_label_idxs:
        x = x_at(i)
        draw.line((x, chart_b, x, chart_b + 5), fill=axis_col, width=1)

    # Оси (поверх сетки, чтобы рамка масштаба читалась явно).
    draw.line((chart_l, chart_t, chart_l, chart_b), fill=axis_col, width=2)  # Y
    draw.line((chart_l, chart_b, chart_r, chart_b), fill=axis_col, width=2)  # X
    # Короткие «усы» на верхнем конце Y и правом конце X.
    draw.line((chart_l - 5, chart_t, chart_l + 5, chart_t), fill=axis_col, width=1)
    draw.line((chart_r, chart_b - 5, chart_r, chart_b + 5), fill=axis_col, width=1)

    pts = [(x_at(i), y_at(v)) for i, v in enumerate(series)]

    # Заливка под линией до оси X.
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.polygon(list(pts) + [(pts[-1][0], chart_b), (pts[0][0], chart_b)], fill=(*accent, 46))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")

    # Повторно оси поверх заливки (заливка не должна их перекрывать).
    draw.line((chart_l, chart_t, chart_l, chart_b), fill=axis_col, width=2)
    draw.line((chart_l, chart_b, chart_r, chart_b), fill=axis_col, width=2)

    draw.line(pts, fill=accent, width=3)

    labeled = set(x_label_idxs)
    for i, (x, y) in enumerate(pts):
        r = 5 if i in labeled else 3.5
        draw.ellipse(
            (x - r, y - r, x + r, y + r),
            fill=accent,
            outline=bg2,
            width=2 if i in labeled else 1,
        )

    # Подписи значений у точек (не путать с подписями оси Y).
    for k, i in enumerate(x_label_idxs):
        x, y = pts[i]
        label = _fmt_num(series[i], dec, pre, unit)
        tw = int(draw.textlength(label, font=font_point))
        th = 15
        if i == n - 1:
            tx = min(max(chart_l + 2, x - tw / 2), chart_r - tw - 2)
            ty = max(chart_t + 2, y - th - 12)
            draw.rounded_rectangle(
                (tx - 5, ty - 2, tx + tw + 5, ty + th + 2),
                radius=7,
                fill=(*accent, 55),
            )
            draw.text((tx, ty), label, fill=text, font=font_point)
        else:
            above = k % 2 == 0
            tx = max(chart_l + 2, min(x - tw / 2, chart_r - tw - 2))
            ty = (y - th - 9) if above else (y + 9)
            ty = max(chart_t + 2, min(ty, chart_b - th - 4))
            draw.text((tx, ty), label, fill=text, font=font_point)

    # Подписи оси X (даты) — под осью, в тех же позициях.
    for i in x_label_idxs:
        x = x_at(i)
        dlabel = _short_date(dates[i])
        tw = int(draw.textlength(dlabel, font=font_small))
        tx = max(chart_l, min(x - tw / 2, chart_r - tw))
        draw.text((tx, chart_b + 10), dlabel, fill=dim, font=font_small)

    # ── Футер ──────────────────────────────────────────────────────────────
    draw.rectangle((0, T.HEIGHT - 44, T.WIDTH, T.HEIGHT), fill=bg)
    draw.line((0, T.HEIGHT - 44, T.WIDTH, T.HEIGHT - 44), fill=T.HAIRLINE, width=1)
    draw.text((pad_x, T.HEIGHT - 32), "IVAN", fill=text, font=font_small)
    right = f"14-day · as of {as_of} UTC"
    tw = int(draw.textlength(right, font=font_small))
    draw.text((T.WIDTH - pad_x - tw, T.HEIGHT - 32), right, fill=faint, font=font_small)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
