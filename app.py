"""
Единая точка входа для Render:
- отдает текущий статический сайт-визитку;
- поднимает Dash на /dash/ с графиками Fear & Greed.

Данные индекса хранятся в PostgreSQL (DATABASE_URL на Render).
"""

from __future__ import annotations

import logging
import os
from hmac import compare_digest
from pathlib import Path

from dash import Dash
from flask import Flask, abort, redirect, request, send_from_directory

from fng_data import full_refresh, get_engine, load_fng_dataframe
from fng_dash_layout import build_dashboard_layout, empty_dashboard_layout, register_dash_callbacks


ROOT_DIR = Path(__file__).resolve().parent
CRON_TOKEN = os.getenv("CRON_TOKEN", "")


def _ensure_stdio_logging() -> None:
    """
    Локально и под gunicorn: если корневой логгер ещё без обработчиков — пишем INFO в stderr.

    Уровень можно переопределить: LOG_LEVEL=DEBUG
    """
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO))
        return
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def create_server() -> Flask:
    """
    Flask-сервер:
    - обслуживает существующие html/css/js;
    - выступает host-сервером для Dash.
    """
    server = Flask(__name__)

    _ensure_stdio_logging()

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


def _dash_layout():
    """
    Собирает layout при каждом открытии /dash/ в браузере (см. fng_dash_layout).
    """
    engine = get_engine()
    df = load_fng_dataframe(engine)
    if df.empty:
        return empty_dashboard_layout()
    return build_dashboard_layout(df)


def build_dash(server: Flask) -> Dash:
    """Создает Dash-приложение поверх существующего Flask-сервера."""
    dash_app = Dash(
        __name__,
        server=server,
        routes_pathname_prefix="/dash/",
        title="Crypto Fear & Greed",
    )

    # Функция layout — Dash вызывает её при загрузке страницы (свежие данные из БД).
    dash_app.layout = _dash_layout
    register_dash_callbacks(dash_app)
    return dash_app


server = create_server()
dash_app = build_dash(server)


if __name__ == "__main__":
    server.run(host="0.0.0.0", port=int(os.getenv("PORT", "8050")), debug=True)
