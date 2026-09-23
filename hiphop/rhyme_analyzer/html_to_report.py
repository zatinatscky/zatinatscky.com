"""Импорт legacy HTML-отчётов в JSON для единого рендера на фронтенде.

Парсит формат, который генерирует html_gen.generate(), и восстанавливает
структуру report version=1. Старые записи журнала получают тот же UI, что и новые.
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path
from typing import Any

from .html_gen import PALETTE
from .report_data import REPORT_VERSION

# HEX → имя цвета палитры (обратное к PALETTE).
_HEX_TO_COLOR = {v.lower(): k for k, v in PALETTE.items()}

# Фрагмент строки: span цепочки или обычный текст.
_CHUNK_RE = re.compile(
    r'<span class="[^"]*w-chain([^"]*)" data-chain="([^"]*)"[^>]*>([^<]*)</span>|([^<]+)',
    re.DOTALL,
)

# Одна строка песни: номер, текст, IPA.
_LINE_RE = re.compile(
    r'<div class="line">'
    r'<div class="lrow"><span class="num">(\d+)</span><span class="text">(.*?)</span></div>'
    r'<div class="lrow"><span class="num">&rarr;</span><span class="ipa">(.*?)</span></div>'
    r"</div>",
    re.DOTALL,
)

# Строка таблицы цепочек.
_CHAIN_ROW_RE = re.compile(
    r'<tr data-chain="([^"]+)">'
    r'<td style="color:([^;"]+)[^"]*"[^>]*>([^<]*)</td>'
    r"<td>([^<]*)</td>"
    r'<td[^>]*>([^<]*)</td>'
    r"<td>([^<]*)</td>"
    r"</tr>",
    re.DOTALL,
)


def _extract_div_inner(html: str, class_name: str, start_at: int = 0) -> tuple[str, int] | tuple[None, int]:
    """Возвращает inner HTML ближайшего <div class="…"> с учётом вложенности."""
    marker = f'<div class="{class_name}">'
    start = html.find(marker, start_at)
    if start < 0:
        return None, start_at
    pos = start + len(marker)
    depth = 1
    i = pos
    while i < len(html) and depth > 0:
        next_open = html.find("<div", i)
        next_close = html.find("</div>", i)
        if next_close < 0:
            break
        if next_open >= 0 and next_open < next_close:
            depth += 1
            i = next_open + 4
        else:
            depth -= 1
            if depth == 0:
                return html[pos:next_close], next_close + 6
            i = next_close + 6
    return None, start_at


def _hex_to_color(hex_val: str) -> str:
    return _HEX_TO_COLOR.get(hex_val.strip().lower(), "purple")


def _parse_chunks(fragment: str) -> list[dict[str, Any]]:
    """Разбирает inner HTML .text / .ipa на куски (цепочка или plain)."""
    chunks: list[dict[str, Any]] = []
    pos = 0
    while pos < len(fragment):
        m = _CHUNK_RE.match(fragment, pos)
        if not m:
            break
        if m.group(2):
            chunks.append(
                {
                    "kind": "chain",
                    "chain": m.group(2),
                    "text": unescape(m.group(3)),
                    "internal": "w-int" in (m.group(1) or ""),
                }
            )
        else:
            chunks.append({"kind": "plain", "text": unescape(m.group(4) or "")})
        pos = m.end()
    return chunks


def _chunks_to_tokens(text_chunks: list[dict], ipa_chunks: list[dict]) -> list[dict[str, Any]]:
    """Сливает параллельные куски текста и IPA в список токенов."""
    tokens: list[dict[str, Any]] = []
    n = max(len(text_chunks), len(ipa_chunks))
    for i in range(n):
        tc = text_chunks[i] if i < len(text_chunks) else {"kind": "plain", "text": ""}
        ic = ipa_chunks[i] if i < len(ipa_chunks) else {"kind": "plain", "text": ""}
        if tc["kind"] == "chain" or ic["kind"] == "chain":
            tokens.append(
                {
                    "display": tc.get("text", ""),
                    "is_word": True,
                    "ipa": ic.get("text", tc.get("text", "")),
                    "chain": tc.get("chain") or ic.get("chain"),
                    "internal": tc.get("internal", False),
                }
            )
        else:
            plain = tc.get("text", "")
            if plain:
                tokens.append(
                    {
                        "display": plain,
                        "is_word": False,
                        "ipa": ic.get("text", plain),
                        "chain": None,
                        "internal": False,
                    }
                )
    return tokens


def _parse_sections(card_html: str) -> list[dict[str, Any]]:
    """Извлекает блоки (.section) из HTML карточки."""
    blocks: list[dict[str, Any]] = []
    pos = 0
    while True:
        sec_start = card_html.find('<div class="section">', pos)
        if sec_start < 0:
            break
        title_m = re.search(r'<div class="sec-title">([^<]*)</div>', card_html[sec_start:])
        title = unescape(title_m.group(1)) if title_m else "Секция"
        lines_html, next_pos = _extract_div_inner(card_html, "lines", sec_start)
        pos = next_pos if next_pos > sec_start else sec_start + 1
        lines = _parse_lines(lines_html or "")
        blocks.append({"title": title, "section_kind": "other", "lines": lines})
    return blocks


def _parse_lines(lines_html: str) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for m in _LINE_RE.finditer(lines_html):
        no = int(m.group(1))
        text_chunks = _parse_chunks(m.group(2))
        ipa_chunks = _parse_chunks(m.group(3))
        lines.append({"no": no, "index": no - 1, "tokens": _chunks_to_tokens(text_chunks, ipa_chunks)})
    return lines


def _parse_meta(html: str) -> dict[str, Any]:
    """Извлекает метаданные из шапки HTML."""
    meta: dict[str, Any] = {}

    m_gen = re.search(r'<meta name="generated" content="([^"]+)"', html)
    if m_gen:
        meta["generated_at"] = m_gen.group(1)

    m_model = re.search(r'<meta name="rhyme-analyzer-model" content="([^"]+)"', html)
    if m_model:
        meta["llm_model"] = unescape(m_model.group(1))

    stats = re.findall(r'<div class="stat"><div class="v">(\d+)</div><div class="l">([^<]+)</div></div>', html)
    labels = {unescape(lbl).strip(): int(val) for val, lbl in stats}
    meta["chains"] = labels.get("звуковые цепочки", 0)
    meta["rhyme_words"] = labels.get("созвучных слов", 0)
    meta["multi"] = labels.get("многосложные", 0)
    meta["internal"] = labels.get("с внутр. рифмой", 0)

    m_mode = re.search(r"режим:\s*<b>([^<]+)</b>", html)
    if m_mode:
        mode_label = unescape(m_mode.group(1))
        mode_map = {
            "OpenAI LLM": "llm",
            "OpenAI LLM (по блокам + IPA)": "llm-blocks",
            "две модели LLM (union рифм)": "llm-dual",
            "кэш LLM": "cached",
            "ручной эталон": "annotate",
            "автодетектор": "autodetect",
        }
        meta["analysis_mode"] = mode_map.get(mode_label, mode_label)

    return meta


def html_to_report(html: str) -> dict[str, Any]:
    """Преобразует legacy HTML в JSON-отчёт version=1."""
    m_title = re.search(r"<title>([^<]*)</title>", html)
    song = unescape(m_title.group(1)) if m_title else "Без названия"

    m_source = re.search(r"Источник:\s*<b>([^<]+)</b>", html)
    source = unescape(m_source.group(1)) if m_source else "legacy-html"

    chains: list[dict[str, Any]] = []
    for m in _CHAIN_ROW_RE.finditer(html):
        cid = m.group(1)
        color = _hex_to_color(m.group(2))
        chains.append(
            {
                "id": cid,
                "color": color,
                "sound": unescape(m.group(3)),
                "words": unescape(m.group(4)),
                "lines": unescape(m.group(5)),
                "kind": unescape(m.group(6)),
            }
        )

    card_m = re.search(r'<div class="card">(.*)</div>\s*<h2>Карта звуковых цепочек', html, re.DOTALL)
    card_html = card_m.group(1) if card_m else html
    blocks = _parse_sections(card_html)

    # Счётчики слов в цепочках — из разобранных токенов (без дубля text+IPA).
    member_counts = {}
    for block in blocks:
        for line in block["lines"]:
            for tok in line["tokens"]:
                cid = tok.get("chain")
                if cid:
                    member_counts[cid] = member_counts.get(cid, 0) + 1

    meta = _parse_meta(html)
    meta.setdefault("blocks", len(blocks))
    meta.setdefault("lines", sum(len(b["lines"]) for b in blocks))

    return {
        "version": REPORT_VERSION,
        "song": song,
        "source": source,
        "palette": dict(PALETTE),
        "meta": meta,
        "blocks": blocks,
        "chains": chains,
        "member_counts": member_counts,
        "imported_from": "html",
    }


def html_file_to_report(path: Path) -> dict[str, Any]:
    return html_to_report(path.read_text(encoding="utf-8"))
