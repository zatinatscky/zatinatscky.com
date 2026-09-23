#!/usr/bin/env bash
# Бэкап PostgreSQL rhyme_analyzer. Хранит последние 14 дампов.
# Прод: один compose в корне монорепозитория, сервис hiphop-db.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/ivan/zatinatscky}"
BACKUP_DIR="${BACKUP_DIR:-/home/ivan/backups/hiphop}"
KEEP=14

cd "$REPO_DIR"

set -a
# shellcheck disable=SC1091
# Пароль БД hiphop в корневом .env называется HIPHOP_POSTGRES_PASSWORD.
source .env
set +a

POSTGRES_USER="${POSTGRES_USER_HIPHOP:-hiphop}"
POSTGRES_DB="${POSTGRES_DB_HIPHOP:-hiphop}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/${POSTGRES_DB}-${STAMP}.sql.gz"

docker compose exec -T hiphop-db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$OUT"
echo "Backup written: $OUT"

ls -1t "$BACKUP_DIR/${POSTGRES_DB}-"*.sql.gz 2>/dev/null | tail -n "+$((KEEP + 1))" | xargs -r rm --
