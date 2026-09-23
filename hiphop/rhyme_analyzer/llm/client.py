"""Обёртка над OpenAI-совместимыми API (OpenAI, DeepSeek)."""

from __future__ import annotations

import json
import os
import re

from openai import AuthenticationError, OpenAI

from .config import (
    DEEPSEEK_BASE_URL,
    PROVIDER_ENV_KEYS,
    PROVIDER_LABELS,
    ProviderId,
    model_provider,
)
from .schema import BLOCK_RESPONSE_SCHEMA, SYSTEM_PROMPT


def mask_key(key: str) -> str:
    if len(key) <= 12:
        return "(слишком короткий)"
    return f"{key[:10]}...{key[-4:]}"


def _check_api_key(key: str, *, env_name: str) -> None:
    """Проверка, что ключ не плейсхолдер."""
    bad = {"sk-...", "sk-…", "your-api-key", "changeme"}
    stripped = key.strip()
    if stripped in bad or stripped.endswith("..."):
        raise EnvironmentError(
            f"{env_name} похож на плейсхолдер (sk-...). "
            f"Вставьте настоящий ключ в .env или выполните: unset {env_name}"
        )
    if not stripped.startswith("sk-"):
        raise EnvironmentError(f"{env_name} должен начинаться с sk-.")


def resolve_api_key(*, provider: ProviderId, api_key: str | None = None) -> str:
    """Ключ для провайдера: явный аргумент или переменная окружения."""
    env_name = PROVIDER_ENV_KEYS[provider]
    key = (api_key or os.environ.get(env_name) or "").strip()
    if not key:
        label = PROVIDER_LABELS[provider]
        raise EnvironmentError(f"не задан {env_name} (нужен для {label})")
    _check_api_key(key, env_name=env_name)
    return key


def completion_kwargs(model: str, *, provider: ProviderId) -> dict:
    """Параметры sampling: зависят от модели и провайдера."""
    m = model.lower()
    # DeepSeek (включая thinking/reasoner) не использует temperature.
    if provider == "deepseek":
        return {}
    if m.startswith("gpt-5") or m.startswith("o"):
        return {}
    return {"temperature": 0}


def _deepseek_api_kwargs(model: str) -> tuple[str, dict]:
    """Имя модели в API DeepSeek + доп. параметры (thinking mode)."""
    m = model.lower()
    if m == "deepseek-v4-pro":
        return "deepseek-v4-pro", {
            "reasoning_effort": "high",
            "extra_body": {"thinking": {"type": "enabled"}},
        }
    if m == "deepseek-v4-flash":
        return "deepseek-v4-flash", {
            "extra_body": {"thinking": {"type": "disabled"}},
        }
    # legacy-алиасы: deepseek-chat, deepseek-reasoner
    return model, {}


def _response_format(*, provider: ProviderId) -> dict:
    """OpenAI — strict json_schema; DeepSeek — json_object (их JSON mode)."""
    if provider == "deepseek":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "rhyme_block_analysis",
            "strict": True,
            "schema": BLOCK_RESPONSE_SCHEMA,
        },
    }


def _parse_windows_from_lines(lines_text: str) -> list[list[int]]:
    """Пытается восстановить windows из текстового поля lines."""
    nums = [int(n) for n in re.findall(r"\d+", lines_text or "")]
    if len(nums) < 2:
        return []
    windows: list[list[int]] = []
    # Пары [start, end]: "1-2, 4-4" -> [1,2], [4,4]
    for i in range(0, len(nums) - 1, 2):
        start, end = nums[i], nums[i + 1]
        if start > end:
            start, end = end, start
        windows.append([start, end])
    return windows


def _lines_from_windows(windows: list[list[int]]) -> str:
    """Строит компактную подпись строк из окон."""
    parts: list[str] = []
    for win in windows:
        if not (isinstance(win, list) and len(win) == 2):
            continue
        start, end = win
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        parts.append(str(start) if start == end else f"{start}-{end}")
    return ", ".join(parts)


def _clean_units(raw_units: object) -> list[str]:
    """Список непустых units из ответа модели."""
    if not isinstance(raw_units, list):
        return []
    return [u.strip() for u in raw_units if isinstance(u, str) and u.strip()]


def _sound_from_units(units: list[str]) -> str:
    """Краткий фонетический паттерн из последних слов units (fallback для DeepSeek)."""
    tails: list[str] = []
    for unit in units[:4]:
        words = unit.split()
        if words:
            tails.append(words[-1].lower())
    return " ~ ".join(tails) if tails else "—"


def _normalize_chain(chain: dict, idx: int) -> dict:
    """Дозаполняет критичные поля, которые часто пропускает json_object-режим."""
    out = dict(chain)
    # id обязателен в валидаторе.
    if not out.get("id"):
        out["id"] = str(idx + 1)
    # color обязателен и ограничен схемой.
    if out.get("color") not in {"purple", "green", "blue", "orange", "pink"}:
        out["color"] = ["purple", "green", "blue", "orange", "pink"][idx % 5]

    windows = out.get("windows")
    if not isinstance(windows, list) or not windows:
        recovered = _parse_windows_from_lines(str(out.get("lines", "")))
        if recovered:
            out["windows"] = recovered
            windows = recovered

    if not str(out.get("lines", "")).strip() and isinstance(windows, list) and windows:
        out["lines"] = _lines_from_windows(windows)

    # Часто модель отдаёт words, но не units (OpenAI) — или наоборот (DeepSeek).
    units = _clean_units(out.get("units"))
    if len(units) < 2 and out.get("words"):
        units = [p.strip() for p in str(out["words"]).split("·") if p.strip()]
    if len(units) >= 2:
        out["units"] = units
        if not str(out.get("words", "")).strip():
            out["words"] = " · ".join(units)
        if not str(out.get("sound", "")).strip():
            out["sound"] = _sound_from_units(units)
        if not str(out.get("kind", "")).strip():
            out["kind"] = "концевая"
    return out


def _normalize_model_output(payload: dict) -> dict:
    """Нормализует общий формат ответа модели к ожидаемому spec."""
    if not isinstance(payload, dict):
        return {"chains": []}
    chains = payload.get("chains")
    if not isinstance(chains, list):
        return {"chains": []}
    return {"chains": [_normalize_chain(ch, i) if isinstance(ch, dict) else {} for i, ch in enumerate(chains)]}


class RhymeLlmClient:
    """Клиент для одного structured-output запроса на блок."""

    def __init__(self, *, model: str, api_key: str | None = None) -> None:
        self.model = model
        self.provider = model_provider(model)
        self._key = resolve_api_key(provider=self.provider, api_key=api_key)
        client_kwargs: dict = {"api_key": self._key}
        if self.provider == "deepseek":
            client_kwargs["base_url"] = DEEPSEEK_BASE_URL
        self._client = OpenAI(**client_kwargs)

    @property
    def masked_key(self) -> str:
        return mask_key(self._key)

    @property
    def provider_label(self) -> str:
        return PROVIDER_LABELS[self.provider]

    def analyze_block(self, *, model: str, user_prompt: str) -> dict:
        """Запрос к API; возвращает dict с ключом chains."""
        provider = model_provider(model)
        api_model = model
        request_kwargs = completion_kwargs(model, provider=provider)
        if provider == "deepseek":
            api_model, ds_kwargs = _deepseek_api_kwargs(model)
            request_kwargs = {**request_kwargs, **ds_kwargs}
        try:
            response = self._client.chat.completions.create(
                model=api_model,
                **request_kwargs,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=_response_format(provider=provider),
            )
        except AuthenticationError as exc:
            env_name = PROVIDER_ENV_KEYS[provider]
            raise EnvironmentError(
                f"{PROVIDER_LABELS[provider]} отклонил API-ключ (401). "
                f"Проверьте .env и выполните: unset {env_name}\n"
                f"  Ключ: {self.masked_key}"
            ) from exc

        content = response.choices[0].message.content
        if not content:
            raise ValueError("модель вернула пустой ответ")
        try:
            parsed = json.loads(content)
            return _normalize_model_output(parsed)
        except json.JSONDecodeError as exc:
            raise ValueError(f"модель вернула невалидный JSON: {exc}") from exc


# Обратная совместимость со старым именем.
OpenAiRhymeClient = RhymeLlmClient
