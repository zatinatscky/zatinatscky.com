"""Валидация JSON-эталона рифм: «заземление» ответа LLM на реальный текст.

После того как модель вернула схему цепочек, код проверяет:
  • обязательные поля и допустимые цвета;
  • что каждая рифменная единица (unit) реально есть в указанных окнах строк;
  • что в цепочке минимум 2 разных единицы.

Это отсекает галлюцинации модели до этапа рендера.
"""

from __future__ import annotations

from .annotate import _find_unit, _word_tokens_in_windows
from .models import Block

# Допустимые имена цветов (совпадают с палитрой html_gen / canvas_gen).
_VALID_COLORS = frozenset({"purple", "green", "blue", "orange", "pink"})


class ValidationFailed(ValueError):
    """Эталон рифм от LLM не прошёл проверку (units/windows и т.д.)."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


def validate_spec(blocks: list[Block], spec: dict) -> list[str]:
    """Возвращает список ошибок. Пустой список = эталон валиден."""
    errors: list[str] = []

    if not isinstance(spec, dict):
        return ["эталон должен быть JSON-объектом"]

    chains = spec.get("chains")
    if not isinstance(chains, list) or not chains:
        errors.append("поле chains должно быть непустым массивом")
        return errors

    seen_ids: set[str] = set()
    for i, raw in enumerate(chains):
        prefix = f"chains[{i}]"
        if not isinstance(raw, dict):
            errors.append(f"{prefix}: ожидается объект")
            continue

        # --- обязательные поля ---
        cid = raw.get("id")
        if not cid or not isinstance(cid, str):
            errors.append(f"{prefix}: отсутствует id")
            continue
        if cid in seen_ids:
            errors.append(f"{prefix}: дублирующийся id «{cid}»")
        seen_ids.add(cid)

        color = raw.get("color", "")
        if color not in _VALID_COLORS:
            errors.append(f"{prefix} ({cid}): недопустимый color «{color}»")

        for field in ("sound", "words", "lines", "kind"):
            if not raw.get(field):
                errors.append(f"{prefix} ({cid}): пустое поле {field}")

        windows = raw.get("windows")
        if not isinstance(windows, list) or not windows:
            errors.append(f"{prefix} ({cid}): windows должен быть непустым массивом")
            continue

        for w_i, win in enumerate(windows):
            if not (isinstance(win, list) and len(win) == 2):
                errors.append(f"{prefix} ({cid}): windows[{w_i}] должен быть [start, end]")
                continue
            start, end = win
            if not isinstance(start, int) or not isinstance(end, int) or start > end:
                errors.append(f"{prefix} ({cid}): windows[{w_i}] = [{start}, {end}] некорректно")

        units = raw.get("units")
        if not isinstance(units, list) or len(units) < 2:
            errors.append(f"{prefix} ({cid}): units должен содержать минимум 2 единицы")
            continue

        # --- заземление: каждая единица должна встретиться в окнах ---
        tokens = _word_tokens_in_windows(blocks, windows)
        for unit in units:
            if not isinstance(unit, str) or not unit.strip():
                errors.append(f"{prefix} ({cid}): пустая unit")
                continue
            hits = _find_unit(tokens, unit)
            if hits == 0:
                errors.append(
                    f"{prefix} ({cid}): unit «{unit}» не найдена в windows {windows}"
                )

    return errors


def require_valid(blocks: list[Block], spec: dict) -> None:
    """Бросает ValidationFailed, если эталон невалиден."""
    errors = validate_spec(blocks, spec)
    if errors:
        raise ValidationFailed(errors)
