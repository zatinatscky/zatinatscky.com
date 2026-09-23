"""Прогресс анализа для веб-интерфейса: технический лог + подсказка пользователю."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from typing import Any

# Колбэк получает dict-событие для SSE.
ProgressCallback = Callable[[dict[str, Any]], None]


class ProgressReporter:
    """Шлёт события прогресса в UI и дублирует лог в терминал."""

    def __init__(self, callback: ProgressCallback | None = None) -> None:
        self._cb = callback
        self._lock = threading.Lock()

    def emit(
        self,
        *,
        stage: str,
        percent: int,
        log: str,
        hint: str,
    ) -> None:
        """Одно событие: stage, процент, сырой лог и пояснение для пользователя."""
        with self._lock:
            print(log)
            if self._cb:
                self._cb(
                    {
                        "type": "progress",
                        "stage": stage,
                        "percent": min(100, max(0, percent)),
                        "log": log,
                        "hint": hint,
                    }
                )

    def log_llm(self, line: str) -> None:
        """Разбирает строку вида [llm] … и шлёт с человекочитаемым hint."""
        hint = humanize_llm_log(line)
        stage = "llm"
        percent = getattr(self, "_last_percent", 20)
        self.emit(stage=stage, percent=percent, log=line, hint=hint)


# --- Пояснения для типичных строк терминала ---

_LLM_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^\[llm\] ключ:"), "Подключение к OpenAI прошло успешно — ключ принят."),
    (re.compile(r"^\[llm\] модель: (.+?) · блоков: (\d+)"), "Будем анализировать {1} секций текста — это займёт несколько минут."),
    (re.compile(r"^\[llm\] параллельно: до (\d+)"), "Несколько секций обрабатываются одновременно (до {0} запросов к API) — быстрее, чем строго по очереди."),
    (re.compile(r"^\[llm\] блок (\d+)/(\d+): «(.+?)»"), "Запущен разбор секции «{2}» ({0} из {1}). Обычно 30–90 секунд на блок."),
    (re.compile(r"^\[llm\]\s+блок (\d+)/(\d+) готов → (\d+)"), "Секция {0} из {1} готова — найдено {2} рифменных цепочек."),
    (re.compile(r"^\[llm\] после слияния: (\d+)"), "Объединили результаты всех секций: всего {0} цепочек в песне."),
    (re.compile(r"^\[llm\]\s+валидация: (\d+) ошибок, повтор"), "Ответ модели уточняем автоматически — иногда первая версия не совпадает с текстом дословно."),
    (re.compile(r"^\[llm\]\s+• (.+)"), "Деталь проверки: {0}"),
    (re.compile(r"валидация не пройдена"), "Модель не смогла согласовать рифмы с текстом после нескольких попыток."),
]


def humanize_llm_log(line: str) -> str:
    """Переводит технический [llm]-лог в понятное пользователю пояснение."""
    for pattern, template in _LLM_HINTS:
        m = pattern.search(line)
        if m:
            groups = m.groups()
            try:
                return template.format(*groups)
            except (IndexError, KeyError):
                return template
    if line.startswith("[llm]"):
        return "Идёт анализ рифм через нейросеть…"
    return line


def humanize_pipeline_stage(stage: str) -> str:
    """Подсказки для этапов пайплайна до/после LLM."""
    return {
        "prepare": "Подготавливаем текст: числа и латиница превращаются в произношение.",
        "phonetics": "Считаем IPA-транскрипцию (espeak) — она нужна модели для точных рифм.",
        "merge": "Сливаем фонетические эвристики с разметкой модели.",
        "annotate": "Раскрашиваем текст по найденным цепочкам рифм.",
        "render": "Собираем HTML-отчёт с подсветкой и таблицей цепочек.",
        "done": "Готово! Отчёт можно открыть справа.",
    }.get(stage, "Обработка…")
