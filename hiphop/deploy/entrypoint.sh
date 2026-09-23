#!/usr/bin/env bash
# Старт web-контейнера: проверка импорта → gunicorn.
set -euo pipefail

echo "[entrypoint] проверка импорта приложения…"
python -c "from rhyme_analyzer.api.app import app; print('[entrypoint] import ok')"

echo "[entrypoint] gunicorn на :8000"
exec gunicorn rhyme_analyzer.api.app:app \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-1}" \
  --timeout 600 \
  --graceful-timeout 30 \
  --keep-alive 5 \
  --access-logfile - \
  --error-logfile -
