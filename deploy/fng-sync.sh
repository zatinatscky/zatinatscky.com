#!/usr/bin/env bash
# Ежедневная синхронизация Fear & Greed + BTC.
# Дёргает /jobs/fng-sync ВНУТРИ web-контейнера (localhost:8050), поэтому
# не зависит от домена/DNS/Caddy. CRON_TOKEN берётся из окружения контейнера.
set -euo pipefail

# Каталог репозитория на сервере (где лежит docker-compose.yml).
REPO_DIR="/home/ivan/zatinatscky"
cd "$REPO_DIR"

docker compose exec -T \
	-e SITE_BASE_URL="http://localhost:8050" \
	web python scripts/trigger_fng_sync.py
