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
- `DASH_ROOT_HOST=ivan.zatinatscky.com` (уже стоит)

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

Скрипт `deploy/fng-sync.sh` дёргает `/jobs/fng-sync` внутри web-контейнера.

```bash
chmod +x deploy/fng-sync.sh deploy/backup.sh

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

## Частые команды

| Действие | Команда |
|----------|---------|
| Статус контейнеров | `docker compose ps` |
| Логи web / caddy / db | `docker compose logs -f web` |
| Перезапустить web | `docker compose restart web` |
| Остановить всё | `docker compose down` |
| Поднять всё | `docker compose up -d` |
| Зайти в БД | `docker compose exec db psql -U ivan -d zatinatscky` |
| Ручной синк | `sudo systemctl start fng-sync.service` |

---

## Возможные проблемы

| Симптом | Что проверить |
|---------|----------------|
| Caddy не выпускает сертификат | DNS `ivan` → IP сервера (A, серая туча); порты 80/443 открыты в `ufw`; `docker compose logs caddy` |
| `502` в браузере | web ещё грузит данные на старте — `docker compose logs -f web`; healthcheck `docker compose ps` |
| Пустой `/fng/` | БД пустая — `sudo systemctl start fng-sync.service`, затем обновить страницу |
| `web` не стартует | `.env` заполнен? `docker compose config` без ошибок? |
| Долгий первый старт | Нормально: грузится история F&G + BTC (несколько минут) |

---

## Чеклист

- [ ] Репозиторий склонирован в `/home/ivan/zatinatscky`
- [ ] `.env` заполнен (пароль БД, CRON_TOKEN)
- [ ] `docker compose up -d --build` — контейнеры `Up`/`healthy`
- [ ] DNS `ivan` → `13.140.157.222` (A), старый CNAME удалён
- [ ] `https://ivan.zatinatscky.com/` и `/fng/` открываются по HTTPS
- [ ] `fng-sync.timer` включён (`systemctl list-timers`)
- [ ] Бэкап работает (`./deploy/backup.sh`), добавлен в cron
