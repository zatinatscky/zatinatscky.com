"""Сервис LLM-анализа: IPA из кода → промпт → блоки (параллельно) → merge."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..models import Block
from ..progress import ProgressReporter
from ..spec_validate import ValidationFailed, require_valid, validate_spec
from .client import RhymeLlmClient
from .config import DEFAULT_MAX_PARALLEL_BLOCKS, DEFAULT_MODEL
from .merge import merge_block_results
from .prompt import build_block_user_prompt


class RhymeLlmService:
    """Оркестратор анализа рифм через OpenAI.

    Требует, чтобы blocks уже прошли normalize + transcribe (IPA заполнен).
    Несколько блоков обрабатываются параллельно (отдельный HTTP-клиент на поток).
  """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        max_retries: int = 2,
        max_parallel: int | None = None,
        reporter: ProgressReporter | None = None,
        llm_base_percent: int = 15,
        llm_span_percent: int = 70,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.max_parallel = max(1, max_parallel or DEFAULT_MAX_PARALLEL_BLOCKS)
        self._api_key = api_key
        self._client = RhymeLlmClient(model=model, api_key=api_key)
        self._reporter = reporter or ProgressReporter()
        self._log_lock = threading.Lock()
        self._blocks_done = 0
        # Доля прогресса, отдаваемая LLM-блокам (настраивается для dual-mode).
        self._llm_base_percent = llm_base_percent
        self._llm_span_percent = llm_span_percent

    def _set_percent(self, percent: int) -> None:
        self._reporter._last_percent = percent  # noqa: SLF001

    def _log(self, line: str) -> None:
        with self._log_lock:
            self._reporter.log_llm(line)

    def _on_block_finished(self, block_index: int, block_total: int, result: dict) -> None:
        """Обновляет прогресс после завершения одного блока."""
        with self._log_lock:
            self._blocks_done += 1
            done = self._blocks_done
            percent = self._llm_base_percent + int(self._llm_span_percent * done / block_total)
            self._set_percent(percent)
        n_chains = len(result.get("chains", []))
        self._log(f"[llm]   блок {block_index + 1}/{block_total} готов → {n_chains} цепочек")

    def analyze(
        self,
        blocks: list[Block],
        *,
        lang: str = "ru",
        title: str = "Фонетический разбор рифм",
    ) -> dict:
        """Анализирует песню по блокам и возвращает объединённый JSON-эталон."""
        if not blocks:
            raise ValueError("нет блоков для анализа")

        total = len(blocks)
        self._blocks_done = 0
        self._log(f"[llm] провайдер: {self._client.provider_label} · ключ: {self._client.masked_key}")
        self._log(f"[llm] модель: {self.model} · блоков: {total} · режим: по блокам + IPA")

        workers = min(self.max_parallel, total)
        if workers > 1:
            self._log(f"[llm] параллельно: до {workers} блоков одновременно")
            block_results = self._analyze_parallel(blocks, lang=lang, workers=workers)
        else:
            block_results = self._analyze_sequential(blocks, lang=lang)

        self._set_percent(88)
        spec = merge_block_results(blocks, block_results, title=title)
        self._log(f"[llm] после слияния: {len(spec.get('chains', []))} цепочек")

        errors = validate_spec(blocks, spec)
        if errors:
            require_valid(blocks, spec)

        return spec

    def _analyze_sequential(self, blocks: list[Block], *, lang: str) -> list[dict]:
        """Один блок за другим (если блок один или max_parallel=1)."""
        total = len(blocks)
        results: list[dict] = []
        for idx, block in enumerate(blocks):
            percent = self._llm_base_percent + int(self._llm_span_percent * idx / total)
            self._set_percent(percent)
            n_lines = len(block.lines)
            self._log(f"[llm] блок {idx + 1}/{total}: «{block.title}» ({n_lines} строк)…")
            result = self._analyze_one_block(
                block,
                blocks,
                lang=lang,
                block_index=idx,
                block_total=total,
                client=self._client,
            )
            results.append(result)
            self._on_block_finished(idx, total, result)
        return results

    def _analyze_parallel(self, blocks: list[Block], *, lang: str, workers: int) -> list[dict]:
        """Параллельный разбор: ThreadPoolExecutor, свой OpenAI-клиент на поток."""
        total = len(blocks)
        results: list[dict | None] = [None] * total
        first_error: BaseException | None = None

        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {
                pool.submit(self._analyze_block_task, idx, blocks, lang, total): idx
                for idx in range(total)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    results[idx] = future.result()
                    self._on_block_finished(idx, total, results[idx])
                except BaseException as exc:
                    if first_error is None:
                        first_error = exc
                    for pending in future_map:
                        pending.cancel()

        if first_error is not None:
            raise first_error

        return [r for r in results if r is not None]

    def _analyze_block_task(
        self,
        block_index: int,
        all_blocks: list[Block],
        lang: str,
        block_total: int,
    ) -> dict:
        """Задача для пула потоков: отдельный клиент OpenAI на блок."""
        block = all_blocks[block_index]
        n_lines = len(block.lines)
        self._log(f"[llm] блок {block_index + 1}/{block_total}: «{block.title}» ({n_lines} строк)…")
        # Отдельный клиент — потокобезопасность HTTP-сессии.
        client = RhymeLlmClient(model=self.model, api_key=self._api_key)
        return self._analyze_one_block(
            block,
            all_blocks,
            lang=lang,
            block_index=block_index,
            block_total=block_total,
            client=client,
        )

    def _analyze_one_block(
        self,
        block: Block,
        all_blocks: list[Block],
        *,
        lang: str,
        block_index: int,
        block_total: int,
        client: RhymeLlmClient,
    ) -> dict:
        """Один блок с retry при ошибках валидации."""
        validation_errors: list[str] | None = None
        title = block.title

        for attempt in range(self.max_retries + 1):
            prompt = build_block_user_prompt(
                block,
                lang=lang,
                block_index=block_index,
                block_total=block_total,
                validation_errors=validation_errors,
            )
            result = client.analyze_block(model=self.model, user_prompt=prompt)

            partial = {"title": block.title, "chains": result.get("chains", [])}
            errors = validate_spec(all_blocks, partial)
            if not errors:
                return result

            validation_errors = errors
            if attempt < self.max_retries:
                self._log(
                    f"[llm]   «{title}»: валидация {len(errors)} ошибок, "
                    f"повтор {attempt + 2}/{self.max_retries + 1}…"
                )
                for err in errors[:5]:
                    self._log(f"[llm]     • {err}")
                if len(errors) > 5:
                    self._log(f"[llm]     … и ещё {len(errors) - 5}")

        self._log(f"[llm]   блок «{title}»: валидация не пройдена после {self.max_retries + 1} попыток")
        for err in validation_errors or []:
            self._log(f"[llm]     • {err}")
        raise ValidationFailed(validation_errors or ["неизвестная ошибка валидации"])
