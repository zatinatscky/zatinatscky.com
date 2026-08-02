# zatinatscky.com / IVAN

Монорепозиторий двух сайтов на одном VPS:

- **`zatinatscky.com`** — статичный сайт-визитка (консалтинг, RU/EN).
- **`ivan.zatinatscky.com`** — продукт **IVAN** (*Index Volatility Alerts & Notifications*): Index Terminal (сетка + страница на каждый индекс) и дашборд Fear & Greed (`/fng/`).

---

## 1. Техническая часть

### Технологии и их применение

| Технология | Зачем используется |
|------------|--------------------|
| **Python 3.12** | Язык бэкенда |
| **Flask** | Веб-сервер: роутинг, отдача статики, host-aware логика, API |
| **Dash + Plotly** | Интерактивный дашборд `/fng/` и графики |
| **pandas** | Подготовка и агрегация рядов данных индекса |
| **PostgreSQL** | Хранилище исторических данных индексов |
| **SQLAlchemy + psycopg v3** | ORM/доступ к БД (URL вида `postgresql+psycopg://`) |
| **gunicorn** | WSGI-сервер в продакшене |
| **Docker + Docker Compose** | Сборка и оркестрация сервисов `web` / `db` / `caddy` |
| **Caddy** | Реверс-прокси + автоматический HTTPS (Let's Encrypt) |
| **systemd timers** | Ежедневная синхронизация данных и бэкапы БД |
| **requests** | Загрузка данных из внешних источников (Binance, F&G API) |

### Логические блоки

- **Точка входа `app.py`** — собирает Flask-приложение, монтирует Dash, реализует **host-aware роутинг**: по `Host` решает, что отдать (визитка vs IVAN), а также `robots.txt`/`sitemap.xml` под каждый домен. Есть API `/api/fng/latest` для живого hero-блока.
- **Слой данных `fng_data.py`** — подключение к Postgres, полная/инкрементальная загрузка истории индекса, нормализация `DATABASE_URL`.
- **Дашборд `fng_dash_layout.py`** — layout и колбэки Dash: «скелетон» при загрузке, графики, фильтр по датам, логотип-ссылка на главную.
- **Продукт IVAN `ivan/`** — Index Terminal: `home.html` + страницы `/i/<id>`, общие модули `js/` (mock-данные, UI на React CDN), `css/terminal.css`, favicon/OG.
- **Дашборд Dash `/fng/`** — отдельный интерактивный Fear & Greed (Plotly); пока живёт рядом с Terminal.
- **Статичный сайт** — `index.html`, `about.html`, `articles.html`, `products.html`, `en/` (английская версия), `css/`, `js/`.
- **Деплой `deploy/` + конфиги** — `Dockerfile`, `docker-compose.yml`, `Caddyfile`, скрипты `fng-sync.*` (синхронизация) и `backup.sh` (бэкап БД).
- **SEO** — мета-теги, Open Graph, JSON-LD (Schema.org), `robots.txt`, `sitemap.xml`.

### Запуск

```bash
# Локально
pip install -r requirements.txt
python app.py            # http://localhost:8050

# Продакшен (VPS)
cp .env.example .env     # заполнить секреты
docker compose up -d --build
```

Подробные инструкции: `DEPLOY_VPS.md` (VPS) и `DEPLOY_RENDER.md` (Render).

---

## 2. Дневник разработки

Кратко, по коммитам (от старых к новым).

**2026-05-11 — Старт.** Статичный сайт-визитка (RU/EN, эффект печатной машинки, стили). Привязка домена `zatinatscky.com` через CNAME.

**2026-05-13 — Бэкенд и данные.** Деплой Flask/Dash на Render: слой данных на Postgres и cron-скрипты. Перешли на psycopg v3 (готовые колёса, без `pg_config`), облегчили cron-сборку. Layout Dash пересобирается на каждый заход — свежие данные и стабильный UI.

**2026-05-26 — Продукт IVAN.** Полноценный дашборд: данные BTC с Binance, фильтр по датам, доки по субдомену. Корень субдомена редиректит на дашборд (`DASH_ROOT_HOST`). Добавлена welcome-страница IVAN, Fear & Greed переехал на `/fng/`. Заголовок на экране загрузки + фикс welcome при пустом `DASH_ROOT_HOST`.

**2026-06-09 — Свой сервер.** Уход с Render на VPS: Docker Compose, Caddy с авто-HTTPS, systemd-таймер синхронизации и бэкапы. Подчистили случайно закоммиченный файл.

**2026-06-11 — SEO.** Технический SEO для `/fng/`: мета-теги, Open Graph, JSON-LD, `robots.txt`, `sitemap.xml`.

**2026-06-14 — Апекс на VPS.** Логотип IVAN со ссылкой на главную на странице `/fng/`. Апекс `zatinatscky.com` переехал с GitHub Pages на тот же VPS: host-aware `robots`/`sitemap`, маршрут `/en/`, self-hosted Inter; Caddy обслуживает оба домена.
