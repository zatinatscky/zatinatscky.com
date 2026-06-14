"""
Единая точка входа для Render:
- отдает статический сайт-визитку (корень на onrender.com);
- на DASH_ROOT_HOST (ivan.*) — welcome IVAN и дашборды (например /fng/);
- данные индексов — PostgreSQL (DATABASE_URL на Render).
"""

from __future__ import annotations

import json
import logging
import os
from hmac import compare_digest
from pathlib import Path

from dash import Dash
from flask import Flask, Response, abort, redirect, request, send_from_directory
from sqlalchemy import text

from fng_data import full_refresh, get_engine
from fng_dash_layout import build_dashboard_shell_layout, register_dash_callbacks


ROOT_DIR = Path(__file__).resolve().parent
IVAN_DIR = ROOT_DIR / "ivan"
CRON_TOKEN = os.getenv("CRON_TOKEN", "")
# Host, на котором / — welcome IVAN (не визитка). На Render задайте в Environment или оставьте default.
DASH_ROOT_HOST = os.getenv("DASH_ROOT_HOST", "ivan.zatinatscky.com").strip().lower()
# Пустая строка в env отключает привязку к субдомену (удобно для особых деплоев).
if os.getenv("DASH_ROOT_HOST") == "":
    DASH_ROOT_HOST = ""


def _is_ivan_host() -> bool:
    """True, если запрос на выделенный Host продукта IVAN."""
    if not DASH_ROOT_HOST:
        return False
    host = request.host.split(":", 1)[0].lower()
    return host == DASH_ROOT_HOST


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
        # На ivan.* — welcome продукта IVAN; на onrender.com — визитка из репозитория.
        if _is_ivan_host():
            return send_from_directory(IVAN_DIR, "welcome.html")
        return send_from_directory(ROOT_DIR, "index.html")

    @server.get("/ivan/<path:filename>")
    def ivan_static(filename: str):
        """Статика welcome-страницы (CSS и будущие ассеты)."""
        return send_from_directory(IVAN_DIR, filename)

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

    @server.get("/en/")
    def en_home():
        # GitHub Pages отдавал /en/ как index.html; на Flask нужен явный роут.
        return send_from_directory(ROOT_DIR / "en", "index.html")

    @server.get("/en/<path:filename>")
    def en_pages(filename: str):
        return send_from_directory(ROOT_DIR / "en", filename)

    @server.get("/fng")
    def fng_redirect():
        # Канонический URL Fear & Greed Dash со слэшем в конце.
        return redirect("/fng/", code=302)

    @server.get("/dash")
    @server.get("/dash/")
    def dash_legacy_redirect():
        # Старый путь — редирект на /fng/.
        return redirect("/fng/", code=301)

    @server.get("/dash/<path:subpath>")
    def dash_legacy_subpath_redirect(subpath: str):
        return redirect(f"/fng/{subpath}", code=301)

    @server.get("/health")
    def health():
        return {"status": "ok"}

    @server.get("/api/fng/latest")
    def api_fng_latest():
        """Последнее значение Fear & Greed + ряд за 30 дней (для живого hero на welcome)."""
        try:
            engine = get_engine()
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT date_utc, value, classification "
                        "FROM fear_greed_index ORDER BY date_utc DESC LIMIT 30"
                    )
                ).fetchall()
        except Exception:
            return {"error": "unavailable"}, 503

        if not rows:
            return {"error": "no data"}, 404

        ordered = list(reversed(rows))  # из убывания дат → в хронологический порядок
        latest = ordered[-1]
        return {
            "value": int(latest[1]),
            "classification": str(latest[2] or ""),
            "date": str(latest[0])[:10],
            "history": [int(r[1]) for r in ordered],
        }

    @server.get("/robots.txt")
    def robots_txt():
        """robots зависит от Host: ivan.* — продукт, апекс — статический файл консалтинга."""
        if _is_ivan_host():
            body = (
                "User-agent: *\n"
                "Allow: /\n"
                "Sitemap: https://ivan.zatinatscky.com/sitemap.xml\n"
            )
            return Response(body, mimetype="text/plain")
        # Апекс zatinatscky.com — robots из репозитория (консалтинг).
        return send_from_directory(ROOT_DIR, "robots.txt")

    @server.get("/sitemap.xml")
    def sitemap_xml():
        """sitemap зависит от Host: ivan.* — дашборды, апекс — статический файл консалтинга."""
        if _is_ivan_host():
            pages = [
                ("https://ivan.zatinatscky.com/", "1.0", "weekly"),
                ("https://ivan.zatinatscky.com/fng/", "0.9", "daily"),
            ]
            items = "".join(
                f"<url><loc>{loc}</loc>"
                f"<changefreq>{freq}</changefreq>"
                f"<priority>{pr}</priority></url>"
                for loc, pr, freq in pages
            )
            xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"{items}</urlset>"
            )
            return Response(xml, mimetype="application/xml")
        # Апекс zatinatscky.com — sitemap из репозитория (консалтинг).
        return send_from_directory(ROOT_DIR, "sitemap.xml")

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


# --- SEO для страницы /fng/ (целевая фраза: "crypto fear and greed index") ---
SITE_BASE_URL_PUBLIC = "https://ivan.zatinatscky.com"
FNG_PAGE_URL = f"{SITE_BASE_URL_PUBLIC}/fng/"
FNG_PAGE_TITLE = "Crypto Fear & Greed Index — Live Chart, History & BTC"
FNG_PAGE_DESCRIPTION = (
    "Live crypto fear and greed index: a daily 0–100 market sentiment gauge with full "
    "historical chart and Bitcoin (BTC) price and volume overlay. Track whether the crypto "
    "market is in fear or greed."
)

# Мета-теги в <head> (рендерятся Dash в {%metas%}).
FNG_META_TAGS = [
    {"name": "viewport", "content": "width=device-width, initial-scale=1"},
    {"name": "description", "content": FNG_PAGE_DESCRIPTION},
    {
        "name": "keywords",
        "content": (
            "crypto fear and greed index, fear and greed index, bitcoin fear and greed, "
            "crypto market sentiment, btc sentiment index, fear greed chart"
        ),
    },
    {"name": "robots", "content": "index, follow"},
    # Open Graph (превью в соцсетях/мессенджерах).
    {"property": "og:type", "content": "website"},
    {"property": "og:site_name", "content": "IVAN"},
    {"property": "og:title", "content": FNG_PAGE_TITLE},
    {"property": "og:description", "content": FNG_PAGE_DESCRIPTION},
    {"property": "og:url", "content": FNG_PAGE_URL},
    {"property": "og:image", "content": f"{SITE_BASE_URL_PUBLIC}/ivan/og-image.png"},
    # Twitter Card.
    {"name": "twitter:card", "content": "summary_large_image"},
    {"name": "twitter:title", "content": FNG_PAGE_TITLE},
    {"name": "twitter:description", "content": FNG_PAGE_DESCRIPTION},
    {"name": "twitter:image", "content": f"{SITE_BASE_URL_PUBLIC}/ivan/og-image.png"},
]

# Структурированные данные: тип приложения + FAQ (шанс на rich snippet в Google).
_FNG_JSONLD = {
    "@context": "https://schema.org",
    "@graph": [
        {
            "@type": "WebApplication",
            "name": "Crypto Fear & Greed Index",
            "url": FNG_PAGE_URL,
            "applicationCategory": "FinanceApplication",
            "operatingSystem": "Web",
            "description": FNG_PAGE_DESCRIPTION,
            "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        },
        {
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": "What is the crypto fear and greed index?",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": (
                            "The crypto fear and greed index is a 0–100 score that summarizes "
                            "Bitcoin and crypto market sentiment. Low values mean fear, high "
                            "values mean greed."
                        ),
                    },
                },
                {
                    "@type": "Question",
                    "name": "How is the fear and greed index calculated?",
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": (
                            "It combines volatility, market momentum and volume, social media, "
                            "Bitcoin dominance, and surveys into a single daily 0–100 value."
                        ),
                    },
                },
            ],
        },
    ],
}
FNG_JSONLD = json.dumps(_FNG_JSONLD, ensure_ascii=False)

# Текст, видимый поисковику и пользователям без JavaScript (Dash рисует UI через JS).
FNG_NOSCRIPT = (
    '<div style="max-width:820px;margin:0 auto;padding:28px;color:#e6edf3;'
    'background:#0f1419;font-family:-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.6;">'
    "<h1>Crypto Fear &amp; Greed Index</h1>"
    "<p>The <strong>crypto fear and greed index</strong> is a daily 0–100 gauge of Bitcoin and "
    "cryptocurrency market sentiment. A low score signals fear, a high score signals greed. "
    "This page shows the live value, the full history, and the BTC price and volume alongside it.</p>"
    "<h2>How to read the index</h2>"
    "<ul>"
    "<li><strong>0–24 — Extreme Fear:</strong> investors are very worried.</li>"
    "<li><strong>25–49 — Fear:</strong> cautious, risk-off mood.</li>"
    "<li><strong>50 — Neutral.</strong></li>"
    "<li><strong>51–74 — Greed:</strong> growing optimism.</li>"
    "<li><strong>75–100 — Extreme Greed:</strong> market may be overheated.</li>"
    "</ul>"
    "<p>Enable JavaScript to view the interactive fear and greed chart and BTC overlay.</p>"
    "</div>"
)

# Кастомный шаблон HTML: canonical + JSON-LD + noscript поверх стандартных плейсхолдеров Dash.
FNG_INDEX_STRING = (
    "<!DOCTYPE html>\n"
    '<html lang="en">\n'
    "<head>\n"
    "{%metas%}\n"
    "<title>{%title%}</title>\n"
    f'<link rel="canonical" href="{FNG_PAGE_URL}" />\n'
    '<link rel="icon" type="image/png" href="/ivan/favicon.png" />\n'
    "{%favicon%}\n"
    "{%css%}\n"
    f'<script type="application/ld+json">{FNG_JSONLD}</script>\n'
    "</head>\n"
    "<body>\n"
    "{%app_entry%}\n"
    f"<noscript>{FNG_NOSCRIPT}</noscript>\n"
    "<footer>\n"
    "{%config%}\n{%scripts%}\n{%renderer%}\n"
    "</footer>\n"
    "</body>\n"
    "</html>"
)


def build_dash(server: Flask) -> Dash:
    """Создает Dash-приложение поверх существующего Flask-сервера."""
    dash_app = Dash(
        __name__,
        server=server,
        routes_pathname_prefix="/fng/",
        requests_pathname_prefix="/fng/",
        title=FNG_PAGE_TITLE,
        meta_tags=FNG_META_TAGS,
    )
    # Шаблон с canonical/JSON-LD/noscript для индексации поисковиком.
    dash_app.index_string = FNG_INDEX_STRING

    # Оболочка сразу; данные и Plotly — в bootstrap-callback (см. fng_dash_layout).
    dash_app.layout = build_dashboard_shell_layout()
    register_dash_callbacks(dash_app)
    return dash_app


server = create_server()
dash_app = build_dash(server)


if __name__ == "__main__":
    server.run(host="0.0.0.0", port=int(os.getenv("PORT", "8050")), debug=True)
