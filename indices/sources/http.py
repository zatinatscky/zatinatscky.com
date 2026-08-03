"""
Общий HTTP-клиент для всех источников.

Зачем свой слой вместо голого requests.get:
- часть источников (Yahoo, CNN) отдаёт данные только «браузерным» User-Agent,
  без него прилетает 403 или «I'm a teapot. You're a bot.»;
- бесплатные API периодически отвечают 429/5xx, поэтому нужен retry с backoff;
- один Session на процесс переиспользует TCP-соединения: синхронизация делает
  сотни запросов к Binance, на каждом сэкономленный handshake заметен.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter

_log = logging.getLogger(__name__)

# UA реального Chrome: Yahoo и CNN без него отвечают 403 / «You're a bot».
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Нейтральный UA для источников с обратным поведением: FRED на браузерном UA
# подвешивает соединение до таймаута, а на «утилитном» отдаёт CSV сразу.
TOOL_UA = "zatinatscky-ivan/1.0 (+https://ivan.zatinatscky.com)"

DEFAULT_TIMEOUT = 45
# Коды, которые имеет смысл повторить: троттлинг и временные сбои шлюзов.
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

_session: requests.Session | None = None


def session() -> requests.Session:
    """Ленивый общий Session с увеличенным пулом соединений."""
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({"User-Agent": BROWSER_UA, "Accept": "application/json, text/csv, */*"})
        adapter = HTTPAdapter(pool_connections=8, pool_maxsize=16)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _session = s
    return _session


def get(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    attempts: int = 3,
    backoff: float = 1.5,
) -> requests.Response:
    """
    GET с повторами по 429/5xx и сетевым ошибкам.

    Пауза растёт как backoff ** n, чтобы не добивать источник, который уже
    ответил 429. Последняя неудача поднимается наружу — вызывающий фетчер
    падает, а sync.py ловит ошибку и помечает только этот индекс.
    """
    last_exc: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            resp = session().get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code in RETRY_STATUS and attempt < attempts:
                wait = backoff**attempt
                _log.warning(
                    "%s -> HTTP %s, повтор через %.1fs (попытка %s/%s)",
                    url,
                    resp.status_code,
                    wait,
                    attempt,
                    attempts,
                )
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            wait = backoff**attempt
            _log.warning(
                "%s -> %s, повтор через %.1fs (попытка %s/%s)",
                url,
                exc.__class__.__name__,
                wait,
                attempt,
                attempts,
            )
            time.sleep(wait)

    raise RuntimeError(f"Не удалось получить {url}: {last_exc}") from last_exc


def get_json(url: str, **kwargs: Any) -> Any:
    """GET + разбор JSON."""
    return get(url, **kwargs).json()


def get_text(url: str, **kwargs: Any) -> str:
    """GET + текст (для CSV-эндпоинтов вроде FRED)."""
    return get(url, **kwargs).text


def get_bytes(url: str, **kwargs: Any) -> bytes:
    """GET + сырые байты (для xlsx NY Fed)."""
    return get(url, **kwargs).content
