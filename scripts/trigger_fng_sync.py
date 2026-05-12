#!/usr/bin/env python3
"""
Триггер синхронизации через HTTP-эндпоинт веб-сервиса.

Почему так:
- Render Cron запускается отдельным сервисом;
- безопаснее дергать update внутри web-процесса, где подключен тот же persistent disk.
"""

from __future__ import annotations

import os
import sys

import requests


def main() -> None:
    site_url = os.getenv("SITE_BASE_URL", "").rstrip("/")
    token = os.getenv("CRON_TOKEN", "")

    if not site_url:
        print("SITE_BASE_URL is required", file=sys.stderr)
        raise SystemExit(2)
    if not token:
        print("CRON_TOKEN is required", file=sys.stderr)
        raise SystemExit(2)

    url = f"{site_url}/jobs/fng-sync"
    response = requests.get(url, params={"token": token}, timeout=60)
    response.raise_for_status()
    print(response.text)


if __name__ == "__main__":
    main()
