"""Оболочка HTML для «открыть в новой вкладке» из веб-UI.

Вместо статической разметки из html_gen.py подключаем тот же report_renderer.js,
что и в превью: IPA-переключатель, пины на чипах и hover работают одинаково.
"""

from __future__ import annotations

import html
import json
from typing import Any


def _safe_json_in_script(data: dict[str, Any]) -> str:
    """JSON для вставки в <script type=\"application/json\"> без XSS и поломки тега."""
    raw = json.dumps(data, ensure_ascii=False)
    # Закрывающий </script> внутри JSON сломает страницу.
    return raw.replace("</", "<\\/")


def generate_export_shell(report: dict[str, Any]) -> str:
    """Самодостаточная страница: CSS + JSON + клиентский рендер отчёта."""
    title = html.escape(str(report.get("song") or "Отчёт"), quote=True)
    payload = _safe_json_in_script(report)

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="rhyme_analyzer">
<title>{title} — Rhyme Analyzer</title>
<link rel="stylesheet" href="/static/report.css">
<style>
  /* Те же переменные, что в основном UI — report.css на них опирается */
  :root {{
    --bg: #0d0f14;
    --surface-2: #1c2230;
    --border: #2a3344;
    --fg: #ececec;
    --fg2: #b6b6bb;
    --fg3: #8a8a90;
    --accent: #b692f6;
  }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--fg);
    padding: 1rem 1.25rem 2rem;
  }}
  #report-root {{
    max-width: 940px;
    margin: 0 auto;
  }}
</style>
</head>
<body>
<div id="report-root" aria-busy="true">Загрузка отчёта…</div>
<script id="report-data" type="application/json">{payload}</script>
<script type="module">
  import {{ renderReport }} from "/static/report_renderer.js";

  const root = document.getElementById("report-root");
  const raw = document.getElementById("report-data").textContent;
  const report = JSON.parse(raw);
  renderReport(root, report);
  document.title = (report.song || "Отчёт") + " — Rhyme Analyzer";
</script>
</body>
</html>
"""
