#!/usr/bin/env bash
# Бэкап PostgreSQL в сжатый дамп. Хранит последние 14 копий.
# Запуск вручную или по cron/таймеру (пример в DEPLOY_VPS.md).
set -euo pipefail

REPO_DIR="/home/ivan/zatinatscky"
BACKUP_DIR="/home/ivan/backups"
KEEP=14

cd "$REPO_DIR"

# Достаём имя пользователя/БД из .env.
set -a
# shellcheck disable=SC1091
source .env
set +a

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/${POSTGRES_DB}-${STAMP}.sql.gz"

# pg_dump внутри контейнера db → сжатый файл на хосте.
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$OUT"
echo "Backup written: $OUT"

# Удаляем всё, кроме последних $KEEP копий.
ls -1t "$BACKUP_DIR/${POSTGRES_DB}-"*.sql.gz 2>/dev/null | tail -n "+$((KEEP + 1))" | xargs -r rm --
