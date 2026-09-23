#!/usr/bin/env bash
# Локальный веб-сервер rhyme_analyzer (форма + API).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "[error] нет .venv — создайте окружение:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

echo "[ok] http://${HOST}:${PORT}"
exec "$ROOT/.venv/bin/python" -m uvicorn rhyme_analyzer.api.app:app --host "$HOST" --port "$PORT" --reload
