#!/usr/bin/env bash
# Первичный деплoy rhyme_analyzer на VPS (запускать НА СЕРВЕРЕ под ivan).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

echo "[1/4] Проверка .env"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "  Создан .env — заполните POSTGRES_PASSWORD и API-ключи, затем запустите снова."
  exit 1
fi

if grep -q 'CHANGE_ME' .env 2>/dev/null; then
  echo "  В .env остались плейсхолдеры CHANGE_ME — отредактируйте файл."
  exit 1
fi

if ! grep -qE '^POSTGRES_PASSWORD=.+$' .env; then
  echo "  В .env нет POSTGRES_PASSWORD — добавьте (openssl rand -hex 24)."
  exit 1
fi
if grep -qE '^DATABASE_URL=' .env; then
  echo "  [warn] Удалите DATABASE_URL из .env — используйте только POSTGRES_USER/PASSWORD/DB."
  sed -i.bak '/^DATABASE_URL=/d' .env
fi
if ! grep -qE '^OPENAI_API_KEY=.+$' .env && ! grep -qE '^DEEPSEEK_API_KEY=.+$' .env; then
  echo "  В .env нужен OPENAI_API_KEY и/или DEEPSEEK_API_KEY."
  exit 1
fi
# Дополняем дефолты, если пользователь не задал явно.
grep -qE '^POSTGRES_USER=' .env || echo 'POSTGRES_USER=hiphop' >> .env
grep -qE '^POSTGRES_DB=' .env || echo 'POSTGRES_DB=hiphop' >> .env
grep -qE '^IVAN_NETWORK=' .env || echo 'IVAN_NETWORK=zatinatscky_default' >> .env

echo "[2/4] Сеть IVAN (Caddy)"
IVAN_NET="$(grep -E '^IVAN_NETWORK=' .env | cut -d= -f2- || true)"
IVAN_NET="${IVAN_NET:-zatinatscky_default}"
if ! docker network inspect "$IVAN_NET" >/dev/null 2>&1; then
  echo "  Сеть $IVAN_NET не найдена. Сначала поднимите IVAN: cd ~/zatinatscky && docker compose up -d"
  exit 1
fi

echo "[3/4] Сборка и запуск контейнеров"
docker compose -f docker-compose.vps.yml up -d --build

echo "[4/4] Healthcheck (до 60 с)"
ok=0
for i in $(seq 1 12); do
  if docker compose -f docker-compose.vps.yml exec -T web \
    python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())" 2>/dev/null; then
    ok=1
    break
  fi
  echo "  ждём web… (${i}/12)"
  sleep 5
done

if [[ "$ok" -ne 1 ]]; then
  echo ""
  echo "[error] hiphop-web не отвечает на /health. Последние логи:"
  docker compose -f docker-compose.vps.yml logs web --tail 40
  exit 1
fi

echo ""
echo "[ok] Локально: http://127.0.0.1:8000/health (внутри контейнера)"
echo "[ok] Снаружи:  https://hiphop.zatinatscky.com/ (после DNS и reload Caddy IVAN)"
