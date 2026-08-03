#!/usr/bin/env bash
# Ежедневная синхронизация данных: Fear & Greed + цены BTC, затем все индексы
# терминала, затем постинг карточек в Telegram-канал.
#
# Первый шаг дёргает /jobs/fng-sync ВНУТРИ web-контейнера (localhost:8050),
# поэтому не зависит от домена/DNS/Caddy; CRON_TOKEN берётся из окружения
# контейнера.
#
# Второй шаг запускает indices.sync напрямую как модуль, а не через HTTP:
# полный проход по источникам занимает несколько минут, что дольше любого
# разумного таймаута запроса.
#
# Третий шаг — python -m telegram_feed.publish (нужны TELEGRAM_BOT_TOKEN и
# TELEGRAM_CHANNEL_ID в .env). Ошибка постинга не валит весь таймер.
set -euo pipefail

# Каталог репозитория на сервере (где лежит docker-compose.yml).
REPO_DIR="/home/ivan/zatinatscky"
cd "$REPO_DIR"

echo "[1/3] Fear & Greed + BTC…"
docker compose exec -T \
	-e SITE_BASE_URL="http://localhost:8050" \
	web python scripts/trigger_fng_sync.py

echo "[2/3] Индексы терминала…"
# Падение отдельного источника не должно ронять весь таймер: indices.sync
# возвращает 0, если обновился хотя бы один индекс, а ошибки складывает
# в index_meta.last_error (видно через /api/indexes/status).
docker compose exec -T web python -m indices.sync

echo "[3/3] Telegram channel feed…"
# Нет токена/канала → publish тихо выходит 0. Сбой API не должен ломать синк.
if ! docker compose exec -T web python -m telegram_feed.publish; then
	echo "Telegram feed failed (non-fatal)" >&2
fi
