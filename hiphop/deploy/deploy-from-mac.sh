#!/usr/bin/env bash
# С Mac: залить hiphop на VPS и перезапустить контейнеры.
# Использование: ./deploy/deploy-from-mac.sh
set -euo pipefail

VPS_USER="${VPS_USER:-ivan}"
VPS_HOST="${VPS_HOST:-13.140.157.222}"
VPS_DIR="${VPS_DIR:-/home/ivan/hiphop}"
IVAN_DIR="${IVAN_DIR:-/home/ivan/zatinatscky}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "[sync] $ROOT → ${VPS_USER}@${VPS_HOST}:${VPS_DIR}/"
rsync -avz --delete \
  --exclude .venv \
  --exclude output \
  --exclude data \
  --exclude .git \
  --exclude __pycache__ \
  "$ROOT/" "${VPS_USER}@${VPS_HOST}:${VPS_DIR}/"

echo "[remote] setup + restart"
ssh "${VPS_USER}@${VPS_HOST}" bash -s <<EOF
set -euo pipefail
cd ${VPS_DIR}
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Создан .env на сервере — заполните секреты и запустите скрипт снова."
  exit 1
fi
chmod +x deploy/setup-vps.sh deploy/backup.sh
./deploy/setup-vps.sh
cd ${IVAN_DIR}
git pull 2>/dev/null || true
docker compose restart caddy
echo "Готово: https://hiphop.zatinatscky.com/"
EOF
