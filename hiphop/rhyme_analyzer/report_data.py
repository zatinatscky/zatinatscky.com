"""Сериализация разбора в JSON для журнала и фронтенд-превью.

Формат version=1: blocks + chains + meta — UI рендерится на клиенте,
поэтому обновления дизайна применяются ко всем сохранённым разборам.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .html_gen import PALETTE
from .models import Block, Chain, Line, Token
from .text_display import token_displays_for_output

REPORT_VERSION = 1


def _line_to_dict(line: Line) -> dict[str, Any]:
    displays = token_displays_for_output(line.tokens)
    return {
        "no": line.no,
        "index": line.index,
        "tokens": [
            {
                "display": displays[i],
                "is_word": tok.is_word,
                "ipa": tok.ipa,
                "chain": tok.chain,
                "internal": tok.internal,
            }
            for i, tok in enumerate(line.tokens)
        ],
    }


def _block_to_dict(block: Block) -> dict[str, Any]:
    return {
        "title": block.title,
        "section_kind": block.section_kind,
        "lines": [_line_to_dict(ln) for ln in block.lines],
    }


def _chain_to_dict(chain: Chain) -> dict[str, Any]:
    return {
        "id": chain.id,
        "color": chain.color,
        "sound": chain.sound,
        "words": chain.words,
        "lines": chain.lines,
        "kind": chain.kind,
    }


def _member_counts(blocks: list[Block]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for block in blocks:
        for line in block.lines:
            for tok in line.words():
                if tok.chain:
                    counts[tok.chain] = counts.get(tok.chain, 0) + 1
    return counts


def build_report(
    blocks: list[Block],
    chains: list[Chain],
    *,
    song: str,
    source: str,
    generated_at: datetime,
    analysis_mode: str,
    llm_model: str | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Собирает JSON-отчёт после annotate."""
    counts = _member_counts(blocks)
    n_multi = sum(1 for c in chains if "многослож" in c.kind.lower())
    n_internal = sum(1 for c in chains if "внутр" in c.kind.lower())

    meta: dict[str, Any] = {
        "generated_at": generated_at.astimezone().isoformat(timespec="seconds"),
        "analysis_mode": analysis_mode,
        "llm_model": llm_model,
        "blocks": len(blocks),
        "lines": sum(len(b.lines) for b in blocks),
        "chains": len(chains),
        "rhyme_words": sum(counts.values()),
        "multi": n_multi,
        "internal": n_internal,
    }
    if extra_meta:
        meta.update(extra_meta)

    return {
        "version": REPORT_VERSION,
        "song": song,
        "source": source,
        "palette": dict(PALETTE),
        "meta": meta,
        "blocks": [_block_to_dict(b) for b in blocks],
        "chains": [_chain_to_dict(c) for c in chains],
        "member_counts": counts,
    }


def _token_from_dict(raw: dict[str, Any]) -> Token:
    return Token(
        display=str(raw.get("display", "")),
        is_word=bool(raw.get("is_word")),
        ipa=str(raw.get("ipa", "")),
        chain=raw.get("chain"),
        internal=bool(raw.get("internal")),
    )


def _line_from_dict(raw: dict[str, Any]) -> Line:
    tokens = [_token_from_dict(t) for t in raw.get("tokens") or [] if isinstance(t, dict)]
    return Line(
        no=int(raw.get("no", 0)),
        index=int(raw.get("index", 0)),
        tokens=tokens,
    )


def _block_from_dict(raw: dict[str, Any]) -> Block:
    lines = [_line_from_dict(ln) for ln in raw.get("lines") or [] if isinstance(ln, dict)]
    return Block(
        title=str(raw.get("title", "")),
        lines=lines,
        section_kind=str(raw.get("section_kind", "other")),
    )


def _chain_from_dict(raw: dict[str, Any]) -> Chain:
    return Chain(
        id=str(raw.get("id", "")),
        color=str(raw.get("color", "purple")),
        sound=str(raw.get("sound", "")),
        words=str(raw.get("words", "")),
        lines=str(raw.get("lines", "")),
        kind=str(raw.get("kind", "")),
    )


def parse_report(data: dict[str, Any]) -> tuple[list[Block], list[Chain], dict[str, Any]]:
    """Восстанавливает blocks, chains и заголовочные поля из JSON."""
    if not isinstance(data, dict):
        raise ValueError("отчёт должен быть JSON-объектом")
    blocks = [_block_from_dict(b) for b in data.get("blocks") or [] if isinstance(b, dict)]
    chains = [_chain_from_dict(c) for c in data.get("chains") or [] if isinstance(c, dict)]
    header = {
        "song": data.get("song", ""),
        "source": data.get("source", ""),
        "meta": data.get("meta") or {},
        "palette": data.get("palette") or dict(PALETTE),
        "member_counts": data.get("member_counts") or {},
        "version": data.get("version", REPORT_VERSION),
    }
    return blocks, chains, header
