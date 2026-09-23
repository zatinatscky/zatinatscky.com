"""Генерация самодостаточного HTML-файла из результатов разбора.

В отличие от canvas_gen (который эмитит React-файл для Cursor Canvas), здесь мы
собираем обычный .html: его можно открыть двойным кликом в любом браузере, без
Cursor и без интернета. Весь CSS встроен в <style>, внешних зависимостей нет.

Содержимое повторяет Canvas: текст с подсветкой цепочек + строка IPA под каждой
строкой + статистика + таблица цепочек + горизонтальный бар-чарт топ-цепочек.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import Block, Chain, Token
from .text_display import token_displays_for_output

# Соответствие имён палитры реальным HEX-цветам (подобрано под тёмную тему,
# те же 5 цветов, что и у Canvas SDK: purple/green/blue/orange/pink).
PALETTE = {
    "purple": "#b692f6",
    "green": "#5fd08a",
    "blue": "#6ba8f7",
    "orange": "#f0a35e",
    "pink": "#f178b6",
}


@dataclass
class ReportMeta:
    """Метаданные разбора для версионности HTML."""

    generated_at: datetime  # момент генерации файла
    analysis_mode: str  # llm | annotate | cached | autodetect
    llm_model: str | None = None  # имя модели OpenAI, если режим llm/cached


def format_timestamp(dt: datetime) -> str:
    """Человекочитаемая метка времени для шапки HTML."""
    local = dt.astimezone()
    # %z даёт +0300 → превращаем в +03:00 для читаемости.
    tz = local.strftime("%z")
    if len(tz) == 5:
        tz = f"{tz[:3]}:{tz[3:]}"
    return local.strftime("%d.%m.%Y %H:%M:%S") + f" ({tz})"


def versioned_html_path(base: Path, generated_at: datetime) -> Path:
    """Имя HTML с датой-временем: stem-YYYYMMDD-HHMMSS.html."""
    stamp = generated_at.astimezone().strftime("%Y%m%d-%H%M%S")
    return base.parent / f"{base.stem}-{stamp}{base.suffix or '.html'}"


def _esc(s: str) -> str:
    """Экранирование под HTML-текст (амперсанды, угловые скобки, кавычки)."""
    return html.escape(s, quote=True)


def _color_of(chain_id: str | None, chains_by_id: dict[str, Chain]) -> str | None:
    """HEX-цвет цепочки по её id (или None, если слово вне цепочек)."""
    if not chain_id:
        return None
    chain = chains_by_id.get(chain_id)
    if not chain:
        return None
    return PALETTE.get(chain.color, "#cccccc")


def _render_segs(tokens: list[Token], chains_by_id: dict[str, Chain], use_ipa: bool) -> str:
    """Собирает HTML строки: цветные <span> для слов из цепочек, текст — для остального."""
    parts: list[str] = []
    plain = ""
    displays = token_displays_for_output(tokens) if not use_ipa else None

    def flush() -> None:
        nonlocal plain
        if plain:
            parts.append(_esc(plain))
            plain = ""

    for i, tok in enumerate(tokens):
        if tok.is_word and tok.chain:
            flush()
            text = tok.ipa if use_ipa else displays[i]
            color = _color_of(tok.chain, chains_by_id)
            dotted = " w-int" if tok.internal else ""
            parts.append(
                f'<span class="w w-chain{dotted}" data-chain="{_esc(tok.chain)}" '
                f'style="--cc:{color}">{_esc(text)}</span>'
            )
        else:
            plain += tok.ipa if (use_ipa and tok.is_word) else (displays[i] if displays is not None else tok.display)
    flush()
    return "".join(parts)


def _chain_ids_in_block(block: Block) -> list[str]:
    """id цепочек, встречающихся в блоке, в порядке появления (для мини-легенды)."""
    seen: list[str] = []
    for line in block.lines:
        for tok in line.words():
            if tok.chain and tok.chain not in seen:
                seen.append(tok.chain)
    return seen


def _member_counts(blocks: list[Block]) -> dict[str, int]:
    """Сколько слов-вхождений в каждой цепочке (для метрик и графика)."""
    counts: dict[str, int] = {}
    for block in blocks:
        for line in block.lines:
            for tok in line.words():
                if tok.chain:
                    counts[tok.chain] = counts.get(tok.chain, 0) + 1
    return counts


def generate(
    blocks: list[Block],
    chains: list[Chain],
    title: str,
    source: str,
    meta: ReportMeta | None = None,
) -> str:
    """Возвращает полный текст самодостаточного .html."""
    if meta is None:
        meta = ReportMeta(generated_at=datetime.now().astimezone(), analysis_mode="autodetect")

    generated_label = format_timestamp(meta.generated_at)
    iso_time = meta.generated_at.astimezone().isoformat(timespec="seconds")

    # Подпись режима анализа для шапки и футера.
    mode_labels = {
        "llm": "OpenAI LLM",
        "llm-blocks": "OpenAI LLM (по блокам + IPA)",
        "llm-dual": "две модели LLM (union рифм)",
        "cached": "кэш LLM",
        "annotate": "ручной эталон",
        "autodetect": "автодетектор",
    }
    mode_label = mode_labels.get(meta.analysis_mode, meta.analysis_mode)
    model_line = f" · модель: <b>{_esc(meta.llm_model)}</b>" if meta.llm_model else ""
    version_line = (
        f"Версия разбора: <b>{generated_label}</b> · режим: <b>{_esc(mode_label)}</b>{model_line}"
    )
    chains_by_id = {c.id: c for c in chains}
    counts = _member_counts(blocks)

    # --- Текст с подсветкой по блокам ---
    sections_html: list[str] = []
    for block in blocks:
        # Мини-легенда блока: звуки цепочек, встречающихся в нём.
        chips: list[str] = []
        for cid in _chain_ids_in_block(block):
            chain = chains_by_id.get(cid)
            if not chain:
                continue
            color = PALETTE.get(chain.color, "#cccccc")
            chips.append(
                f'<span class="chip" style="--cc:{color}" title="{_esc(chain.words)}">'
                f"{_esc(chain.sound)}</span>"
            )
        chips_html = "".join(chips)

        # Строки блока: основная строка + строка IPA под ней.
        line_rows: list[str] = []
        for line in block.lines:
            segs = _render_segs(line.tokens, chains_by_id, use_ipa=False)
            phon = _render_segs(line.tokens, chains_by_id, use_ipa=True)
            line_rows.append(
                '<div class="line">'
                f'<div class="lrow"><span class="num">{line.no}</span>'
                f'<span class="text">{segs}</span></div>'
                f'<div class="lrow"><span class="num">&rarr;</span>'
                f'<span class="ipa">{phon}</span></div>'
                "</div>"
            )
        sections_html.append(
            '<div class="section">'
            f'<div class="sec-title">{_esc(block.title)}</div>'
            f'<div class="chips">{chips_html}</div>'
            f'<div class="lines">{"".join(line_rows)}</div>'
            "</div>"
        )

    # --- Метрики ---
    n_chains = len(chains)
    n_multi = sum(1 for c in chains if "многослож" in c.kind.lower())
    n_internal = sum(1 for c in chains if "внутр" in c.kind.lower())
    n_words = sum(counts.values())

    # --- Таблица цепочек ---
    table_rows: list[str] = []
    for c in chains:
        color = PALETTE.get(c.color, "#cccccc")
        table_rows.append(
            f'<tr data-chain="{_esc(c.id)}">'
            f'<td style="color:{color};font-weight:600">{_esc(c.sound)}</td>'
            f"<td>{_esc(c.words)}</td>"
            f'<td class="nowrap">{_esc(c.lines)}</td>'
            f"<td>{_esc(c.kind)}</td>"
            "</tr>"
        )
    table_html = "".join(table_rows)

    # --- Бар-чарт: топ цепочек по числу созвучных слов ---
    top = sorted(chains, key=lambda c: counts.get(c.id, 0), reverse=True)[:6]
    max_count = max((counts.get(c.id, 0) for c in top), default=1) or 1
    bar_rows: list[str] = []
    for c in top:
        cnt = counts.get(c.id, 0)
        color = PALETTE.get(c.color, "#cccccc")
        width_pct = cnt / max_count * 100
        bar_rows.append(
            '<div class="bar-row">'
            f'<span class="bar-label" style="color:{color}">{_esc(c.sound)}</span>'
            '<span class="bar-track">'
            f'<span class="bar-fill" style="width:{width_pct:.1f}%;background:{color}"></span>'
            # Подпись данных у каждого бара (требование: подписи у всех точек).
            f'<span class="bar-value">{cnt}</span>'
            "</span>"
            "</div>"
        )
    bars_html = "".join(bar_rows)

    # --- Сборка финального HTML ---
    return _TEMPLATE.format(
        title=_esc(title),
        source=_esc(source),
        sections=" ".join(sections_html),
        table=table_html,
        bars=bars_html,
        n_chains=n_chains,
        n_words=n_words,
        n_multi=n_multi,
        n_internal=n_internal,
        generated_iso=_esc(iso_time),
        generated_label=_esc(generated_label),
        version_line=version_line,
        mode_label=_esc(mode_label),
        model_meta=(
            f'<meta name="rhyme-analyzer-model" content="{_esc(meta.llm_model)}">'
            if meta.llm_model
            else ""
        ),
    )


# Статический шаблон. Плейсхолдеры {…} заполняются через str.format в generate().
# Фигурные скобки CSS удвоены ({{ }}), чтобы str.format их не трогал.
_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="rhyme_analyzer">
<meta name="generated" content="{generated_iso}">
{model_meta}
<title>{title}</title>
<style>
  :root {{
    --bg: #1b1b1d; --card: #242427; --stroke: #36363a;
    --fg: #ececec; --fg2: #b6b6bb; --fg3: #8a8a90;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.5; padding: 32px 20px;
  }}
  .wrap {{ max-width: 940px; margin: 0 auto; }}
  h1 {{ font-size: 26px; margin: 0 0 4px; }}
  h2 {{ font-size: 18px; margin: 28px 0 12px; }}
  .muted {{ color: var(--fg2); }}
  .muted3 {{ color: var(--fg3); }}
  .version {{ font-size: 12.5px; color: var(--fg3); margin-top: 6px; }}

  /* Метрики */
  .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 18px; }}
  .stat {{ background: var(--card); border: 1px solid var(--stroke); border-radius: 12px; padding: 14px 16px; }}
  .stat .v {{ font-size: 26px; font-weight: 700; }}
  .stat .l {{ font-size: 12px; color: var(--fg3); margin-top: 2px; }}

  /* Легенда */
  .legend {{ display: flex; gap: 22px; flex-wrap: wrap; align-items: center; margin: 10px 0 14px; font-size: 13px; }}
  .legend b {{ color: var(--fg); }}
  .legend .int {{
    display: inline-block;
    font-weight: 600;
    color: var(--fg);
    background: color-mix(in srgb, #5fd08a 24%, transparent);
    padding: 0 3px;
    border-radius: 4px;
    text-decoration: underline dotted;
    text-underline-offset: 3px;
    text-decoration-color: #5fd08a;
  }}

  /* Карточка с текстом */
  .card {{ background: var(--card); border: 1px solid var(--stroke); border-radius: 12px; padding: 16px; }}
  .section {{ margin-bottom: 18px; }}
  .sec-title {{ font-size: 12px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; color: var(--fg3); margin-bottom: 6px; }}
  .chips {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }}
  .chip {{
    font-weight: 600;
    font-size: 12.5px;
    white-space: nowrap;
    color: var(--fg);
    background: color-mix(in srgb, var(--cc) 24%, transparent);
    padding: 2px 7px;
    border-radius: 5px;
  }}

  .line {{ padding: 4px 0; border-bottom: 1px solid var(--stroke); }}
  .lrow {{ display: flex; gap: 10px; align-items: baseline; }}
  .num {{ width: 24px; flex-shrink: 0; text-align: right; color: var(--fg3); font-size: 11px; font-variant-numeric: tabular-nums; }}
  .text {{ font-size: 14px; }}
  .ipa {{ font-size: 12.5px; color: var(--fg2); font-style: italic; }}

  /* Слова в цепочках: цвет цепочки = подложка, текст всегда обычный */
  .w-chain {{
    font-weight: 600;
    color: inherit;
    border-radius: 4px;
    padding: 0 3px;
    margin: 0 -1px;
    cursor: default;
    background: color-mix(in srgb, var(--cc) 26%, transparent);
    transition: background 0.12s ease, color 0.12s ease;
  }}
  .ipa .w-chain {{
    background: color-mix(in srgb, var(--cc) 20%, transparent);
  }}
  .w-chain.w-int {{
    text-decoration: underline dotted;
    text-underline-offset: 3px;
    text-decoration-color: color-mix(in srgb, var(--cc) 65%, transparent);
  }}

  /* Наведение: затемняем текст вокруг, подложки активной цепочки остаются и усиливаются */
  .card.focus-chain .text {{
    color: color-mix(in srgb, var(--fg) 46%, var(--bg));
  }}
  .card.focus-chain .ipa {{
    color: color-mix(in srgb, var(--fg2) 46%, var(--bg));
  }}
  .card.focus-chain .w-chain:not(.chain-active) {{
    color: color-mix(in srgb, var(--fg) 46%, var(--bg));
    background: color-mix(in srgb, var(--cc) 10%, transparent);
  }}
  .card.focus-chain .ipa .w-chain:not(.chain-active) {{
    color: color-mix(in srgb, var(--fg2) 46%, var(--bg));
    background: color-mix(in srgb, var(--cc) 8%, transparent);
  }}
  .card.focus-chain .w-chain.chain-active {{
    color: var(--fg);
    background: color-mix(in srgb, var(--cc) 44%, transparent);
    text-decoration-color: var(--cc);
  }}
  .card.focus-chain .ipa .w-chain.chain-active {{
    color: var(--fg2);
    background: color-mix(in srgb, var(--cc) 36%, transparent);
  }}

  table tbody tr.chain-active {{
    background: rgba(255,255,255,0.06);
  }}
  table tbody tr.chain-active td:first-child {{
    box-shadow: inset 3px 0 0 var(--row-cc, #6ba8f7);
  }}

  /* Таблица цепочек */
  table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--stroke); vertical-align: top; }}
  th {{ color: var(--fg3); font-size: 12px; text-transform: uppercase; letter-spacing: 0.4px; }}
  tbody tr:nth-child(odd) {{ background: rgba(255,255,255,0.02); }}
  .nowrap {{ white-space: nowrap; }}

  /* Бар-чарт */
  .chart {{ background: var(--card); border: 1px solid var(--stroke); border-radius: 12px; padding: 16px; }}
  .bar-row {{ display: flex; align-items: center; gap: 12px; margin: 8px 0; }}
  .bar-label {{ width: 150px; flex-shrink: 0; font-weight: 600; font-size: 13px; text-align: right; }}
  .bar-track {{ flex: 1; display: flex; align-items: center; gap: 8px; }}
  .bar-fill {{ height: 18px; border-radius: 5px; min-width: 2px; }}
  .bar-value {{ font-size: 13px; font-weight: 700; color: var(--fg); }}

  .callout {{ background: var(--card); border: 1px solid var(--stroke); border-left: 3px solid #6ba8f7; border-radius: 10px; padding: 14px 16px; margin-top: 20px; font-size: 13px; color: var(--fg2); }}
  hr {{ border: none; border-top: 1px solid var(--stroke); margin: 24px 0; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{title}</h1>
  <div class="muted">Автоматический фонетический разбор рифм. Источник: <b>{source}</b></div>
  <div class="version">{version_line}</div>

  <div class="stats">
    <div class="stat"><div class="v">{n_chains}</div><div class="l">звуковые цепочки</div></div>
    <div class="stat"><div class="v">{n_words}</div><div class="l">созвучных слов</div></div>
    <div class="stat"><div class="v">{n_multi}</div><div class="l">многосложные</div></div>
    <div class="stat"><div class="v">{n_internal}</div><div class="l">с внутр. рифмой</div></div>
  </div>

  <h2>Текст с подсветкой и транскрипцией</h2>
  <div class="legend">
    <span>Цветная <b>подложка</b> = звуковая цепочка · наведите — затемняется текст вокруг</span>
    <span><span class="int">Слово</span> — внутренняя рифма (пунктир)</span>
    <span class="muted3">&rarr; строка снизу — IPA</span>
  </div>
  <div class="card">{sections}</div>

  <h2>Карта звуковых цепочек</h2>
  <table>
    <thead><tr><th>Звук</th><th>Слова</th><th>Строки</th><th>Тип</th></tr></thead>
    <tbody>{table}</tbody>
  </table>

  <h2>Самые длинные цепочки (число созвучных слов)</h2>
  <div class="chart">{bars}</div>
  <div class="muted3" style="font-size:12px;margin-top:6px;">Подписи (число слов) указаны справа от каждого бара.</div>

  <hr>
  <div class="callout">
    <b>Как получено.</b> Пайплайн rhyme_analyzer ({mode_label}, {generated_label}): чистка текста &rarr;
    нормализация (числа/латиница &rarr; произношение) &rarr; G2P/IPA с ударениями &rarr;
    разметка рифменных цепочек &rarr; HTML. Транскрипция под строками — IPA.
  </div>
</div>
<script>
(function () {{
  var card = document.querySelector('.card');
  var table = document.querySelector('table tbody');
  if (!card) return;

  function clearFocus() {{
    card.classList.remove('focus-chain');
    card.removeAttribute('data-active-chain');
    card.querySelectorAll('.w-chain').forEach(function (el) {{
      el.classList.remove('chain-active');
    }});
    if (table) {{
      table.querySelectorAll('tr.chain-active').forEach(function (row) {{
        row.classList.remove('chain-active');
        row.style.removeProperty('--row-cc');
      }});
    }}
  }}

  function focusChain(id, cc) {{
    card.classList.add('focus-chain');
    card.setAttribute('data-active-chain', id);
    card.querySelectorAll('.w-chain').forEach(function (el) {{
      el.classList.toggle('chain-active', el.getAttribute('data-chain') === id);
    }});
    if (table) {{
      table.querySelectorAll('tr[data-chain]').forEach(function (row) {{
        var on = row.getAttribute('data-chain') === id;
        row.classList.toggle('chain-active', on);
        if (on && cc) row.style.setProperty('--row-cc', cc);
      }});
    }}
  }}

  card.addEventListener('mouseover', function (e) {{
    var w = e.target.closest('.w-chain');
    if (!w) {{
      clearFocus();
      return;
    }}
    var id = w.getAttribute('data-chain');
    if (card.getAttribute('data-active-chain') === id) return;
    var cc = w.style.getPropertyValue('--cc') || '';
    focusChain(id, cc);
  }});

  card.addEventListener('mouseleave', clearFocus);
}})();
</script>
</body>
</html>
"""
