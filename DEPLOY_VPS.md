# Деплой IVAN на свой VPS (Contabo, Ubuntu 24.04)

Стек: **Docker Compose** → PostgreSQL + web (Flask/Dash под gunicorn) + **Caddy** (авто-HTTPS).
Ежедневная синхронизация — **systemd timer**. Бэкапы — `pg_dump`.

- Сервер: `13.140.157.222`
- Домен: `ivan.zatinatscky.com`
- Каталог репозитория на сервере: `/home/ivan/zatinatscky`

> Сервис на Render (`render.yaml`) можно не трогать, пока не убедитесь, что VPS работает.

---

## 0. Перед началом (один раз, уже сделано)

На сервере должны быть: пользователь `ivan` (в группе `sudo` и `docker`), вход по SSH-ключу,
открытые порты (`ufw`: 22/80/443), установленный Docker. Проверка:

```bash
ssh ivan@13.140.157.222
docker run --rm hello-world
```

---

## 1. Залить репозиторий на сервер

На сервере под пользователем `ivan`:

```bash
cd ~
git clone https://github.com/zatinatscky/zatinatscky.com.git zatinatscky
cd zatinatscky
```

(Дальше все команды выполняются из `/home/ivan/zatinatscky`.)

---

## 2. Создать файл секретов `.env`

```bash
cp .env.example .env
nano .env
```

Заполнить:

- `POSTGRES_PASSWORD` — длинный пароль: `openssl rand -hex 24`
- `CRON_TOKEN` — длинный токен: `openssl rand -hex 32`
- `SECRET_KEY` — длинный секрет для cookie-сессий: `openssl rand -hex 32`
- `PUBLIC_BASE_URL=https://ivan.zatinatscky.com`
- `DASH_ROOT_HOST=ivan.zatinatscky.com` (уже стоит)
- (опционально) Google / Telegram — см. блок Auth в `.env.example`. Без них Sign-in в UI скрыт.

Сохранить (Ctrl+O, Enter, Ctrl+X). Файл `.env` в git не попадает.

---

## 3. Поднять контейнеры

```bash
docker compose up -d --build
```

Что произойдёт:

1. Соберётся образ web, поднимется PostgreSQL (том `pgdata`).
2. При старте web выполнит первичную загрузку (история Fear & Greed + BTC) — **несколько минут**.
3. Caddy запросит TLS-сертификат у Let's Encrypt (нужен шаг 4 — DNS).

Логи в реальном времени:

```bash
docker compose logs -f web      # прогресс загрузки данных
docker compose logs -f caddy    # выпуск сертификата
```

Проверка живости изнутри (до переключения DNS):

```bash
docker compose exec -T web python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8050/health').read())"
# ожидается: b'{"status":"ok"}'
```

---

## 4. Переключить DNS на новый сервер (Cloudflare)

В зоне `zatinatscky.com` → DNS:

1. Найти запись **`ivan`** (сейчас `CNAME` → `*.onrender.com`).
2. Заменить на **A-запись**:

| Тип | Имя | Значение | Proxy |
|-----|-----|----------|-------|
| `A` | `ivan` | `13.140.157.222` | **DNS only** (серая туча) на время выпуска TLS |

3. Удалить старый `CNAME` на Render.

> Серая туча обязательна на старте: Caddy должен достучаться до сервера по 80/443 для выпуска
> сертификата. После успешного HTTPS можно включить оранжевую тучу (proxy), если нужен CDN/WAF.

Проверка распространения:

```bash
dig ivan.zatinatscky.com A +short      # должно показать 13.140.157.222
```

Когда DNS обновился, Caddy сам выпустит сертификат. Проверьте в браузере:

- `https://ivan.zatinatscky.com/` — welcome IVAN
- `https://ivan.zatinatscky.com/fng/` — дашборд
- `https://ivan.zatinatscky.com/health` — `{"status":"ok"}`

---

## 5. Ежедневная синхронизация (systemd timer)

Скрипт `deploy/fng-sync.sh` делает три шага: дёргает `/jobs/fng-sync` внутри
web-контейнера (Fear & Greed + цены BTC), запускает `python -m indices.sync`
(ряды индексов терминала) и `python -m telegram_feed.publish` (карточки в
Telegram-канал; без `TELEGRAM_CHANNEL_ID` шаг тихо пропускается).

Бит запуска у скриптов проставлен в самом git (`100755`), поэтому `chmod +x`
здесь делать **не нужно**: локальное изменение прав git считает модификацией
файла, и она блокирует последующие `git pull`, которые этот файл затрагивают.

На всякий случай стоит один раз сказать клону на сервере не обращать внимания
на права — тогда любые будущие `chmod` не превратятся в мнимые правки:

```bash
git config core.fileMode false
```

```bash
sudo cp deploy/fng-sync.service /etc/systemd/system/
sudo cp deploy/fng-sync.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fng-sync.timer
```

Проверка:

```bash
systemctl list-timers fng-sync.timer      # когда следующий запуск
sudo systemctl start fng-sync.service     # разовый прогон сейчас
journalctl -u fng-sync.service -n 50      # лог последнего запуска
```

---

## 6. Бэкапы БД

Разовый бэкап:

```bash
./deploy/backup.sh
ls -lh ~/backups
```

Ежедневный бэкап в 04:30 через cron пользователя:

```bash
crontab -e
# добавить строку:
30 4 * * * /home/ivan/zatinatscky/deploy/backup.sh >> /home/ivan/backups/backup.log 2>&1
```

> Желательно копировать дампы и **вне сервера** (на случай проблем у хостера): rclone в облако/S3
> или периодически `scp` к себе на Mac.

Восстановление из дампа (пример):

```bash
gunzip -c ~/backups/zatinatscky-YYYYMMDD-HHMMSS.sql.gz | \
  docker compose exec -T db psql -U ivan -d zatinatscky
```

---

## 7. Обновление кода (новый деплой)

```bash
cd ~/zatinatscky
git pull
docker compose up -d --build
docker compose logs -f web
```

---

## Перенос апекса zatinatscky.com на сервер (с GitHub Pages)

Тот же Flask отдаёт визитку консалтинга по Host (контент не меняется, дизайн сохранён).
Caddy уже настроен на оба домена (см. `Caddyfile`).

1. Задеплоить актуальный код: `git pull && docker compose up -d --build`.
2. В Cloudflare → DNS зоны `zatinatscky.com`:
   - **Удалить** 4 A-записи апекса на GitHub Pages (`185.199.108–111.153`).
   - **Добавить** одну A-запись: `@` → `13.140.157.222`, **DNS only** (серая туча) на время выпуска TLS.
   - Запись **TXT** `google-site-verification=...` — оставить.
   - `www`: либо удалить, либо `CNAME www → zatinatscky.com` (и раскомментировать www-блок в `Caddyfile`).
3. В GitHub → репозиторий → **Settings → Pages**: убрать кастомный домен (чтобы Pages не «держал» домен).
4. Дождаться, пока Caddy выпустит сертификат: `docker compose logs -f caddy`.
5. Проверить:

```bash
dig zatinatscky.com A +short        # 13.140.157.222
curl -sI https://zatinatscky.com/   # 200, x-render? нет — gunicorn/caddy
```

> Файл `CNAME` в репозитории нужен только GitHub Pages; на работу VPS он не влияет.

---

## hiphop (rhyme_analyzer) в том же репозитории

Код лежит в **`~/zatinatscky/hiphop`**. Caddy проксирует **`hiphop.zatinatscky.com`** → `hiphop-web:8000` (тот же `docker compose` в корне).

Первый переезд со старой папки `~/hiphop`:

1. В корневой `~/zatinatscky/.env` добавить (пароль взять из старого `~/hiphop/.env`):
   - `HIPHOP_POSTGRES_PASSWORD=...`
   - `OPENAI_API_KEY=...` и/или `DEEPSEEK_API_KEY=...`
2. Остановить старый стек, **тома не удалять**:

```bash
cd ~/hiphop
docker compose -f docker-compose.vps.yml down
# том hiphop_hiphop_pgdata должен остаться: docker volume ls | grep hiphop
```

3. Поднять всё из монорепозитория:

```bash
cd ~/zatinatscky
git pull
docker compose up -d --build
```

Проверка: `https://hiphop.zatinatscky.com/health` → `{"status":"ok",...}`.

## Частые команды

| Действие | Команда |
|----------|---------|
| Статус контейнеров | `docker compose ps` |
| Логи web / caddy / db | `docker compose logs -f web` |
| Перезапустить web | `docker compose restart web` |
| Остановить всё | `docker compose down` |
| Поднять всё | `docker compose up -d` |
| Зайти в БД | `docker compose exec db psql -U ivan -d zatinatscky` |
| Ручной синк (всё) | `sudo systemctl start fng-sync.service` |
| Синк только индексов | `docker compose exec -T web python -m indices.sync` |
| Один индекс | `docker compose exec -T web python -m indices.sync vix` |
| Состояние индексов | `docker compose exec -T web python -m indices.sync --report` |
| Telegram dry-run | `docker compose exec -T web python -m telegram_feed.publish --dry-run` |
| Telegram пост сейчас | `docker compose exec -T web python -m telegram_feed.publish` |

---

## Sign-in (Google / Telegram)

Пока переменные пустые, кнопки входа в UI скрыты — терминал работает как раньше (watchlist в localStorage).

**Google**

1. [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → OAuth 2.0 Client ID (Web).
2. Authorized redirect URI: `https://ivan.zatinatscky.com/api/auth/google/callback`
3. В `.env`: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, затем `docker compose up -d` (пересоздаст `web` с новыми env).

**Telegram (логин + 14 каналов фида)**

1. Создать бота у `@BotFather`, взять token и username.
2. `/setdomain` → `ivan.zatinatscky.com` (для Login Widget).
3. Создать **14 каналов** (по одному на индекс) и добавить бота **админом** в каждый.
4. В `.env`:
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` (без `@`)
   - `TELEGRAM_CHANNEL_FNG=@…`, `TELEGRAM_CHANNEL_VIX=@…`, … (все 14 — см. `.env.example`)
   - опционально `TELEGRAM_SUMMARY_CHANNEL_ID` для дневного дайджеста
   - `TELEGRAM_FEED_ENABLED=true`
5. `docker compose up -d` (подхватит env).

Проверка постинга:

```bash
docker compose exec -T web python -m telegram_feed.publish --list-channels
docker compose exec -T web python -m telegram_feed.publish --dry-run
docker compose exec -T web python -m telegram_feed.publish
```

Обязательно также задать `SECRET_KEY` и `PUBLIC_BASE_URL` (см. `.env.example`).

---

## Возможные проблемы

| Симптом | Что проверить |
|---------|----------------|
| Caddy не выпускает сертификат | DNS `ivan` → IP сервера (A, серая туча); порты 80/443 открыты в `ufw`; `docker compose logs caddy` |
| `502` в браузере | web ещё грузит данные на старте — `docker compose logs -f web`; healthcheck `docker compose ps` |
| Пустой `/fng/` | БД пустая — `sudo systemctl start fng-sync.service`, затем обновить страницу |
| Терминал пишет «Index data unavailable» | Таблицы индексов пустые — `docker compose exec -T web python -m indices.sync`. Значения намеренно не подставляются из генератора, поэтому до первой синхронизации страница честно показывает ошибку |
| `ModuleNotFoundError: indices` | `git pull` не прошёл или образ не пересобран — `docker compose up -d --build`. Код IVAN теперь в `ivan/` |
| `git pull` → `Your local changes would be overwritten` | Обычно это следы старого `chmod +x`: git считает смену прав модификацией файла. Лечится один раз — `git config core.fileMode false && git checkout -- deploy/`, дальше `git pull`. Сбрасывать файлы по одному не надо: `chmod` делался сразу для `fng-sync.sh` и `backup.sh`, и пул упрётся во второй файл. Проверить, что других правок нет: `git status --porcelain` |
| `web` не стартует | `.env` заполнен? `docker compose config` без ошибок? |
| Долгий первый старт | Нормально: грузится история F&G + BTC (несколько минут) |
| Синк индексов идёт долго | Нормально: полный проход ~4 минуты (пагинация Binance, чанки Deribit, троттлинг bitcoin-data). В `fng-sync.service` под это поднят `TimeoutStartSec=1800` |

---

## Чеклист

- [ ] Репозиторий склонирован в `/home/ivan/zatinatscky`
- [ ] `.env` заполнен (пароль БД, CRON_TOKEN, SECRET_KEY; опционально Google/Telegram)
- [ ] `docker compose up -d --build` — контейнеры `Up`/`healthy`
- [ ] DNS `ivan` → `13.140.157.222` (A), старый CNAME удалён
- [ ] `https://ivan.zatinatscky.com/` и `/fng/` открываются по HTTPS
- [ ] `fng-sync.timer` включён (`systemctl list-timers`)
- [ ] Индексы прогружены (`docker compose exec -T web python -m indices.sync --report` — все строки `OK`)
- [ ] Бэкап работает (`./deploy/backup.sh`), добавлен в cron
