# Деплой rhyme_analyzer (каталог hiphop/ монорепозитория)

Стек: **общий Docker Compose в корне** `~/zatinatscky` → PostgreSQL + FastAPI → Caddy (HTTPS).

| | |
|---|---|
| Сервер | `13.140.157.222` |
| Домен | **`https://hiphop.zatinatscky.com`** |
| Код | `/home/ivan/zatinatscky/hiphop` |
| Compose | `/home/ivan/zatinatscky/docker-compose.yml` |

Прод поднимается командой `docker compose up -d --build` **из корня** репозитория (сервисы `hiphop-db` и `hiphop-web`). Старый отдельный каталог `~/hiphop` больше не нужен.

---

## 1. DNS (Cloudflare)

В зоне `zatinatscky.com` → DNS добавить:

| Тип | Имя | Значение | Proxy |
|-----|-----|----------|-------|
| `A` | `hiphop` | `13.140.157.222` | **DNS only** (серая туча) на время выпуска TLS |

Проверка:

```bash
dig hiphop.zatinatscky.com A +short
# → 13.140.157.222
```

---

## 2. Залить код на сервер

На Mac (если репозиторий ещё не на GitHub — rsync):

```bash
rsync -avz --exclude .venv --exclude output --exclude data --exclude .git \
  ~/Documents/hiphop/ ivan@13.140.157.222:~/hiphop/
```

Или через git на сервере:

```bash
ssh ivan@13.140.157.222
cd ~
git clone <URL-репозитория-hiphop> hiphop
cd hiphop
```

---

## 3. Секреты `.env`

```bash
cd ~/hiphop
cp .env.example .env
nano .env
```

Заполнить:

- `POSTGRES_PASSWORD` — `openssl rand -hex 24`
- `OPENAI_API_KEY` и/или `DEEPSEEK_API_KEY`
- `IVAN_NETWORK=zatinatscky_default` (если IVAN в каталоге `~/zatinatscky`)

Проверить имя сети IVAN:

```bash
docker network ls | grep zatinatscky
# zatinatscky_default
```

---

## 4. Обновить Caddy IVAN (если ещё не в main)

В `~/zatinatscky/Caddyfile` должен быть блок (уже в репозитории):

```
hiphop.zatinatscky.com {
    reverse_proxy hiphop-web:8000
    ...
}
```

Перезагрузить Caddy после изменений:

```bash
cd ~/zatinatscky
docker compose restart caddy
docker compose logs -f caddy   # выпуск TLS для hiphop.*
```

---

## 5. Поднять контейнеры hiphop

```bash
cd ~/hiphop
docker compose -f docker-compose.vps.yml up -d --build
```

Проверка:

```bash
docker compose -f docker-compose.vps.yml ps
# hiphop-web — healthy, hiphop-db — healthy

docker compose -f docker-compose.vps.yml exec -T web \
  python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read())"
# b'{"status":"ok","service":"rhyme-analyzer","db":true}'
```

Изнутри сети IVAN (Caddy видит сервис):

```bash
docker compose -f ~/zatinatscky/docker-compose.yml exec -T caddy \
  wget -qO- http://hiphop-web:8000/health
```

В браузере:

- **https://hiphop.zatinatscky.com/** — форма разбора рифм
- **https://hiphop.zatinatscky.com/health** — `{"status":"ok",...}`

---

## 6. Импорт старого журнала (опционально)

Если на Mac были разборы в `output/journal/`:

```bash
# на Mac — скопировать output на сервер
rsync -avz ~/Documents/hiphop/output/ ivan@13.140.157.222:~/hiphop/output/

# на сервере
cd ~/hiphop
docker compose -f docker-compose.vps.yml exec web \
  python -m rhyme_analyzer.db.migrate_journal
```

---

## 7. Бэкапы БД

```bash
chmod +x deploy/backup.sh
./deploy/backup.sh
```

Cron (ежедневно в 05:00):

```bash
crontab -e
# добавить:
0 5 * * * /home/ivan/hiphop/deploy/backup.sh >> /home/ivan/backups/hiphop/backup.log 2>&1
```

---

## 8. Обновление после правок кода

```bash
cd ~/hiphop
git pull   # или rsync с Mac
docker compose -f docker-compose.vps.yml up -d --build
docker compose -f docker-compose.vps.yml logs -f web
```

---

## Частые команды

| Действие | Команда |
|----------|---------|
| Статус | `docker compose -f docker-compose.vps.yml ps` |
| Логи web | `docker compose -f docker-compose.vps.yml logs -f web` |
| Перезапуск | `docker compose -f docker-compose.vps.yml restart web` |
| БД psql | `docker compose -f docker-compose.vps.yml exec db psql -U hiphop -d hiphop` |
| Остановить | `docker compose -f docker-compose.vps.yml down` |

---

## Возможные проблемы

| Симптом | Решение |
|---------|---------|
| `502` на hiphop.* | `docker compose -f docker-compose.vps.yml ps` — web healthy? Caddy видит сеть? |
| Caddy: `dial hiphop-web: connection refused` | Контейнер не в сети `zatinatscky_default`: проверить `IVAN_NETWORK` в `.env` |
| Нет моделей в селекте | Ключи в `.env`, пересобрать: `up -d --build` |
| Анализ обрывается | LLM timeout — в Dockerfile gunicorn `--timeout 600`; проверить логи web |
| TLS не выпускается | DNS `hiphop` → IP сервера, серая туча Cloudflare |

---

## Чеклист

- [ ] DNS `hiphop` → `13.140.157.222`
- [ ] Репозиторий в `/home/ivan/hiphop`, `.env` заполнен
- [ ] IVAN Caddy содержит блок `hiphop.zatinatscky.com`
- [ ] `docker compose -f docker-compose.vps.yml up -d --build` — оба контейнера healthy
- [ ] https://hiphop.zatinatscky.com/ открывается
- [ ] Тестовый разбор рифм проходит до конца
