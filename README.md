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
| **requests** | Загрузка данных из внешних источников (FRED, Binance, Deribit, ЕЦБ и др.) |

### Логические блоки

- **Точка входа `app.py`** — собирает Flask-приложение, монтирует Dash, реализует **host-aware роутинг**: по `Host` решает, что отдать (визитка vs IVAN), а также `robots.txt`/`sitemap.xml` под каждый домен. API: `/api/fng/latest` для живого hero-блока, `/api/indexes` для терминала, `/api/auth/*` и `/api/me*` для Google/Telegram login и sync watchlist.
- **Авторизация `auth/`** — Google OAuth + Telegram Login Widget, cookie-сессия, watchlist в Postgres после входа (до входа — localStorage).
- **Слой данных `fng_data.py`** — подключение к Postgres, полная/инкрементальная загрузка истории Fear & Greed и цен BTC, нормализация `DATABASE_URL`.
- **Слой индексов `indices/`** — реальные данные терминала (см. раздел «Данные индексов» ниже).
- **Дашборд `fng_dash_layout.py`** — layout и колбэки Dash: «скелетон» при загрузке, графики, фильтр по датам, логотип-ссылка на главную.
- **Продукт IVAN `ivan/`** — Index Terminal: `home.html` + страницы `/i/<id>`, общие модули `js/` (`data-api.js` — загрузка из API, UI на React CDN), `css/terminal.css`, favicon/OG.
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

### Данные индексов

Терминал работает на реальных данных: мок-генератор удалён, значения приходят из
БД через `GET /api/indexes`. Если API недоступен, страница показывает ошибку и
предложение повторить — подставлять сгенерированные значения вместо рыночных
нельзя.

**Отбор индексов.** В терминал попадает индекс, который можно забирать напрямую и
обновлять раз в сутки. По этому критерию не вошли месячные показатели (US CPI,
China PMI, ifo, NY Fed GSCPI), EURO STOXX 50 / золото / BCOM (единственный
бесплатный источник — неофициальный Yahoo Finance, отвечает 429 при регулярных
обращениях) и BTC Dominance (бесплатной истории общей капитализации рынка нет).

**Источники — 14 индексов, все бесплатные и без ключей:**

| Источник | Индексы |
|---|---|
| FRED (`fredgraph.csv`) | `vix`, `spx`, `nikkei`, `brent`, `us10y` |
| CBOE (`VIX_History.csv`) | резерв для `vix` |
| Alternative.me | `fng` |
| Deribit DVOL | `bvol` |
| bitcoin-data.com | `nupl`, `mvrv` |
| Binance Futures | `funding` |
| CNN Business | `cnnfng` |
| Binance + CoinGecko | `altseason` (доля топ-50, обогнавших BTC за 90 дней) |
| Binance + blockchain.info + DefiLlama | `ssr` (капитализация BTC / supply стейблкоинов) |
| Курсы ЕЦБ | `dxy` (открытая формула DXY по дневному фиксингу) |

Особенности источников, из-за которых пришлось развести настройки: **FRED
подвешивает соединение на браузерном User-Agent** и требует утилитного, а **Yahoo
и CNN — наоборот**, без браузерного отвечают 403 / «You're a bot». bitcoin-data.com
и Yahoo лимитируют частоту, поэтому у них троттлинг между запросами.

**Схема БД.** Таблицы `index_meta` (описания + результат последней синхронизации) и
`index_observation` (`index_id`, `date_utc`, `value`, `volume`). Ряды приводятся к
общему календарю forward-fill'ом в `indices/series.py`: биржи не торгуют в
выходные, и без этого даты на графике разъехались бы со значениями. Таблицы
`fear_greed_index` и `btc_usd_daily` живут отдельно — на них работает `/fng/`.

**Объёмы.** Столбец `volume` лежит в той же строке, что и значение индекса,
поэтому оборот всегда сопоставлен конкретной дате конкретного индекса. Объём
показывается только там, где индекс описывает торгуемый рынок с доступным
дневным оборотом (см. `indices/volumes.py`):

| Рынок | Индексы | Подпись в интерфейсе |
|---|---|---|
| Спот BTCUSDT (Binance) | `fng`, `bvol`, `nupl`, `mvrv`, `ssr` | BTC spot volume |
| Бессрочный BTCUSDT (Binance fapi) | `funding` | BTC perp volume |
| — | `altseason`, `vix`, `spx`, `nikkei`, `cnnfng`, `brent`, `us10y`, `dxy` | столбиков нет |

У ставки финансирования оборот берётся именно с фьючерсов: сама ставка
рассчитывается по этому контракту, и его оборот примерно на порядок больше
спотового. Индексы без объёма отдают график без полосы столбиков — она не
рисуется пустой, высота отдаётся линии индекса.

**Синхронизация.**

```bash
python -m indices.sync            # все индексы
python -m indices.sync vix spx    # только указанные
python -m indices.sync --report    # состояние БД без загрузки
```

Каждый индекс синхронизируется независимо: падение одного источника не отменяет
остальные, ошибка пишется в `index_meta.last_error` и видна в
`GET /api/indexes/status`. На VPS запускается systemd-таймером через
`deploy/fng-sync.sh` (второй шаг после Fear & Greed), либо вручную через
`GET /jobs/indexes-sync?token=$CRON_TOKEN`.

**Telegram-карточки (черновик).** Пакет `telegram_feed/` рисует PNG за 14 дней
в стиле терминала (Pillow, без Plotly) и короткую подпись ≤250 символов.
Примеры: `telegram_feed/examples/FEED.md`.

```bash
python -m telegram_feed --from-api --out telegram_feed/out
python -m telegram_feed.publish --dry-run   # после синка; в cron — без --dry-run
```

**Описания индексов** (что показывает, как считается, что говорит о рынке, как
читать изменения) лежат в `indices/registry.py` — единственном источнике правды по
метаданным. Оттуда они попадают и в БД, и в блок «About this index» на странице
`/i/<id>`.

---

## 2. Дневник разработки

Кратко, по коммитам (от старых к новым).

**2026-05-11 — Старт.** Статичный сайт-визитка (RU/EN, эффект печатной машинки, стили). Привязка домена `zatinatscky.com` через CNAME.

**2026-05-13 — Бэкенд и данные.** Деплой Flask/Dash на Render: слой данных на Postgres и cron-скрипты. Перешли на psycopg v3 (готовые колёса, без `pg_config`), облегчили cron-сборку. Layout Dash пересобирается на каждый заход — свежие данные и стабильный UI.

**2026-05-26 — Продукт IVAN.** Полноценный дашборд: данные BTC с Binance, фильтр по датам, доки по субдомену. Корень субдомена редиректит на дашборд (`DASH_ROOT_HOST`). Добавлена welcome-страница IVAN, Fear & Greed переехал на `/fng/`. Заголовок на экране загрузки + фикс welcome при пустом `DASH_ROOT_HOST`.

**2026-06-09 — Свой сервер.** Уход с Render на VPS: Docker Compose, Caddy с авто-HTTPS, systemd-таймер синхронизации и бэкапы. Подчистили случайно закоммиченный файл.

**2026-06-11 — SEO.** Технический SEO для `/fng/`: мета-теги, Open Graph, JSON-LD, `robots.txt`, `sitemap.xml`.

**2026-06-14 — Апекс на VPS.** Логотип IVAN со ссылкой на главную на странице `/fng/`. Апекс `zatinatscky.com` переехал с GitHub Pages на тот же VPS: host-aware `robots`/`sitemap`, маршрут `/en/`, self-hosted Inter; Caddy обслуживает оба домена.

**2026-08-03 — Реальные данные в терминале.** Мок-генератор `mock-data.js` удалён, значения индексов приходят из БД через `/api/indexes`. Новый слой `indices/`: реестр метаданных, схема `index_meta`/`index_observation`, фетчеры бесплатных публичных API и ежедневная синхронизация с изоляцией ошибок по индексу. Состав сокращён с 22 до 14 индексов — остались только те, что обновляются раз в сутки без костылей. На страницу индекса добавлен разбор из четырёх частей: что показывает, как считается, что говорит о рынке и как читать изменения.
