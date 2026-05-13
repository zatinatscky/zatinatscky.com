# Deploy on Render (site + Dash + PostgreSQL + daily sync)

## Что в проекте

- `app.py` — Flask + Dash:
  - визитка: `/`, `/about.html`, …
  - дашборд: `/dash/`
- `fng_data.py` — загрузка Fear & Greed, upsert в **PostgreSQL** (`DATABASE_URL`).
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
