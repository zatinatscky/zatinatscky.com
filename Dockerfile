# Образ веб-сервиса IVAN (Flask + Dash под gunicorn).
# psycopg[binary] ставится готовым колесом (libpq внутри) — системные пакеты не нужны.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Сначала зависимости — слой кешируется, пока не меняется requirements.txt.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Затем код приложения.
COPY . .

EXPOSE 8050

# Healthcheck бьёт в /health. start-period большой: при старте идёт full_refresh
# (история Fear & Greed + BTC), это может занять несколько минут.
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8050/health').status==200 else 1)"

# Тот же запуск, что был на Render (gunicorn app:server).
CMD ["gunicorn", "app:server", "--bind", "0.0.0.0:8050", "--workers", "2", "--threads", "4", "--timeout", "120"]
