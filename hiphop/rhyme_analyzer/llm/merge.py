"""Слияние результатов анализа по блокам в один JSON-эталон."""

from __future__ import annotations

from collections import defaultdict

from ..models import Block
from ..yo_restore import fold_yo_for_match
from .config import PALETTE


def _chain_signature(chain: dict) -> frozenset[str]:
    """Сигнатура цепочки для дедупликации повторяющихся припевов."""
    units = tuple(u.lower() for u in chain.get("units", []))
    return frozenset(units)


def _merge_windows(a: list[list[int]], b: list[list[int]]) -> list[list[int]]:
    """Объединяет окна строк без дубликатов."""
    seen: set[tuple[int, int]] = set()
    merged: list[list[int]] = []
    for win in a + b:
        if len(win) != 2:
            continue
        key = (win[0], win[1])
        if key not in seen:
            seen.add(key)
            merged.append([win[0], win[1]])
    return sorted(merged, key=lambda w: (w[0], w[1]))


def merge_block_results(
    blocks: list[Block],
    block_results: list[dict],
    *,
    title: str,
) -> dict:
    """Склеивает chains из всех блоков; дедуплицирует идентичные припевные цепочки."""
    merged_chains: list[dict] = []
    sig_index: dict[frozenset[str], int] = {}

    for block_idx, (block, result) in enumerate(zip(blocks, block_results)):
        chains = result.get("chains") or []
        for local_i, raw in enumerate(chains):
            chain = dict(raw)
            sig = _chain_signature(chain)

            if sig in sig_index:
                # Тот же набор units (типичный припев) — расширяем windows, не плодим дубликат.
                existing = merged_chains[sig_index[sig]]
                existing["windows"] = _merge_windows(
                    existing.get("windows", []), chain.get("windows", [])
                )
                continue

            # Уникальный id и глобальный цвет по порядку появления.
            chain["id"] = f"b{block_idx + 1}_{chain.get('id', local_i + 1)}"
            chain["color"] = PALETTE[len(merged_chains) % len(PALETTE)]
            merged_chains.append(chain)
            sig_index[sig] = len(merged_chains) - 1

    return {"title": title, "chains": merged_chains}


def _units_signature(chain: dict) -> frozenset[str]:
    """Нормализованный набор units для сравнения цепочек."""
    units = chain.get("units") or []
    return frozenset(u.strip().lower() for u in units if isinstance(u, str) and u.strip())


def merge_specs(
    spec_a: dict,
    spec_b: dict,
    *,
    title: str,
) -> tuple[dict, dict[str, int]]:
    """Объединяет эталоны двух моделей: union цепочек с дедупликацией по units.

    Если набор units совпадает — расширяем windows, не дублируем цепочку.
    Возвращает (merged_spec, stats) для meta в отчёте.
    """
    merged_chains: list[dict] = []
    sig_index: dict[frozenset[str], int] = {}
    skipped = 0

    for raw in list(spec_a.get("chains") or []) + list(spec_b.get("chains") or []):
        if not isinstance(raw, dict):
            skipped += 1
            continue
        chain = dict(raw)
        sig = _units_signature(chain)
        if len(sig) < 2:
            skipped += 1
            continue

        if sig in sig_index:
            existing = merged_chains[sig_index[sig]]
            existing["windows"] = _merge_windows(
                existing.get("windows", []), chain.get("windows", [])
            )
            continue

        chain["id"] = str(len(merged_chains) + 1)
        chain["color"] = PALETTE[len(merged_chains) % len(PALETTE)]
        merged_chains.append(chain)
        sig_index[sig] = len(merged_chains) - 1

    n_a = len(spec_a.get("chains") or [])
    n_b = len(spec_b.get("chains") or [])
    stats = {
        "chains_model_a": n_a,
        "chains_model_b": n_b,
        "chains_merged": len(merged_chains),
        "chains_union_added": max(0, len(merged_chains) - n_a),
        "chains_skipped": skipped,
    }
    return {"title": title, "chains": merged_chains}, stats


def _norm_unit(unit: str) -> str:
    """Нормализованный unit для сравнения (ё≡е, регистр)."""
    return " ".join(fold_yo_for_match(w) for w in unit.split())


def _chain_priority(chain: dict) -> tuple[int, int, int]:
    """Меньше = предпочтительнее как «главная» цепочка при слиянии."""
    cid = str(chain.get("id", ""))
    is_phon = cid.startswith("phon_")
    has_sound = bool(str(chain.get("sound", "")).strip())
    n_units = len(chain.get("units") or [])
    return (1 if is_phon else 0, 0 if has_sound else 1, -n_units)


def _merge_kind(kinds: list[str], fallback: str) -> str:
    if any("через строку" in k for k in kinds):
        return "через строку"
    if any("многослож" in k.lower() for k in kinds):
        return "многосложная"
    if any("внутр" in k.lower() for k in kinds):
        return next(k for k in kinds if "внутр" in k.lower())
    if any("ассонанс" in k.lower() for k in kinds):
        return next(k for k in kinds if "ассонанс" in k.lower())
    return fallback or (kinds[0] if kinds else "")


def _merge_chain_dicts(chains: list[dict]) -> dict:
    """Склеивает несколько цепочек с пересекающимися units в одну."""
    ordered = sorted(chains, key=_chain_priority)
    primary = ordered[0]
    merged = dict(primary)

    units: list[str] = []
    seen_units: set[str] = set()
    windows: list[list[int]] = []
    seen_wins: set[tuple[int, int]] = set()
    kinds: list[str] = []

    for chain in ordered:
        for unit in chain.get("units") or []:
            if not isinstance(unit, str) or not unit.strip():
                continue
            key = _norm_unit(unit)
            if key not in seen_units:
                seen_units.add(key)
                units.append(unit)
        for win in chain.get("windows") or []:
            if len(win) == 2:
                wkey = (win[0], win[1])
                if wkey not in seen_wins:
                    seen_wins.add(wkey)
                    windows.append([win[0], win[1]])
        kind = chain.get("kind") or ""
        if kind:
            kinds.append(kind)

    merged["units"] = units
    merged["windows"] = _merge_windows(windows, [])
    merged["kind"] = _merge_kind(kinds, str(primary.get("kind") or ""))

    if not str(merged.get("words", "")).strip() or merged.get("words") == " · ".join(
        primary.get("units") or []
    ):
        merged["words"] = " · ".join(units)

    if windows:
        line_nos = sorted({w[0] for w in merged["windows"]})
        merged["lines"] = ", ".join(str(n) for n in line_nos)

    merged.pop("_phon_score", None)
    return merged


class _UnionFind:
    def __init__(self, ids: list[str]) -> None:
        self.parent = {i: i for i in ids}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def merge_specs_union(
    spec_llm: dict,
    spec_heuristic: dict,
    *,
    title: str,
) -> tuple[dict, dict[str, int]]:
    """Union LLM-spec и heuristic-spec: цепочки с общими units сливаются.

    В отличие от merge_specs (дедуп по полному набору units), здесь
    «кашей манной» из LLM и «ветерану» из эвристики объединяются,
    если делят хотя бы один unit.
    """
    raw_chains: list[dict] = []
    skipped = 0

    for i, raw in enumerate(
        list(spec_llm.get("chains") or []) + list(spec_heuristic.get("chains") or [])
    ):
        if not isinstance(raw, dict):
            skipped += 1
            continue
        chain = dict(raw)
        units = chain.get("units") or []
        if len(units) < 2:
            skipped += 1
            continue
        chain["_merge_id"] = f"m{i}"
        raw_chains.append(chain)

    if not raw_chains:
        stats = {
            "chains_llm": len(spec_llm.get("chains") or []),
            "chains_heuristic": len(spec_heuristic.get("chains") or []),
            "chains_merged": 0,
            "chains_union_added": 0,
            "chains_skipped": skipped,
        }
        return {"title": title, "chains": []}, stats

    uf = _UnionFind([c["_merge_id"] for c in raw_chains])
    unit_to_ids: dict[str, set[str]] = defaultdict(set)

    for chain in raw_chains:
        mid = chain["_merge_id"]
        for unit in chain.get("units") or []:
            key = _norm_unit(unit)
            for other in unit_to_ids[key]:
                uf.union(mid, other)
            unit_to_ids[key].add(mid)

    groups: dict[str, list[str]] = defaultdict(list)
    for chain in raw_chains:
        groups[uf.find(chain["_merge_id"])].append(chain["_merge_id"])

    merged_chains: list[dict] = []
    for members in groups.values():
        group = [c for c in raw_chains if c["_merge_id"] in members]
        merged = _merge_chain_dicts(group)
        merged.pop("_merge_id", None)
        merged_chains.append(merged)

    n_llm = len(spec_llm.get("chains") or [])
    n_heur = len(spec_heuristic.get("chains") or [])
    stats = {
        "chains_llm": n_llm,
        "chains_heuristic": n_heur,
        "chains_merged": len(merged_chains),
        "chains_union_added": max(0, len(merged_chains) - n_llm),
        "chains_skipped": skipped,
    }
    return {"title": title, "chains": merged_chains}, stats
