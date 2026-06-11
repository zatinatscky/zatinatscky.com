"""
Вёрстка и графики Dash для индекса Fear & Greed и BTC (цена и объём с биржи).

Стиль: тёмная тема, сетка графиков, подписи на точках (как в прототипе).
Справка о методологии и ссылки на провайдеров данных — в шапке (раскрывающийся блок).
Все подписи UI — на английском.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dcc, html
from dash.exceptions import PreventUpdate
from plotly.subplots import make_subplots

from fng_data import get_engine, load_fng_dataframe

# Идентификаторы Dash (shell, bootstrap, фильтр дат).
DASH_DF_STORE_ID = "fng-dash-df-store"
DASH_DATE_PICKER_ID = "fng-dash-date-picker"
DASH_CHARTS_OUTLET_ID = "fng-dash-charts-outlet"
DASH_RANGE_HINT_ID = "fng-dash-range-hint"
FNG_URL_ID = "fng-url"
FNG_TOP_ROW_ID = "fng-top-row"
FNG_PAGE_META_ID = "fng-page-meta"
FNG_PAGE_LOADING_ID = "fng-page-loading"

# --- Тема (как в прототипе дашборда) ---
BACKGROUND = "#0f1419"
CARD = "#1a2332"
TEXT_COLOR = "#e6edf3"
ACCENT = "#58a6ff"
BTC_LINE = "#f7931a"

# Оболочка страницы /fng/: на всю ширину viewport (без max-width по центру).
PAGE_SHELL_STYLE: dict = {
    "width": "100%",
    "maxWidth": "100%",
    "margin": "0",
    "padding": "14px 18px 20px",
    "boxSizing": "border-box",
    "backgroundColor": BACKGROUND,
    "minHeight": "100vh",
    "color": TEXT_COLOR,
}

# Plotly: responsive только при явной высоте figure + контейнера в px (см. MAIN_CHART_HEIGHT).
GRAPH_CONFIG = {"displayModeBar": True, "responsive": True, "displaylogo": False}
MAIN_CHART_HEIGHT = 480

# Провайдеры данных (показ в UI)
ALT_FNG_URL = "https://alternative.me/crypto/fear-and-greed-index/"
ALT_HOME_URL = "https://alternative.me/"
BINANCE_KLINES_DOC_URL = "https://binance-docs.github.io/apidocs/spot/en/#kline-candlestick-data"

# Цвета линии F&G: три режима (меньше смен цвета → меньше trace и быстрее Dash).
# Пороговые зоны 20/80 на фоне остаются; отсечки 20/40/60/80 — пунктиром.
FNG_LINE_MID = "#7ec8ff"
FNG_COLOR_EXTREME_FEAR = "#ff4d4d"
FNG_COLOR_EXTREME_GREED = "#3ddc84"


def _fng_line_tone(v: float) -> int:
    """0 = зона страха (<20), 1 = основная полоса, 2 = жадность (>80)."""
    if v < 20:
        return 0
    if v > 80:
        return 2
    return 1


def _fng_line_tone_color(t: int) -> str:
    return (FNG_COLOR_EXTREME_FEAR, FNG_LINE_MID, FNG_COLOR_EXTREME_GREED)[t]


# Заливки зон на основном графике (ось F&G 0–100).
ZONE_FEAR_FILL = "rgba(255, 77, 77, 0.14)"
ZONE_GREED_FILL = "rgba(64, 192, 87, 0.14)"


@dataclass(frozen=True)
class HeroStats:
    """Сводка для «пуль» под спидометром: вчера, среднее за 7 и 30 последних дней ряда."""

    yesterday_label: str
    yesterday_value: str
    week_avg_label: str
    week_avg_value: str
    month_avg_label: str
    month_avg_value: str


def compute_hero_stats(df: pd.DataFrame) -> HeroStats | None:
    """
    Вчера относительно последней даты в данных; средние — по последним 7 и 30 наблюдениям ряда.
    """
    if df.empty or "date_utc" not in df.columns:
        return None
    s = df.sort_values("date_utc").reset_index(drop=True)
    last_dt = pd.Timestamp(s["date_utc"].iloc[-1]).normalize()
    prev_dt = last_dt - pd.Timedelta(days=1)
    mask_y = s["date_utc"].dt.normalize() == prev_dt
    if mask_y.any():
        row = s.loc[mask_y].iloc[-1]
        yv = int(row["value"])
        yc = str(row.get("classification", "")).strip() or "—"
        y_str = f"{yc} — {yv}"
    else:
        y_str = "No row for previous UTC day"

    w = s.tail(7)["value"]
    m = s.tail(30)["value"]
    w_str = f"{w.mean():.1f}" if len(w) else "—"
    m_str = f"{m.mean():.1f}" if len(m) else "—"

    return HeroStats(
        yesterday_label="Yesterday",
        yesterday_value=y_str,
        week_avg_label="Last week (avg, last 7 days)",
        week_avg_value=w_str,
        month_avg_label="Last month (avg, last 30 days)",
        month_avg_value=m_str,
    )


def dataframe_to_store_records(df: pd.DataFrame) -> list[dict]:
    """
    Сериализация датафрейма в JSON для dcc.Store (callback на клиенте не трогает БД).

    Даты — ISO-8601 строки UTC; пропуски в числах превращаем в None для валидного JSON.
    """
    frame = df.copy()
    frame["date_utc"] = pd.to_datetime(frame["date_utc"], utc=True).map(lambda t: t.isoformat())
    recs = frame.to_dict(orient="records")
    out: list[dict] = []
    for row in recs:
        clean = {k: (None if v is pd.NA or (isinstance(v, float) and pd.isna(v)) else v) for k, v in row.items()}
        out.append(clean)
    return out


def dataframe_from_store_records(rows: list | None) -> pd.DataFrame:
    """Восстановление таблицы из dcc.Store после round-trip JSON."""
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "date_utc" not in df.columns:
        return pd.DataFrame()
    df["date_utc"] = pd.to_datetime(df["date_utc"], utc=True)
    if "value" in df.columns:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    if "classification" in df.columns:
        df["classification"] = df["classification"].astype(str).replace({"nan": ""})
    for col in ("btc_usd", "btc_volume_btc", "btc_quote_usdt", "rolling_30d", "sma_30"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _calendar_range_hint(start_date: str | None, end_date: str | None, n_rows: int) -> str:
    """Подпись под DatePickerRange: выбранный календарный интервал и число дней в срезе."""
    if not start_date or not end_date:
        return "Select start and end dates (UTC)."
    return f"Selected: {start_date} — {end_date} UTC · {n_rows} day(s) in view"


def _slice_df_by_calendar_range(
    df: pd.DataFrame,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    """Фильтр ряда по календарным датам UTC (включительно оба конца)."""
    if df.empty or not start_date or not end_date:
        return df
    start = pd.Timestamp(start_date).tz_localize("UTC")
    end = pd.Timestamp(end_date).tz_localize("UTC")
    if start > end:
        start, end = end, start
    days = df["date_utc"].dt.normalize()
    mask = (days >= start.normalize()) & (days <= end.normalize())
    sub = df.loc[mask].copy()
    return sub if len(sub) > 0 else df


def prepare_df_for_charts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Сортирует ряд, приводит типы, добавляет SMA и флаги для подписей на линии.

    Ожидаются колонки: date_utc, value, classification; опционально btc_usd и объёмы Binance.
    """
    out = df.sort_values("date_utc").reset_index(drop=True).copy()
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["value", "date_utc"])

    if "btc_usd" in out.columns:
        out["btc_usd"] = pd.to_numeric(out["btc_usd"], errors="coerce")
    if "btc_volume_btc" in out.columns:
        out["btc_volume_btc"] = pd.to_numeric(out["btc_volume_btc"], errors="coerce")
    if "btc_quote_usdt" in out.columns:
        out["btc_quote_usdt"] = pd.to_numeric(out["btc_quote_usdt"], errors="coerce")

    if "rolling_30d" in out.columns:
        out["sma_30"] = pd.to_numeric(out["rolling_30d"], errors="coerce")
    else:
        out["sma_30"] = out["value"].rolling(window=30, min_periods=1).mean()

    out["show_label"] = False
    if len(out) > 0:
        step = max(1, len(out) // 40)
        out.loc[out.index[::step], "show_label"] = True
        out.loc[out.index[-1], "show_label"] = True

    # Разреженные подписи на столбиках дневного объёма (USDT) на отдельном графике.
    out["show_btc_vol_label"] = False
    if len(out) > 0 and "btc_quote_usdt" in out.columns and out["btc_quote_usdt"].notna().any():
        step_v = max(1, len(out) // 35)
        out.loc[out.index[::step_v], "show_btc_vol_label"] = True
        out.loc[out.index[-1], "show_btc_vol_label"] = True

    return out


def methodology_header() -> html.Div:
    """
    Шапка: краткое описание методологии, ссылки на Alternative.me и Binance Spot API,
    раскрывающийся блок с подробностями (раньше был в «футере»).
    """
    intro = html.Div(
        [
            html.P(
                [
                    "The ",
                    html.Strong("Crypto Fear & Greed Index"),
                    " is computed by ",
                    html.A("Alternative.me", href=ALT_HOME_URL, target="_blank", rel="noopener noreferrer"),
                    " from volatility, momentum, social media, dominance, and surveys. ",
                    "Daily BTC/USDT candle close (UTC day) and trade volumes are loaded from the Binance ",
                    html.A("Spot public REST API", href=BINANCE_KLINES_DOC_URL, target="_blank", rel="noopener noreferrer"),
                    " (pair BTCUSDT, interval 1d, no API key) and stored alongside this series in the same database.",
                ],
                style={"margin": "0 0 10px 0", "lineHeight": 1.55, "fontSize": "0.92rem", "opacity": 0.95},
            ),
            html.P(
                [
                    "Official index page: ",
                    html.A("Alternative.me — Fear & Greed", href=ALT_FNG_URL, target="_blank", rel="noopener noreferrer"),
                    ".",
                ],
                style={"margin": "0", "fontSize": "0.88rem", "opacity": 0.9},
            ),
        ],
    )

    details_body = html.Div(
        [
            html.P(
                "The index maps several inputs into a single 0–100 score: 0 means Extreme Fear, "
                "100 means Extreme Greed. It is a sentiment snapshot, not a trading signal on its own.",
                style={"margin": "0 0 10px 0", "lineHeight": 1.55},
            ),
            html.P(
                "BTC data are Binance daily klines: close in USDT (shown like USD on charts) and quote volume "
                "in USDT per UTC calendar day. The first chart overlays the index (left axis) and BTC (right axis). "
                "The charts section shows a gauge for the latest day in range, historical summary pills, "
                "and a dual-axis chart (Fear/Greed vs BTC) with zones and dashed grid lines at 20-point steps.",
                style={"margin": "0 0 10px 0", "lineHeight": 1.55},
            ),
            html.P(
                "This dashboard is for information only; it is not investment advice.",
                style={"margin": "0", "lineHeight": 1.55},
            ),
        ],
        style={"padding": "10px 0 0 0"},
    )

    collapsible = html.Details(
        [
            html.Summary(
                "Methodology & data sources (expand)",
                style={
                    "cursor": "pointer",
                    "fontWeight": "600",
                    "color": ACCENT,
                },
            ),
            details_body,
        ],
        style={
            "marginTop": "12px",
            "paddingTop": "12px",
            "borderTop": "1px solid #30363d",
        },
    )

    # Контент без обёртки ширины — родитель задаёт 80% верхней строки страницы.
    return html.Div([intro, collapsible], style={"height": "100%"})


def _hero_stat_row(label: str, pill_text: str, *, with_bottom_border: bool = True) -> html.Div:
    """Строка «подпись слева — значение в капсуле справа» (как у референс-дашбордов)."""
    row_style: dict = {
        "display": "flex",
        "alignItems": "center",
        "justifyContent": "space-between",
        "gap": "12px",
        "padding": "10px 0",
    }
    if with_bottom_border:
        row_style["borderBottom"] = "1px solid #30363d"
    return html.Div(
        [
            html.Span(label, style={"flex": "1", "fontSize": "0.88rem", "opacity": 0.88}),
            html.Span(
                pill_text,
                style={
                    "padding": "6px 14px",
                    "borderRadius": "999px",
                    "background": "#f0e6d2",
                    "color": "#1a1a1a",
                    "fontSize": "0.82rem",
                    "fontWeight": "600",
                    "maxWidth": "62%",
                    "textAlign": "right",
                    "lineHeight": 1.25,
                },
            ),
        ],
        style=row_style,
    )


def figure_fng_gauge(last_value: int, last_classification: str, last_date_str: str) -> go.Figure:
    """
    Полукруглый gauge 0–100: шкала от красного к зелёному, стрелка на последнем загруженном дне.
    """
    safe_cls = last_classification.strip() if last_classification else "—"
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=last_value,
            number={
                "font": {"size": 46, "color": TEXT_COLOR, "family": "system-ui, sans-serif"},
            },
            title={
                "text": f"Latest · {last_date_str} UTC<br><span style='font-size:0.82rem;font-weight:400;opacity:0.88'>{safe_cls}</span>",
                "font": {"size": 13, "color": TEXT_COLOR},
            },
            gauge={
                "axis": {
                    "range": [0, 100],
                    "tickvals": [0, 20, 40, 60, 80, 100],
                    "tickwidth": 1,
                    "tickcolor": "#8b949e",
                },
                "bar": {"color": "rgba(255,255,255,0.22)"},
                "bgcolor": CARD,
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 20], "color": "rgba(180, 45, 45, 0.65)"},
                    {"range": [20, 40], "color": "rgba(200, 95, 40, 0.5)"},
                    {"range": [40, 60], "color": "rgba(190, 165, 55, 0.42)"},
                    {"range": [60, 80], "color": "rgba(55, 150, 85, 0.48)"},
                    {"range": [80, 100], "color": "rgba(35, 120, 60, 0.62)"},
                ],
                "threshold": {
                    "line": {"color": "#f0f6fc", "width": 3},
                    "thickness": 0.82,
                    "value": last_value,
                },
            },
        )
    )
    fig.update_layout(
        paper_bgcolor=CARD,
        font=dict(color=TEXT_COLOR),
        margin=dict(l=20, r=20, t=36, b=12),
        height=300,
    )
    return fig


def figure_full_timeline(df: pd.DataFrame) -> go.Figure:
    """
    Главный график: F&G (ось 0–100) с зонами <20 / >80, пунктирные отсечки каждые 20,
    многоцветная линия по диапазонам; BTC на вторичной оси.
    """
    has_btc = "btc_usd" in df.columns and df["btc_usd"].notna().any()
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    dates = df["date_utc"].tolist()
    values = [float(v) for v in df["value"].tolist()]
    n = len(values)

    if n == 0:
        fig.update_layout(title="No data", paper_bgcolor=CARD, plot_bgcolor=CARD, font=dict(color=TEXT_COLOR))
        return fig

    x_min, x_max = dates[0], dates[-1]

    # --- Фоновые зоны по оси F&G (под графиками) ---
    fig.add_shape(
        type="rect",
        xref="x",
        yref="y",
        x0=x_min,
        x1=x_max,
        y0=0,
        y1=20,
        fillcolor=ZONE_FEAR_FILL,
        line_width=0,
        layer="below",
    )
    fig.add_shape(
        type="rect",
        xref="x",
        yref="y",
        x0=x_min,
        x1=x_max,
        y0=80,
        y1=100,
        fillcolor=ZONE_GREED_FILL,
        line_width=0,
        layer="below",
    )

    # --- Пунктирные горизонтали на переднем плане (каждые 20 пунктов по шкале F&G) ---
    for y_line in (20, 40, 60, 80):
        fig.add_hline(
            y=y_line,
            line_dash="dot",
            line_color="rgba(230, 237, 243, 0.38)",
            line_width=1,
            layer="above",
            secondary_y=False,
        )

    # --- Подписи экстремальных зон (справа у последней даты, чтобы попадали в «текущий» край графика) ---
    fig.add_annotation(
        x=x_max,
        y=9,
        xref="x",
        yref="y",
        xanchor="right",
        text="Extreme Fear",
        showarrow=False,
        font=dict(size=11, color="rgba(255, 160, 160, 0.95)"),
    )
    fig.add_annotation(
        x=x_max,
        y=91,
        xref="x",
        yref="y",
        xanchor="right",
        text="Extreme Greed",
        showarrow=False,
        font=dict(size=11, color="rgba(160, 230, 175, 0.95)"),
    )
    # Доп. подписи уровней на правом краю области F&G (как ориентиры шкалы)
    for y_txt, lab in ((40, "Fear"), (60, "Neutral"), (80, "Greed")):
        fig.add_annotation(
            x=x_max,
            y=y_txt,
            xref="x",
            yref="y",
            xanchor="right",
            yshift=10 if y_txt == 80 else (-10 if y_txt == 40 else 0),
            text=lab,
            showarrow=False,
            font=dict(size=10, color="rgba(230, 237, 243, 0.55)"),
        )

    # --- Линия F&G: один trace на каждый непрерывный участок с одним цветом (меньше нагрузка на Plotly) ---
    b_series = df["value"].map(lambda v: _fng_line_tone(float(v)))
    run_id = b_series.ne(b_series.shift()).cumsum()
    first_legend = True
    for _, grp in df.groupby(run_id, sort=False):
        xs = grp["date_utc"].tolist()
        ys = [float(v) for v in grp["value"].tolist()]
        t0 = int(grp["value"].map(_fng_line_tone).iloc[0])
        clr = _fng_line_tone_color(t0)
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                name="Fear & Greed" if first_legend else "_fng",
                legendgroup="fng",
                showlegend=first_legend,
                line=dict(color=clr, width=2.5),
                hovertemplate="Date: %{x|%Y-%m-%d}<br>F&G: %{y}<extra></extra>",
            ),
            secondary_y=False,
        )
        first_legend = False

    if has_btc:
        hover_lines: list[str] = []
        for _, r in df.iterrows():
            if pd.isna(r["btc_usd"]):
                hover_lines.append("")
                continue
            parts = [
                f"Date: {r['date_utc']:%Y-%m-%d}",
                f"BTC close (USDT): ${float(r['btc_usd']):,.2f}",
            ]
            if "btc_quote_usdt" in df.columns and pd.notna(r.get("btc_quote_usdt")):
                parts.append(f"Quote volume (USDT): {float(r['btc_quote_usdt']):,.0f}")
            if "btc_volume_btc" in df.columns and pd.notna(r.get("btc_volume_btc")):
                parts.append(f"Base volume (BTC): {float(r['btc_volume_btc']):.4f}")
            hover_lines.append("<br>".join(parts))

        fig.add_trace(
            go.Scatter(
                x=df["date_utc"],
                y=df["btc_usd"],
                mode="lines",
                name="BTC / USDT",
                line=dict(color=BTC_LINE, width=1.35),
                hovertext=hover_lines,
                hoverinfo="text",
                connectgaps=False,
            ),
            secondary_y=True,
        )

    # Заголовок только в html.H2 карточки. Высота в px обязательна — иначе SVG схлопывается (hover есть, линий нет).
    fig.update_layout(
        autosize=True,
        height=MAIN_CHART_HEIGHT,
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        font=dict(color=TEXT_COLOR),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=0.99,
            x=0.01,
            bgcolor="rgba(26, 35, 50, 0.6)",
            font=dict(size=11),
        ),
        margin=dict(l=52, r=76, t=12, b=44, pad=0),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#30363d", title="Date (UTC)")
    fig.update_yaxes(
        title_text="Fear & Greed (0–100)",
        range=[0, 100],
        showgrid=False,
        secondary_y=False,
    )
    fig.update_yaxes(
        title_text="BTC close (USDT)",
        showgrid=False,
        secondary_y=True,
        tickformat="$,.0f",
    )
    return fig


def _short_usdt_notation(value: float) -> str:
    """Короткая подпись объёма на столбиках (читаемость при тысячах точек)."""
    if value >= 1e9:
        return f"{value / 1e9:.1f}B"
    if value >= 1e6:
        return f"{value / 1e6:.0f}M"
    if value >= 1e3:
        return f"{value / 1e3:.0f}K"
    return f"{value:,.0f}"


def figure_btc_price_and_volume(df: pd.DataFrame) -> go.Figure:
    """
    Два ряда: дневной close BTCUSDT и дневной quote volume (USDT) с разреженными подписями на столбиках.
    """
    has_price = "btc_usd" in df.columns and df["btc_usd"].notna().any()
    has_vol = "btc_quote_usdt" in df.columns and df["btc_quote_usdt"].notna().any()
    if not has_price or not has_vol:
        fig = go.Figure()
        fig.update_layout(
            title="BTC — daily close & quote volume (no data)",
            paper_bgcolor=CARD,
            plot_bgcolor=CARD,
            font=dict(color=TEXT_COLOR),
            height=380,
            annotations=[
                dict(
                    text="No Binance BTC rows in the database yet.",
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.5,
                    showarrow=False,
                    font=dict(size=14),
                )
            ],
        )
        return fig

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.55, 0.45],
        subplot_titles=(
            "BTC/USDT — daily close (Binance)",
            "Quote volume per UTC day (USDT)",
        ),
    )

    fig.add_trace(
        go.Scatter(
            x=df["date_utc"],
            y=df["btc_usd"],
            mode="lines",
            name="Close",
            line=dict(color=BTC_LINE, width=1.2),
            hovertemplate="Date: %{x|%Y-%m-%d}<br>Close: $%{y:,.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    # Разреженные числовые подписи к цене закрытия (не на каждой точке).
    btc_ok = df["btc_usd"].notna()
    btc_idx = df.index[btc_ok]
    if len(btc_idx) > 0:
        step = max(1, len(btc_idx) // 35)
        lab_pos = list(btc_idx[::step])
        if lab_pos[-1] != btc_idx[-1]:
            lab_pos.append(btc_idx[-1])
        lab_df = df.loc[lab_pos]
        fig.add_trace(
            go.Scatter(
                x=lab_df["date_utc"],
                y=lab_df["btc_usd"],
                mode="markers+text",
                name="Close labels",
                text=[f"${float(v):,.0f}" for v in lab_df["btc_usd"]],
                textposition="top center",
                textfont=dict(size=8, color=TEXT_COLOR),
                marker=dict(size=4, color=BTC_LINE),
                showlegend=False,
                hoverinfo="skip",
            ),
            row=1,
            col=1,
        )

    vol_text: list[str] = []
    for _, r in df.iterrows():
        if bool(r.get("show_btc_vol_label")) and pd.notna(r.get("btc_quote_usdt")):
            vol_text.append(_short_usdt_notation(float(r["btc_quote_usdt"])))
        else:
            vol_text.append("")

    base_series = df["btc_volume_btc"] if "btc_volume_btc" in df.columns else pd.Series([pd.NA] * len(df))
    fig.add_trace(
        go.Bar(
            x=df["date_utc"],
            y=df["btc_quote_usdt"],
            name="Quote volume",
            marker_color="#3d444d",
            text=vol_text,
            textposition="outside",
            outsidetextfont=dict(size=7, color=TEXT_COLOR),
            hovertemplate=(
                "Date: %{x|%Y-%m-%d}<br>Quote vol (USDT): %{y:,.0f}"
                "<br>Base vol (BTC): %{customdata}<extra></extra>"
            ),
            customdata=[
                f"{float(x):.4f}" if pd.notna(x) else "—" for x in base_series
            ],
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title="BTC — price and exchange volume (Binance BTCUSDT, 1d)",
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        font=dict(color=TEXT_COLOR),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=55, r=20, t=80, b=40),
        height=440,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#30363d", title="Date (UTC)", row=2, col=1)
    fig.update_xaxes(showgrid=True, gridcolor="#30363d", row=1, col=1)
    fig.update_yaxes(
        title_text="Close (USDT)",
        tickformat="$,.0f",
        showgrid=True,
        gridcolor="#30363d",
        row=1,
        col=1,
    )
    fig.update_yaxes(
        title_text="Quote vol (USDT)",
        showgrid=True,
        gridcolor="#30363d",
        row=2,
        col=1,
    )
    return fig


def figure_value_and_sma(df: pd.DataFrame) -> go.Figure:
    """Daily index and 30-day simple moving average."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["date_utc"],
            y=df["value"],
            mode="lines",
            name="Index",
            line=dict(color="#8b949e", width=1),
            hovertemplate="Date: %{x|%Y-%m-%d}<br>Index: %{y}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["date_utc"],
            y=df["sma_30"],
            mode="lines",
            name="SMA 30",
            line=dict(color="#3fb950", width=2),
            hovertemplate="Date: %{x|%Y-%m-%d}<br>SMA30: %{y:.1f}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Index and 30-day moving average",
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        font=dict(color=TEXT_COLOR),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        xaxis=dict(showgrid=True, gridcolor="#30363d", title="Date (UTC)"),
        yaxis=dict(
            range=[0, 100],
            title="Value",
            showgrid=True,
            gridcolor="#30363d",
        ),
        margin=dict(l=50, r=20, t=50, b=40),
        height=320,
    )
    return fig


def figure_histogram(df: pd.DataFrame) -> go.Figure:
    """Histogram of index values (how often each band occurs)."""
    fig = go.Figure(
        data=[
            go.Histogram(
                x=df["value"],
                nbinsx=20,
                name="Count",
                marker_color=ACCENT,
                hovertemplate="Bin center: %{x}<br>Days: %{y}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title="Distribution of index values",
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        font=dict(color=TEXT_COLOR),
        xaxis=dict(title="Index value", showgrid=True, gridcolor="#30363d"),
        yaxis=dict(title="Number of days", showgrid=True, gridcolor="#30363d"),
        margin=dict(l=50, r=20, t=50, b=40),
        height=320,
        bargap=0.05,
    )
    return fig


def figure_last_90_days(df: pd.DataFrame) -> go.Figure:
    """Last 90 days with a numeric label on every point."""
    tail = df.tail(90).copy()
    cls_text = tail["classification"].fillna("").astype(str) if "classification" in tail.columns else pd.Series([""] * len(tail))

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=tail["date_utc"],
            y=tail["value"],
            mode="lines+markers+text",
            name="Last 90 days",
            line=dict(color="#d29922", width=2),
            marker=dict(size=6),
            text=tail["value"].astype(str),
            textposition="top center",
            textfont=dict(size=8, color=TEXT_COLOR),
            hovertemplate=(
                "Date: %{x|%Y-%m-%d}<br>Value: %{y}<br>"
                "Classification: %{customdata}<extra></extra>"
            ),
            customdata=cls_text,
        )
    )
    fig.update_layout(
        title="Last 90 days (value label on each day)",
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        font=dict(color=TEXT_COLOR),
        xaxis=dict(showgrid=True, gridcolor="#30363d", title="Date (UTC)"),
        yaxis=dict(
            range=[0, 100],
            title="Value",
            showgrid=True,
            gridcolor="#30363d",
        ),
        margin=dict(l=50, r=20, t=50, b=40),
        height=320,
    )
    return fig


def figure_classification_counts(df: pd.DataFrame) -> go.Figure:
    """Bar chart: number of days per API classification label."""
    if "classification" not in df.columns or df["classification"].isna().all():
        fig = go.Figure()
        fig.update_layout(
            title="Days per classification (no data)",
            paper_bgcolor=CARD,
            plot_bgcolor=CARD,
            font=dict(color=TEXT_COLOR),
            height=280,
        )
        return fig

    counts = df["classification"].fillna("—").value_counts()
    fig = go.Figure(
        data=[
            go.Bar(
                x=counts.index.astype(str),
                y=counts.values,
                marker_color="#a371f7",
                hovertemplate="%{x}<br>Days: %{y}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title="Number of days by sentiment category",
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        font=dict(color=TEXT_COLOR),
        xaxis=dict(title="Category", tickangle=-25),
        yaxis=dict(title="Days", showgrid=True, gridcolor="#30363d"),
        margin=dict(l=50, r=20, t=50, b=80),
        height=280,
    )
    return fig


def empty_dashboard_layout() -> html.Div:
    """Dark empty state when the database has no rows yet."""
    return html.Div(
        [
            html.H1(
                "Crypto Fear & Greed Dashboard",
                style={"margin": "0 0 8px 0", "fontSize": "1.4rem"},
            ),
            html.P(
                "No data yet. Run a sync (or wait for the next scheduled job) and refresh.",
                style={"margin": "0", "opacity": 0.9},
            ),
            methodology_header(),
        ],
        style=PAGE_SHELL_STYLE,
    )


def build_dashboard_inner(df: pd.DataFrame) -> html.Div:
    """
    Блок графиков: только Market sentiment (gauge + пули) и Fear & Greed vs BTC.

    Используется при первой отрисовке и из callback после смены дат в DatePickerRange.
    """
    last_date = df["date_utc"].max().strftime("%Y-%m-%d")
    last_row = df.iloc[-1]
    last_val = int(last_row["value"])
    last_cls = str(last_row.get("classification", "") or "—")
    last_date_str = pd.Timestamp(last_row["date_utc"]).strftime("%Y-%m-%d")
    stats = compute_hero_stats(df)
    if stats is None:
        return html.Div(
            "Not enough data for this range.",
            style={"padding": "24px", "opacity": 0.85},
        )

    # --- Первый экран: слева спидометр + исторические значения, справа основной график ---
    hero_sidebar = html.Div(
        [
            html.H2(
                "Market sentiment",
                style={
                    "margin": "0 0 10px 0",
                    "fontSize": "1.05rem",
                    "fontWeight": "600",
                    "opacity": 0.95,
                },
            ),
            dcc.Graph(
                figure=figure_fng_gauge(last_val, last_cls, last_date_str),
                config=GRAPH_CONFIG,
                style={"height": "310px", "width": "100%"},
            ),
            html.Div(
                [
                    _hero_stat_row(stats.yesterday_label, stats.yesterday_value),
                    _hero_stat_row(stats.week_avg_label, stats.week_avg_value),
                    _hero_stat_row(stats.month_avg_label, stats.month_avg_value, with_bottom_border=False),
                ],
                style={"marginTop": "6px"},
            ),
        ],
        style={
            "flex": "0 0 22%",
            "width": "22%",
            "minWidth": "240px",
            "maxWidth": "360px",
            "padding": "16px 18px",
            "backgroundColor": CARD,
            "borderRadius": "12px",
            "border": "1px solid #30363d",
            "boxSizing": "border-box",
        },
    )

    hero_chart = html.Div(
        [
            html.H2(
                "Fear & Greed vs BTC",
                style={
                    "margin": "0 0 8px 0",
                    "fontSize": "1.05rem",
                    "fontWeight": "600",
                    "opacity": 0.95,
                    "flexShrink": "0",
                },
            ),
            html.Div(
                dcc.Graph(
                    figure=figure_full_timeline(df),
                    config=GRAPH_CONFIG,
                    className="fng-main-chart",
                    style={"width": "100%", "height": f"{MAIN_CHART_HEIGHT}px"},
                ),
                className="fng-chart-wrap",
            ),
        ],
        style={
            "flex": "1 1 0",
            "minWidth": "min(100%, 480px)",
            "padding": "12px 10px 10px",
            "backgroundColor": CARD,
            "borderRadius": "12px",
            "border": "1px solid #30363d",
            "boxSizing": "border-box",
            "display": "flex",
            "flexDirection": "column",
            "minHeight": "480px",
        },
    )

    hero_row = html.Div(
        [hero_sidebar, hero_chart],
        style={
            "display": "flex",
            "flexWrap": "wrap",
            "gap": "16px",
            "alignItems": "stretch",
            "width": "100%",
        },
    )

    meta = html.P(
        f"Observations in view: {len(df):,} · Last date in range (UTC): {last_date}",
        style={"margin": "0 0 12px 0", "opacity": 0.85, "fontSize": "0.9rem"},
    )

    return html.Div([meta, hero_row], style={"width": "100%"})


def _date_picker_column(df: pd.DataFrame) -> html.Div:
    """Колонка 20% ширины: календарный выбор начала и конца периода (UTC)."""
    d_first = pd.Timestamp(df["date_utc"].iloc[0]).strftime("%Y-%m-%d")
    d_last = pd.Timestamp(df["date_utc"].iloc[-1]).strftime("%Y-%m-%d")
    return html.Div(
        [
            html.Strong("Date range (UTC)", style={"fontSize": "0.9rem", "display": "block", "marginBottom": "10px"}),
            dcc.DatePickerRange(
                id=DASH_DATE_PICKER_ID,
                start_date=d_first,
                end_date=d_last,
                min_date_allowed=d_first,
                max_date_allowed=d_last,
                display_format="YYYY-MM-DD",
                minimum_nights=0,
                clearable=False,
            ),
            html.Div(
                id=DASH_RANGE_HINT_ID,
                children=_calendar_range_hint(d_first, d_last, len(df)),
                style={"marginTop": "12px", "fontSize": "0.8rem", "lineHeight": 1.45, "opacity": 0.9},
            ),
        ],
        style={
            "boxSizing": "border-box",
            "padding": "14px 12px",
            "height": "100%",
        },
    )


def _page_top_row(df: pd.DataFrame) -> html.Div:
    """
    Верх страницы: 80% — описание и раскрывающаяся методология; 20% — DatePickerRange.
    """
    card_base = {
        "backgroundColor": CARD,
        "borderRadius": "12px",
        "border": "1px solid #30363d",
        "boxSizing": "border-box",
    }
    return html.Div(
        [
            html.Div(
                methodology_header(),
                style={
                    **card_base,
                    "flex": "0 0 80%",
                    "width": "80%",
                    "maxWidth": "80%",
                    "padding": "16px 20px",
                },
            ),
            html.Div(
                _date_picker_column(df),
                style={
                    **card_base,
                    "flex": "0 0 20%",
                    "width": "20%",
                    "maxWidth": "20%",
                },
            ),
        ],
        style={
            "display": "flex",
            "flexWrap": "nowrap",
            "alignItems": "stretch",
            "gap": "14px",
            "width": "100%",
            "marginBottom": "20px",
        },
    )


def _fng_path_active(pathname: str | None) -> bool:
    """True для маршрутов /fng/ (с учётом routes_pathname_prefix)."""
    if not pathname:
        return False
    path = pathname.rstrip("/")
    return path.endswith("/fng") or path == "/fng"


def _core_columns(df: pd.DataFrame) -> list[str]:
    return [
        c
        for c in ("date_utc", "value", "classification", "btc_usd", "btc_volume_btc", "btc_quote_usdt")
        if c in df.columns
    ]


def _pack_dashboard_payload(df: pd.DataFrame) -> tuple[list | None, str, html.Div, html.Div]:
    """
    Готовит Store + мета + верхнюю строку + графики из уже загруженного DataFrame.

    Возвращает кортеж для Outputs bootstrap-callback.
    """
    df = prepare_df_for_charts(df)
    if len(df) == 0 or compute_hero_stats(df) is None:
        return (
            None,
            "No chartable data in the database yet.",
            html.Div(methodology_header(), style={"marginBottom": "12px"}),
            html.Div("Waiting for a successful data sync.", style={"padding": "20px", "opacity": 0.9}),
        )

    records = dataframe_to_store_records(df[_core_columns(df)])
    last_date = df["date_utc"].max().strftime("%Y-%m-%d")
    meta = f"Full series: {len(df):,} observations · Last date (UTC): {last_date}"
    return records, meta, _page_top_row(df), build_dashboard_inner(df)


def build_dashboard_shell_layout() -> html.Div:
    """
    Лёгкая оболочка страницы /fng/: отдаётся сразу, без запроса к БД и без Plotly.

    Данные и графики подгружаются в callback _bootstrap_dashboard (см. dcc.Loading).
    """
    return html.Div(
        [
            dcc.Location(id=FNG_URL_ID, refresh=False),
            dcc.Store(id=DASH_DF_STORE_ID, data=None),
            html.H1(
                "Crypto Fear & Greed Index",
                style={"margin": "0 0 6px 0", "fontSize": "1.4rem"},
            ),
            # Вводный абзац с целевой фразой — текст для пользователей и поисковика.
            html.P(
                "Live crypto fear and greed index: a daily 0–100 market sentiment gauge with "
                "full history and the Bitcoin (BTC) price and volume alongside it.",
                style={"margin": "0 0 12px 0", "opacity": 0.9, "fontSize": "0.95rem", "maxWidth": "760px"},
            ),
            html.Div(
                id=FNG_PAGE_META_ID,
                children="Loading market data…",
                style={"margin": "0 0 14px 0", "opacity": 0.85, "fontSize": "0.9rem"},
            ),
            dcc.Loading(
                id=FNG_PAGE_LOADING_ID,
                type="circle",
                color=ACCENT,
                className="fng-dash-loading",
                children=html.Div(
                    [
                        html.Div(id=FNG_TOP_ROW_ID),
                        html.Div(id=DASH_CHARTS_OUTLET_ID),
                    ],
                ),
            ),
        ],
        style=PAGE_SHELL_STYLE,
    )


def register_dash_callbacks(app: Dash) -> None:
    """
    Bootstrap при открытии /fng/ и callback фильтра по DatePickerRange.

    Вызывать один раз после создания Dash(app).
    """

    @app.callback(
        Output(DASH_DF_STORE_ID, "data"),
        Output(FNG_PAGE_META_ID, "children"),
        Output(FNG_TOP_ROW_ID, "children"),
        Output(DASH_CHARTS_OUTLET_ID, "children"),
        Input(FNG_URL_ID, "pathname"),
        prevent_initial_call=False,
    )
    def _bootstrap_dashboard(pathname: str | None) -> tuple:
        if not _fng_path_active(pathname):
            raise PreventUpdate

        df = load_fng_dataframe(get_engine())
        if df.empty:
            return (
                None,
                "No data yet. Run a sync (or wait for the next scheduled job) and refresh.",
                html.Div(methodology_header()),
                html.Div(
                    "Database is empty.",
                    style={"padding": "20px", "opacity": 0.9},
                ),
            )

        return _pack_dashboard_payload(df)

    @app.callback(
        Output(DASH_CHARTS_OUTLET_ID, "children", allow_duplicate=True),
        Output(DASH_RANGE_HINT_ID, "children"),
        Input(DASH_DATE_PICKER_ID, "start_date"),
        Input(DASH_DATE_PICKER_ID, "end_date"),
        State(DASH_DF_STORE_ID, "data"),
        prevent_initial_call=True,
    )
    def _apply_date_picker_range(
        start_date: str | None,
        end_date: str | None,
        store_data: list | None,
    ) -> tuple[html.Div, str]:
        if not store_data:
            return (
                html.Div("No series data in session.", style={"padding": "20px"}),
                "",
            )

        df_core = dataframe_from_store_records(store_data)
        if df_core.empty:
            return (
                html.Div("Empty series.", style={"padding": "20px"}),
                "",
            )

        df_full = prepare_df_for_charts(df_core)
        sub = _slice_df_by_calendar_range(df_full, start_date, end_date)

        inner = build_dashboard_inner(sub)
        hint = _calendar_range_hint(start_date, end_date, len(sub))
        return inner, hint
