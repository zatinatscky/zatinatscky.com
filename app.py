"""
Единая точка входа для Render:
- отдает текущий статический сайт-визитку;
- поднимает Dash на /dash/ с графиками Fear & Greed.

Данные индекса хранятся в PostgreSQL (DATABASE_URL на Render).
"""

from __future__ import annotations

import os
from hmac import compare_digest
from pathlib import Path

import dash
import plotly.express as px
from dash import Dash, dcc, html
from flask import Flask, abort, redirect, request, send_from_directory

from fng_data import full_refresh, get_engine, load_fng_dataframe


ROOT_DIR = Path(__file__).resolve().parent
CRON_TOKEN = os.getenv("CRON_TOKEN", "")


def create_server() -> Flask:
    """
    Flask-сервер:
    - обслуживает существующие html/css/js;
    - выступает host-сервером для Dash.
    """
    server = Flask(__name__)

    engine = get_engine()

    # Заполняем БД на старте, чтобы дашборд сразу имел актуальные данные.
    # Можно отключить через env AUTO_SYNC_ON_START=false.
    if os.getenv("AUTO_SYNC_ON_START", "true").lower() == "true":
        full_refresh(engine)

    @server.get("/")
    def home():
        return send_from_directory(ROOT_DIR, "index.html")

    @server.get("/about.html")
    def about():
        return send_from_directory(ROOT_DIR, "about.html")

    @server.get("/articles.html")
    def articles():
        return send_from_directory(ROOT_DIR, "articles.html")

    @server.get("/products.html")
    def products():
        return send_from_directory(ROOT_DIR, "products.html")

    @server.get("/css/<path:filename>")
    def css(filename: str):
        return send_from_directory(ROOT_DIR / "css", filename)

    @server.get("/js/<path:filename>")
    def js(filename: str):
        return send_from_directory(ROOT_DIR / "js", filename)

    @server.get("/en/<path:filename>")
    def en_pages(filename: str):
        return send_from_directory(ROOT_DIR / "en", filename)

    @server.get("/dash")
    def dash_redirect():
        # Канонический URL Dash со слэшем в конце.
        return redirect("/dash/", code=302)

    @server.get("/health")
    def health():
        return {"status": "ok"}

    @server.get("/jobs/fng-sync")
    def sync_job():
        """
        Эндпоинт для Render Cron.

        Защита: ?token=... и compare_digest с CRON_TOKEN.
        """
        req_token = str(request.args.get("token", ""))
        if not CRON_TOKEN or not compare_digest(req_token, CRON_TOKEN):
            return {"status": "forbidden"}, 403

        upserted = full_refresh(get_engine())
        return {"status": "ok", "upserted": upserted}

    @server.errorhandler(404)
    def not_found(_err):
        abort(404)

    return server


def build_dash(server: Flask) -> Dash:
    """Создает Dash-приложение поверх существующего Flask-сервера."""
    dash_app = Dash(
        __name__,
        server=server,
        routes_pathname_prefix="/dash/",
        title="Fear & Greed Dashboard",
    )

    df = load_fng_dataframe(get_engine())
    if df.empty:
        dash_app.layout = html.Div(
            [
                html.H1("Fear & Greed dashboard"),
                html.P("No data yet. Run sync and refresh page."),
            ],
            style={"fontFamily": "monospace", "padding": "24px"},
        )
        return dash_app

    fig_index = px.line(
        df,
        x="date_utc",
        y="value",
        title="Fear & Greed Index Over Time",
        labels={"date_utc": "Date (UTC)", "value": "Index value"},
    )
    fig_index.update_traces(line={"width": 2}, name="Daily index")

    fig_rolling = px.line(
        df,
        x="date_utc",
        y="rolling_30d",
        title="30-Day Rolling Average",
        labels={"date_utc": "Date (UTC)", "rolling_30d": "Rolling avg"},
    )
    fig_rolling.update_traces(line={"width": 2}, name="30d average")

    class_counts = (
        df.groupby("classification", dropna=False)["value"]
        .count()
        .reset_index(name="points")
        .sort_values("points", ascending=False)
    )
    fig_classes = px.bar(
        class_counts,
        x="classification",
        y="points",
        title="Distribution by Classification",
        labels={"classification": "Classification", "points": "Data points"},
    )

    dash_app.layout = html.Div(
        [
            html.H1("Crypto Fear & Greed Dashboard"),
            html.P(
                "Source: alternative.me/fng API. "
                "Data stored in PostgreSQL (DATABASE_URL).",
            ),
            dcc.Graph(figure=fig_index),
            dcc.Graph(figure=fig_rolling),
            dcc.Graph(figure=fig_classes),
        ],
        style={"fontFamily": "Arial, sans-serif", "maxWidth": "1200px", "margin": "0 auto"},
    )
    return dash_app


server = create_server()
dash_app = build_dash(server)


if __name__ == "__main__":
    server.run(host="0.0.0.0", port=int(os.getenv("PORT", "8050")), debug=True)
