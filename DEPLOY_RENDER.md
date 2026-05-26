# Deploy on Render (site + Dash + PostgreSQL + daily sync)

## Что в проекте

- `app.py` — Flask + Dash:
  - визитка: `/`, `/about.html`, …
  - дашборд: `/dash/`
- `fng_data.py` — загрузка Fear & Greed, upsert в **PostgreSQL** (`DATABASE_URL`); таблица **btc_usd_daily** (дневные свечи **Binance** Spot `GET /api/v3/klines`, пара BTCUSDT: close в USDT, объёмы base/quote — **без API-ключа**).
  - Локально **без** `DATABASE_URL` — fallback на SQLite в `./data/fear_greed.db`.
- `scripts/update_fng_data.py` — ручная синхронизация (использует тот же `get_engine()`).
- `scripts/trigger_fng_sync.py` — Render Cron дергает `/jobs/fng-sync` на web-сервисе.
- `render.yaml` — Postgres + web + cron.

## PostgreSQL-драйвер (локально и на Render)

В `requirements.txt` используется **psycopg v3** (`psycopg[binary]`): под **Python 3.14** на macOS нет колёс `psycopg2-binary`, сборка из исходников требует `pg_config`.

Строка `DATABASE_URL` от Render вида `postgresql://...` в коде превращается в **`postgresql+psycopg://...`** для SQLAlchemy.

## Локальный запуск

### Вариант A: только SQLite (без установки Postgres)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
unset DATABASE_URL   # чтобы использовался ./data/fear_greed.db
python scripts/update_fng_data.py
python app.py
```

### Вариант B: локальный PostgreSQL

```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/mydb"
pip install -r requirements.txt
python scripts/update_fng_data.py
python app.py
```

Проверка:

- сайт: `http://127.0.0.1:8050/`
- дашборд: `http://127.0.0.1:8050/dash/`

## Настройка на Render (Blueprint)

1. Подключите репозиторий и создайте **Blueprint** из `render.yaml`.
2. Замените в `render.yaml`:
   - `SITE_BASE_URL` — URL вашего web-сервиса (кастомный домен или `https://<service>.onrender.com`).
   - `CRON_TOKEN` — длинная случайная строка (**одинаково** в web и в cron).
3. Деплой: Render создаст **PostgreSQL** и проставит `DATABASE_URL` на web-сервисе.

## Ежедневное обновление

- Cron вызывает `scripts/trigger_fng_sync.py`.
- Скрипт делает `GET /jobs/fng-sync?token=...`.
- Web выполняет `full_refresh()` и пишет в **ту же** Postgres, куда смотрит дашборд.

## Регистрация пользователей позже

Таблица `fear_greed_index` живёт в той же БД — можно добавлять таблицы `users`, `sessions` и т.д. в том же Postgres или через миграции (Alembic).

---

## Субдомен `ivan.zatinatscky.com` (дашборд на Render)

Схема: **корень `zatinatscky.com`** может оставаться на GitHub Pages (визитка), **`ivan.zatinatscky.com`** — только на **web-сервис Render** (`zatinatscky-site`). Конфликта нет: это разные DNS-записи.

| URL | Куда ведёт |
|-----|------------|
| `https://zatinatscky.com/` | GitHub Pages (статика) |
| `https://ivan.zatinatscky.com/` | Render — редирект на `/dash/` (env `DASH_ROOT_HOST`) |
| `https://ivan.zatinatscky.com/dash/` | Render — Dash (Fear & Greed + BTC) |
| `https://ivan.zatinatscky.com/health` | Render — проверка живости |

### 1. Код в GitHub и деплой на Render

1. Закоммитьте и запушьте актуальный `main` в репозиторий `zatinatscky/zatinatscky.com`.
2. В [Render Dashboard](https://dashboard.render.com): **Blueprint** из `render.yaml` или уже созданный сервис **`zatinatscky-site`**.
3. Дождитесь успешного **Deploy** (логи без ошибок, `GET /health` → `{"status":"ok"}` на URL вида `https://zatinatscky-site-xxxx.onrender.com/health`).

### 2. Секреты и cron (обязательно)

В **Environment** web-сервиса и cron-сервиса:

| Переменная | Значение |
|------------|----------|
| `CRON_TOKEN` | Одна длинная случайная строка (**одинаковая** в web и cron) |
| `DASH_ROOT_HOST` | `ivan.zatinatscky.com` — на этом Host `/` открывает Dash, не `index.html` |
| `SITE_BASE_URL` (только cron) | `https://ivan.zatinatscky.com` — после того как домен заработает |
| `AUTO_SYNC_ON_START` | `true` (первая загрузка F&G + BTC в Postgres при старте) |

`DATABASE_URL` Render подставляет сам из `zatinatscky-postgres`.

Первый старт может занять **несколько минут** (Binance + история F&G). Смотрите **Logs** web-сервиса.

### 3. Кастомный домен в Render

1. Откройте сервис **`zatinatscky-site`** → **Settings** → **Custom Domains**.
2. **Add Custom Domain** → введите `ivan.zatinatscky.com`.
3. Render покажет, что добавить в DNS (обычно **CNAME**):

   | Тип | Имя (host) | Значение (target) |
   |-----|------------|-------------------|
   | `CNAME` | `ivan` | `zatinatscky-site.onrender.com` *(точное имя смотрите в UI Render)* |

4. Дождитесь статуса **Verified** и выпуска **TLS** (часто 5–30 минут, иногда до 48 ч).

### 4. DNS у регистратора / Cloudflare

Где управляется зона **`zatinatscky.com`** (Cloudflare, Namecheap, и т.д.):

1. Добавьте запись **CNAME**: host **`ivan`** → target из шага 3 (хост Render).
2. **Не** перенаправляйте весь `zatinatscky.com` на Render — только субдомен `ivan`.
3. **Cloudflare**: для записи `ivan` часто надёжнее режим **DNS only** (серая тучка), пока Render не выдаст сертификат. Потом можно включить прокси (оранжевая туча), если HTTPS стабилен.

Проверка с Mac:

```bash
dig ivan.zatinatscky.com CNAME +short
curl -sI https://ivan.zatinatscky.com/health
```

Ожидается CNAME на `*.onrender.com` и ответ `200` с JSON `ok`.

### 5. Обновить cron после домена

В cron **`fear-greed-daily-sync`** задайте:

```text
SITE_BASE_URL=https://ivan.zatinatscky.com
```

И тот же `CRON_TOKEN`, что у web. Иначе ночной job будет бить старый URL.

В `render.yaml` для удобства можно поменять дефолт `SITE_BASE_URL` на `https://ivan.zatinatscky.com` и сделать **Manual Deploy** / синхронизацию env из Blueprint.

### 6. Ссылка с визитки

На GitHub Pages (`index.html` / `en/index.html`) добавьте ссылку, например:

```html
<a href="https://ivan.zatinatscky.com/dash/">Fear & Greed dashboard</a>
```

### 7. Частые проблемы

| Симптом | Что проверить |
|---------|----------------|
| Домен не верифицируется | CNAME только для `ivan`, без лишней A-записи на тот же host |
| 502 / таймаут при старте | Логи: `full_refresh` на старте; увеличить `--timeout` в gunicorn (уже 120 с) |
| Пустой `/dash/` | Postgres пустая — дождаться sync или вызвать `GET /jobs/fng-sync?token=...` |
| Cron не обновляет данные | `SITE_BASE_URL` и `CRON_TOKEN` совпадают с web |

### Чеклист

- [ ] Web на Render: deploy OK, `/health` OK  
- [ ] Postgres подключена, в логах есть BTC sync  
- [ ] `ivan.zatinatscky.com` в Custom Domains → Verified  
- [ ] CNAME `ivan` → `*.onrender.com`  
- [ ] `https://ivan.zatinatscky.com/dash/` открывается  
- [ ] Cron: `SITE_BASE_URL=https://ivan.zatinatscky.com`, тот же `CRON_TOKEN`  
- [ ] Ссылка на дашборд на основном сайте (по желанию)
