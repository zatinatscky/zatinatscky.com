"""Оркестратор анализа: блоки формы → LLM → HTML."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import annotate as annotate_mod
from . import html_gen, llm_analyze
from .from_blocks import BlockSubmission, blocks_from_submission, validate_submission
from .llm.config import DEFAULT_MAX_PARALLEL_BLOCKS, DEFAULT_MODEL
from .chain_cleanup import (
    build_heuristic_spec,
    finalize_chains,
    reconcile_chains,
    split_spec_at_rhyme_boundaries,
)
from .llm.merge import merge_specs_union
from .normalize import Normalizer
from .phonetics import get_transcriber, transcribe_blocks
from .progress import ProgressReporter, humanize_pipeline_stage
from .report_data import build_report
from .yo_restore import YoRestorer


def _load_dotenv() -> None:
    """OPENAI_API_KEY из .env в корне проекта."""
    try:
        from dotenv import load_dotenv

        env_path = Path(__file__).resolve().parent.parent / ".env"
        load_dotenv(env_path, override=True)
    except ImportError:
        pass


def analyze_blocks(
    *,
    song: str,
    blocks: list[BlockSubmission],
    lang: str = "ru",
    model: str | None = None,
    model_secondary: str | None = None,
    force_fallback: bool = False,
    reporter: ProgressReporter | None = None,
) -> tuple[dict, dict]:
    """Полный пайплайн → (report_json, meta)."""
    _load_dotenv()
    rep = reporter or ProgressReporter()

    filled = [b for b in blocks if b.text.strip()]
    errors = validate_submission(filled)
    if errors:
        raise ValueError("; ".join(errors))

    song = song.strip()
    if not song:
        raise ValueError("укажите название песни")

    parsed = blocks_from_submission(filled)
    generated_at = datetime.now().astimezone()
    llm_model = model or DEFAULT_MODEL
    dual_mode = bool(model_secondary and model_secondary.strip() and model_secondary != llm_model)
    n_blocks = len(parsed)

    rep.emit(
        stage="prepare",
        percent=5,
        log="[pipeline] нормализация текста",
        hint=humanize_pipeline_stage("prepare"),
    )
    Normalizer().apply(parsed)
    YoRestorer().apply(parsed, lang=lang)

    rep.emit(
        stage="phonetics",
        percent=12,
        log="[pipeline] транскрипция IPA (espeak)",
        hint=humanize_pipeline_stage("phonetics"),
    )
    transcriber = get_transcriber(lang, force_fallback=force_fallback)
    transcribe_blocks(parsed, transcriber)

    if dual_mode:
        rep.emit(
            stage="llm",
            percent=15,
            log=f"[pipeline] dual LLM: {llm_model} + {model_secondary}, блоков: {n_blocks}",
            hint=f"Два прогона: {llm_model} и {model_secondary}. "
            f"Результаты объединяются (union рифм).",
        )
        spec, dual_stats = llm_analyze.analyze_dual_models(
            parsed,
            lang=lang,
            model_primary=llm_model,
            model_secondary=model_secondary.strip(),
            title=song,
            max_retries=3,
            max_parallel=DEFAULT_MAX_PARALLEL_BLOCKS,
            reporter=rep,
        )
        analysis_mode = "llm-dual"
        llm_model_label = f"{llm_model} + {model_secondary}"
    else:
        rep.emit(
            stage="llm",
            percent=15,
            log=f"[pipeline] запуск LLM ({llm_model}), блоков: {n_blocks}, параллельно до {min(n_blocks, DEFAULT_MAX_PARALLEL_BLOCKS)}",
            hint=f"Запускаем анализ рифм моделью {llm_model}. "
            f"Блоков: {n_blocks}. Несколько секций могут обрабатываться одновременно.",
        )
        spec = llm_analyze.analyze_with_openai(
            parsed,
            lang=lang,
            model=llm_model,
            title=song,
            max_retries=3,
            max_parallel=DEFAULT_MAX_PARALLEL_BLOCKS,
            reporter=rep,
        )
        analysis_mode = "llm-blocks"
        llm_model_label = llm_model
        dual_stats = {}

    rep.emit(
        stage="merge",
        percent=88,
        log="[pipeline] union эвристик + LLM",
        hint="Сливаем фонетические эвристики с разметкой модели для максимального покрытия.",
    )
    heuristic = build_heuristic_spec(parsed, title=song)
    spec, heur_stats = merge_specs_union(spec, heuristic, title=song)
    spec, split_count = split_spec_at_rhyme_boundaries(parsed, spec)
    if split_count:
        heur_stats = {**heur_stats, "chains_split_at_boundary": split_count}
    rep.emit(
        stage="annotate",
        percent=90,
        log=(
            f"[pipeline] эвристик: {heur_stats['chains_heuristic']}, "
            f"после union: {heur_stats['chains_merged']} цепочек "
            f"(+{heur_stats['chains_union_added']} к LLM)"
        ),
        hint=humanize_pipeline_stage("annotate"),
    )
    chains = annotate_mod.annotate(parsed, spec)
    chains = reconcile_chains(parsed, chains, spec)
    chains = finalize_chains(parsed, chains)

    rep.emit(
        stage="render",
        percent=96,
        log="[pipeline] сборка отчёта",
        hint=humanize_pipeline_stage("render"),
    )
    report = build_report(
        parsed,
        chains,
        song=song,
        source="web-form",
        generated_at=generated_at,
        analysis_mode=analysis_mode,
        llm_model=llm_model_label,
        extra_meta={**(dual_stats if dual_stats else {}), **heur_stats},
    )

    meta = {
        "song": song,
        "blocks": n_blocks,
        "lines": sum(len(b.lines) for b in parsed),
        "chains": len(chains),
        "model": llm_model_label,
        "dual_mode": dual_mode,
        "generated_at": generated_at.isoformat(timespec="seconds"),
        **heur_stats,
    }
    if dual_stats:
        meta.update(dual_stats)

    rep.emit(
        stage="done",
        percent=100,
        log="[pipeline] готово",
        hint=humanize_pipeline_stage("done"),
    )
    return report, meta


def analyze_blocks_to_html(
    *,
    song: str,
    blocks: list[BlockSubmission],
    lang: str = "ru",
    model: str | None = None,
    model_secondary: str | None = None,
    force_fallback: bool = False,
    reporter: ProgressReporter | None = None,
) -> tuple[str, dict]:
    """CLI/экспорт: пайплайн + статический HTML."""
    report, meta = analyze_blocks(
        song=song,
        blocks=blocks,
        lang=lang,
        model=model,
        model_secondary=model_secondary,
        force_fallback=force_fallback,
        reporter=reporter,
    )
    from .report_data import parse_report

    parsed_blocks, chains, header = parse_report(report)
    gen_at = datetime.fromisoformat(meta["generated_at"])
    html = html_gen.generate(
        parsed_blocks,
        chains,
        title=song,
        source=header.get("source", "web-form"),
        meta=html_gen.ReportMeta(
            generated_at=gen_at,
            analysis_mode=report["meta"].get("analysis_mode", "llm-blocks"),
            llm_model=report["meta"].get("llm_model"),
        ),
    )
    return html, meta
