"""Дополнение и слияние цепочек: соседние концовки + рифма через строку."""

from __future__ import annotations

from collections import defaultdict

from .llm.config import PALETTE
from .models import Block, Chain, Line
from .skip_line import (
    AdjacentPhraseMatch,
    CONSECUTIVE_PHRASE_THRESHOLD,
    InternalCrossLineMatch,
    IntraLineRhymeMatch,
    best_adjacent_match,
    consecutive_phrase_similarity,
    find_adjacent_phrase_matches,
    find_adjacent_phrase_pairs,
    find_internal_cross_line_matches,
    find_intra_line_rhyme_matches,
    find_rhyme_boundaries,
    find_skip_line_pairs,
    lines_share_rhyme_group,
    phrase_unit_text,
)
from .yo_restore import fold_yo_for_match


def _norm_unit(unit: str) -> str:
    """Нормализованный unit для сравнения (ё≡е, регистр)."""
    return " ".join(fold_yo_for_match(w) for w in unit.split())


def _chain_ids_on_line_end(line: Line, n_words: int = 2) -> set[str]:
    """id цепочек у последних n_words слов строки."""
    words = line.words()
    if not words:
        return set()
    chunk = words[-n_words:] if len(words) >= n_words else words
    return {w.chain for w in chunk if w.chain}


def _line_window(line_no: int) -> list[int]:
    return [line_no, line_no]


def _new_chain_from_adjacent_match(spec: dict, match: AdjacentPhraseMatch) -> dict:
    """Новая цепочка в spec, если LLM пропустил фонетическую пару."""
    n = len(spec.get("chains") or [])
    kind = "многосложная" if match.asymmetric else "ассонанс"
    return {
        "id": f"phon_{match.line_a.no}_{match.line_b.no}",
        "color": PALETTE[n % len(PALETTE)],
        "sound": "",
        "words": f"{match.unit_a} · {match.unit_b}",
        "lines": (
            f"{match.line_a.no}"
            if match.line_a.no == match.line_b.no
            else f"{match.line_a.no}, {match.line_b.no}"
        ),
        "kind": kind,
        "windows": [
            [match.line_a.no, match.line_a.no],
            [match.line_b.no, match.line_b.no],
        ],
        "units": [match.unit_a, match.unit_b],
    }


def _apply_adjacent_match_to_chain(chain: dict, match: AdjacentPhraseMatch) -> int:
    """Дописывает unit из AdjacentPhraseMatch в цепочку spec."""
    before = len(chain.get("units") or [])
    _ensure_unit(chain, match.unit_a)
    _ensure_unit(chain, match.unit_b)
    _ensure_window(chain, match.line_a.no)
    _ensure_window(chain, match.line_b.no)
    kind = chain.get("kind") or ""
    if match.asymmetric and "многослож" not in kind:
        chain["kind"] = "многосложная"
    elif not kind:
        chain["kind"] = "многосложная"
    return max(0, len(chain.get("units") or []) - before)


def _new_chain_from_internal_cross(spec: dict, match: InternalCrossLineMatch) -> dict:
    """Новая цепочка для внутренней рифмы между соседними строками."""
    n = len(spec.get("chains") or [])
    return {
        "id": f"phon_int_{match.line_a.no}_{match.line_b.no}",
        "color": PALETTE[n % len(PALETTE)],
        "sound": "",
        "words": f"{match.unit_a} · {match.unit_b}",
        "lines": f"{match.line_a.no}, {match.line_b.no}",
        "kind": "внутренняя",
        "windows": [
            [match.line_a.no, match.line_a.no],
            [match.line_b.no, match.line_b.no],
        ],
        "units": [match.unit_a, match.unit_b],
        "_phon_score": match.score,
    }


def _apply_internal_cross_to_chain(chain: dict, match: InternalCrossLineMatch) -> int:
    """Дописывает внутреннюю пару слов в цепочку spec."""
    before = len(chain.get("units") or [])
    _ensure_unit(chain, match.unit_a)
    _ensure_unit(chain, match.unit_b)
    _ensure_window(chain, match.line_a.no)
    _ensure_window(chain, match.line_b.no)
    kind = chain.get("kind") or ""
    if "внутр" not in kind:
        chain["kind"] = "внутренняя"
    return max(0, len(chain.get("units") or []) - before)


def _new_chain_from_intra_line(spec: dict, match: IntraLineRhymeMatch) -> dict:
    """Новая цепочка для внутренней рифмы в одной строке."""
    n = len(spec.get("chains") or [])
    kind = "многосложная" if match.asymmetric else "внутренняя"
    return {
        "id": f"phon_intra_{match.line.no}",
        "color": PALETTE[n % len(PALETTE)],
        "sound": "",
        "words": f"{match.unit_a} · {match.unit_b}",
        "lines": str(match.line.no),
        "kind": kind,
        "windows": [[match.line.no, match.line.no]],
        "units": [match.unit_a, match.unit_b],
        "_phon_score": match.score,
    }


def _apply_intra_line_to_chain(chain: dict, match: IntraLineRhymeMatch) -> int:
    """Дописывает внутристрочную пару в цепочку spec."""
    before = len(chain.get("units") or [])
    _ensure_unit(chain, match.unit_a)
    _ensure_unit(chain, match.unit_b)
    _ensure_window(chain, match.line.no)
    kind = chain.get("kind") or ""
    if match.asymmetric and "многослож" not in kind:
        chain["kind"] = "многосложная"
    elif "внутр" not in kind:
        chain["kind"] = "внутренняя"
    return max(0, len(chain.get("units") or []) - before)


def _chain_ids_on_word(line: Line, word: str) -> set[str]:
    """id цепочек у конкретного слова в строке."""
    return _chain_ids_on_unit(line, word)


def _chain_ids_on_unit(line: Line, unit: str) -> set[str]:
    """id цепочек у слова или многословной единицы в строке."""
    from .annotate import _norm_word, _unit_word_parts

    parts = _unit_word_parts(unit)
    words = line.words()
    n = len(parts)
    ids: set[str] = set()
    for i in range(len(words) - n + 1):
        window = words[i : i + n]
        if [_norm_word(w.display) for w in window] == parts:
            ids.update(w.chain for w in window if w.chain)
    return ids


def _ensure_window(chain: dict, line_no: int) -> None:
    w = _line_window(line_no)
    windows: list = chain.setdefault("windows", [])
    if w not in windows:
        windows.append(w)


def _ensure_unit(chain: dict, unit: str) -> None:
    if not unit.strip():
        return
    units: list = chain.setdefault("units", [])
    nu = _norm_unit(unit)
    if nu not in {_norm_unit(u) for u in units}:
        units.append(unit)


def _find_chain_with_unit(spec: dict, unit: str) -> dict | None:
    nu = _norm_unit(unit)
    for chain in spec.get("chains") or []:
        for u in chain.get("units") or []:
            if _norm_unit(u) == nu:
                return chain
    return None


def _find_chain_touching_line(spec: dict, line_no: int) -> dict | None:
    for chain in spec.get("chains") or []:
        for start, end in chain.get("windows") or []:
            if start <= line_no <= end:
                return chain
    return None


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


def _new_chain_from_skip_line(
    spec: dict,
    line_a: Line,
    line_b: Line,
    unit_a: str,
    unit_b: str,
    *,
    score: float,
) -> dict:
    """Новая цепочка для рифмы через строку (skip-line)."""
    n = len(spec.get("chains") or [])
    return {
        "id": f"phon_skip_{line_a.no}_{line_b.no}",
        "color": PALETTE[n % len(PALETTE)],
        "sound": "",
        "words": f"{unit_a} · {unit_b}",
        "lines": f"{line_a.no}, {line_b.no}",
        "kind": "через строку",
        "windows": [
            [line_a.no, line_a.no],
            [line_b.no, line_b.no],
        ],
        "units": [unit_a, unit_b],
        "_phon_score": score,
    }


def _apply_heuristics_to_spec(blocks: list[Block], spec: dict) -> int:
    """Вносит все фонетические эвристики в spec; создаёт цепочки при необходимости."""
    lines = [line for block in blocks for line in block.lines]
    by_index = {line.index: line for line in lines}
    added = 0

    # 1) Соседние созвучные концовки (2↔2, 1↔2, 1↔3 …).
    for match in find_adjacent_phrase_matches(blocks):
        chain = (
            _find_chain_with_unit(spec, match.unit_b)
            or _find_chain_with_unit(spec, match.unit_a)
            or _find_chain_touching_line(spec, match.line_b.no)
            or _find_chain_touching_line(spec, match.line_a.no)
        )
        if chain is None:
            chain = _new_chain_from_adjacent_match(spec, match)
            chain["_phon_score"] = match.score
            spec.setdefault("chains", []).append(chain)
            added += len(chain.get("units") or [])
            continue
        added += _apply_adjacent_match_to_chain(chain, match)

    # 1b) Внутренняя рифма между соседними строками (гномиков ~ экономике).
    for match in find_internal_cross_line_matches(blocks):
        chain = (
            _find_chain_with_unit(spec, match.unit_b)
            or _find_chain_with_unit(spec, match.unit_a)
        )
        if chain is None:
            chain = _new_chain_from_internal_cross(spec, match)
            spec.setdefault("chains", []).append(chain)
            added += len(chain.get("units") or [])
            continue
        added += _apply_internal_cross_to_chain(chain, match)

    # 1c) Внутренняя рифма в одной строке (дашборд ~ дал в рот).
    for match in find_intra_line_rhyme_matches(blocks):
        tail_word = match.unit_b.split()[-1]
        chain = (
            _find_chain_with_unit(spec, match.unit_b)
            or _find_chain_with_unit(spec, match.unit_a)
            or _find_chain_with_unit(spec, tail_word)
            or _find_chain_touching_line(spec, match.line.no)
        )
        if chain is None:
            chain = _new_chain_from_intra_line(spec, match)
            spec.setdefault("chains", []).append(chain)
            added += len(chain.get("units") or [])
            continue
        added += _apply_intra_line_to_chain(chain, match)

    # 2) Рифма через строку + соседняя строка перед partner (Наших Данных ~ манной ~ ветерану).
    for line_a, line_b, score in find_skip_line_pairs(blocks):
        words_a = line_a.words()
        if not words_a:
            continue
        unit_a = phrase_unit_text(line_a, 2) if len(words_a) >= 2 else words_a[-1].display
        unit_b = line_b.words()[-1].display

        chain = (
            _find_chain_with_unit(spec, unit_a)
            or _find_chain_with_unit(spec, unit_b)
            or _find_chain_touching_line(spec, line_a.no)
            or _find_chain_touching_line(spec, line_b.no)
        )
        if chain is None:
            chain = _new_chain_from_skip_line(
                spec, line_a, line_b, unit_a, unit_b, score=score,
            )
            spec.setdefault("chains", []).append(chain)
            added += len(chain.get("units") or [])
        else:
            before = len(chain.get("units") or [])
            _ensure_unit(chain, unit_a)
            _ensure_unit(chain, unit_b)
            _ensure_window(chain, line_a.no)
            _ensure_window(chain, line_b.no)
            added += max(0, len(chain.get("units") or []) - before)

        if "через строку" not in (chain.get("kind") or ""):
            chain["kind"] = "через строку"

        prev = by_index.get(line_a.index - 1)
        if prev is not None:
            prev_match = consecutive_phrase_similarity(prev, line_a)
            if prev_match >= CONSECUTIVE_PHRASE_THRESHOLD:
                adj = best_adjacent_match(prev, line_a)
                if adj is not None:
                    added += _apply_adjacent_match_to_chain(chain, adj)
                if "многослож" not in (chain.get("kind") or ""):
                    chain["kind"] = "многосложная"

    return added


def build_heuristic_spec(blocks: list[Block], *, title: str = "") -> dict:
    """Полный spec только из фонетических эвристик (без LLM)."""
    spec: dict = {"title": title, "chains": []}
    _apply_heuristics_to_spec(blocks, spec)
    # Цепочка без пары unit бесполезна для разметки.
    spec["chains"] = [
        c for c in spec.get("chains") or []
        if len(c.get("units") or []) >= 2
    ]
    return spec


def _partition_units_by_windows(
    blocks: list[Block],
    units: list[str],
    left_wins: list[list[int]],
    right_wins: list[list[int]],
) -> tuple[list[str], list[str]]:
    """Делит units цепочки по окнам строк слева/справа от разрыва схемы."""
    from .annotate import _find_unit, _word_tokens_in_windows

    left_tokens = _word_tokens_in_windows(blocks, left_wins)
    right_tokens = _word_tokens_in_windows(blocks, right_wins)
    left_units: list[str] = []
    right_units: list[str] = []

    for unit in units:
        if not isinstance(unit, str) or not unit.strip():
            continue
        in_left = _find_unit(left_tokens, unit) > 0
        in_right = _find_unit(right_tokens, unit) > 0
        if in_left and not in_right:
            left_units.append(unit)
        elif in_right and not in_left:
            right_units.append(unit)
        elif in_left and in_right:
            # Редкий случай: unit на обеих сторонах — оставляем на стороне с большим окном.
            left_units.append(unit)
    return left_units, right_units


def _split_chain_dict_at_boundaries(
    chain: dict,
    boundaries: set[int],
    blocks: list[Block],
) -> list[dict]:
    """Режет одну цепочку spec, если разрыв схемы проходит внутри её окон."""
    windows = chain.get("windows") or []
    if not windows or not boundaries:
        return [chain]

    line_nos = sorted({w[0] for w in windows})
    dividers = sorted(
        b for b in boundaries
        if any(n <= b for n in line_nos) and any(n > b for n in line_nos)
    )
    if not dividers:
        return [chain]

    parts: list[dict] = []
    suffixes = "abcdefghijklmnopqrstuvwxyz"
    for div_i, boundary in enumerate(dividers):
        left_wins = [w for w in windows if w[1] <= boundary]
        right_wins = [w for w in windows if w[0] > boundary]
        if not left_wins or not right_wins:
            continue

        max_left = max(w[1] for w in left_wins)
        min_right = min(w[0] for w in right_wins)
        # Между окнами ровно одна строка — рифма через заглушку (11…13), не режем.
        if min_right - max_left == 2:
            continue

        units = chain.get("units") or []
        left_units, right_units = _partition_units_by_windows(
            blocks, units, left_wins, right_wins,
        )
        if len(left_units) < 2 or len(right_units) < 2:
            return [chain]

        base_id = str(chain.get("id", "chain"))
        sfx = suffixes[div_i] if div_i < len(suffixes) else str(div_i)
        left = dict(chain)
        left["id"] = f"{base_id}_{sfx}L"
        left["windows"] = left_wins
        left["units"] = left_units
        left["words"] = " · ".join(left_units)
        left["lines"] = ", ".join(str(w[0]) for w in sorted(left_wins, key=lambda w: w[0]))

        right = dict(chain)
        right["id"] = f"{base_id}_{sfx}R"
        right["windows"] = right_wins
        right["units"] = right_units
        right["words"] = " · ".join(right_units)
        right["lines"] = ", ".join(str(w[0]) for w in sorted(right_wins, key=lambda w: w[0]))
        parts = [left, right]
        break  # один разрыв за проход; для длинных цепочек можно вызывать рекурсивно

    return parts if parts else [chain]


def split_spec_at_rhyme_boundaries(blocks: list[Block], spec: dict) -> tuple[dict, int]:
    """Разрывает цепочки LLM/union на границах смены рифменной схемы.

    Возвращает (обновлённый spec, число разрезанных цепочек).
    """
    boundaries = find_rhyme_boundaries(blocks)
    if not boundaries:
        return spec, 0

    out = dict(spec)
    new_chains: list[dict] = []
    split_count = 0
    for chain in spec.get("chains") or []:
        if not isinstance(chain, dict):
            continue
        parts = _split_chain_dict_at_boundaries(chain, boundaries, blocks)
        if len(parts) > 1:
            split_count += 1
        new_chains.extend(parts)

    out["chains"] = new_chains
    return out, split_count


def supplement_spec_from_phonetics(blocks: list[Block], spec: dict) -> int:
    """Дописывает в spec пропущенные units (обратная совместимость CLI).

    В пайплайне предпочтительнее build_heuristic_spec + merge_specs_union.
    """
    return _apply_heuristics_to_spec(blocks, spec)


def _merge_chain_group(chains: list[Chain], primary_id: str) -> Chain:
    primary = chains[0]
    words: list[str] = []
    seen: set[str] = set()
    for c in chains:
        for part in c.words.split(" · "):
            part = part.strip()
            if part and part not in seen:
                seen.add(part)
                words.append(part)

    lines_parts: list[str] = []
    for c in chains:
        if c.lines and c.lines not in lines_parts:
            lines_parts.append(c.lines)

    kinds = [c.kind for c in chains if c.kind]
    if any("через строку" in k for k in kinds):
        kind = "через строку"
    elif any("многослож" in k.lower() for k in kinds):
        kind = "многосложная"
    else:
        kind = primary.kind

    return Chain(
        id=primary_id,
        color=primary.color,
        sound=primary.sound,
        words=" · ".join(words),
        lines=", ".join(lines_parts),
        kind=kind,
    )


def reconcile_chains(blocks: list[Block], chains: list[Chain], spec: dict) -> list[Chain]:
    """Сливает цепочки с общими units и фонетически связанные строки."""
    if not chains:
        return chains

    boundaries = find_rhyme_boundaries(blocks)
    all_ids = [c.id for c in chains]
    uf = _UnionFind(all_ids)

    def _maybe_union(a: str | None, b: str | None, line_a: int, line_b: int) -> None:
        if not a or not b or a not in uf.parent or b not in uf.parent:
            return
        if not lines_share_rhyme_group(line_a, line_b, boundaries):
            return
        uf.union(a, b)

    # Общие units в spec (напр. «кашей манной» в двух цепочках LLM).
    unit_to_ids: dict[str, set[str]] = defaultdict(set)
    for raw in spec.get("chains") or []:
        cid = raw.get("id")
        if cid not in uf.parent:
            continue
        for unit in raw.get("units") or []:
            key = _norm_unit(unit)
            for other in unit_to_ids[key]:
                uf.union(cid, other)
            unit_to_ids[key].add(cid)

    # Фонетические связи по размеченным концам строк.
    for match in find_adjacent_phrase_matches(blocks):
        for a in _chain_ids_on_line_end(match.line_a, match.n_words_a):
            for b in _chain_ids_on_line_end(match.line_b, match.n_words_b):
                _maybe_union(a, b, match.line_a.no, match.line_b.no)

    for match in find_internal_cross_line_matches(blocks):
        for a in _chain_ids_on_word(match.line_a, match.unit_a):
            for b in _chain_ids_on_word(match.line_b, match.unit_b):
                _maybe_union(a, b, match.line_a.no, match.line_b.no)

    for match in find_intra_line_rhyme_matches(blocks):
        for a in _chain_ids_on_unit(match.line, match.unit_a):
            for b in _chain_ids_on_unit(match.line, match.unit_b):
                _maybe_union(a, b, match.line.no, match.line.no)

    for line_a, line_b, _ in find_adjacent_phrase_pairs(blocks):
        for a in _chain_ids_on_line_end(line_a, 2):
            for b in _chain_ids_on_line_end(line_b, 2):
                _maybe_union(a, b, line_a.no, line_b.no)

    for line_a, line_b, _ in find_skip_line_pairs(blocks):
        for a in _chain_ids_on_line_end(line_a, 2):
            for b in _chain_ids_on_line_end(line_b, 2):
                _maybe_union(a, b, line_a.no, line_b.no)
        last_b = line_b.words()[-1].chain if line_b.words() else None
        if last_b:
            for a in _chain_ids_on_line_end(line_a, 2):
                _maybe_union(a, last_b, line_a.no, line_b.no)

    groups: dict[str, list[str]] = defaultdict(list)
    for cid in all_ids:
        groups[uf.find(cid)].append(cid)

    id_map = {cid: root for root, members in groups.items() for cid in members}

    for block in blocks:
        for line in block.lines:
            for tok in line.tokens:
                if tok.chain and tok.chain in id_map:
                    tok.chain = id_map[tok.chain]

    by_id = {c.id: c for c in chains}
    merged: list[Chain] = []
    for root, members in groups.items():
        merged.append(_merge_chain_group([by_id[m] for m in members if m in by_id], root))
    return merged


def count_chain_members(blocks: list[Block]) -> dict[str, int]:
    """Сколько слов размечено в каждой цепочке."""
    counts: dict[str, int] = {}
    for block in blocks:
        for line in block.lines:
            for tok in line.words():
                if tok.chain:
                    counts[tok.chain] = counts.get(tok.chain, 0) + 1
    return counts


def finalize_chains(blocks: list[Block], chains: list[Chain]) -> list[Chain]:
    """Убирает одиночные «цепочки» и снимает подсветку с осиротевших слов."""
    counts = count_chain_members(blocks)
    valid = {cid for cid, n in counts.items() if n >= 2}

    for block in blocks:
        for line in block.lines:
            for tok in line.tokens:
                if tok.chain and tok.chain not in valid:
                    tok.chain = None
                    tok.internal = False

    return [c for c in chains if c.id in valid]
