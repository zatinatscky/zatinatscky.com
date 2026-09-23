#!/usr/bin/env bash
# Запуск rhyme_analyzer через venv проекта (не системный python3).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "[error] нет .venv — создайте окружение:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

exec "$ROOT/.venv/bin/python" -m rhyme_analyzer "$@"
