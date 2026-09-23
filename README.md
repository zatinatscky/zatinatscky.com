# zatinatscky.com — монорепозиторий IVAN + hiphop

Два продукта в одном git-репозитории и на одном VPS:

```
zatinatscky/
  ivan/     # визитка zatinatscky.com + IVAN Terminal + дашборды
  hiphop/   # rhyme_analyzer (hiphop.zatinatscky.com)
```

- **`zatinatscky.com`** — статичный сайт-визитка (консалтинг, RU/EN).
- **`ivan.zatinatscky.com`** — продукт **IVAN** (*Index Volatility Alerts & Notifications*): Index Terminal и дашборд Fear & Greed (`/fng/`).
- **`hiphop.zatinatscky.com`** — текстовый анализатор рифм.

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

- **Точка входа `ivan/app.py`** — Flask + Dash, host-aware роутинг (визитка vs IVAN), `robots.txt`/`sitemap.xml`. API: `/api/fng/latest`, `/api/indexes`, `/api/auth/*`, `/api/me*`.
- **Авторизация `ivan/auth/`** — Google OAuth + Telegram Login Widget, cookie-сессия, watchlist в Postgres.
- **Слой данных `ivan/fng_data.py`** — Postgres, история Fear & Greed и BTC.
- **Слой индексов `ivan/indices/`** — реальные данные терминала (см. раздел «Данные индексов» ниже).
- **Дашборд `ivan/fng_dash_layout.py`** — layout и колбэки Dash.
- **UI терминала `ivan/ivan/`** — Index Terminal: `home.html`, `/i/<id>`, `js/`, `css/terminal.css`.
- **Статичный сайт** — `ivan/index.html`, `about.html`, `articles.html`, `products.html`, `en/`, `css/`.
- **hiphop `hiphop/`** — FastAPI `rhyme_analyzer` + `web/` (форма разбора рифм).
- **Деплой** — корневые `docker-compose.yml`, `Caddyfile`, `deploy/` (синк IVAN и бэкап). Образы собираются из `ivan/` и `hiphop/`.
- **SEO** — мета-теги, Open Graph, JSON-LD, `robots.txt`, `sitemap.xml`.

### Запуск

```bash
# Локально — IVAN
cd ivan
pip install -r requirements.txt
python app.py            # http://localhost:8050

# Локально — hiphop
cd hiphop
pip install -r requirements.txt
./run_server.sh          # http://localhost:8000

# Продакшен (VPS), из корня репозитория
cp .env.example .env     # заполнить секреты IVAN и HIPHOP_*
docker compose up -d --build
```

Подробные инструкции: `DEPLOY_VPS.md` (VPS) и `ivan/DEPLOY_RENDER.md` (Render).

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
