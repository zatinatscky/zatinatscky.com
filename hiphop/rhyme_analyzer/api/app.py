"""FastAPI-приложение: веб-форма + анализ рифм + журнал разборов."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..block_limits import ALLOWED_KINDS, BlockLimits
from ..cost_estimate import estimate_analysis_cost, estimate_dual_analysis_cost
from ..db.activity import ActivityRecorder
from ..db.config import database_enabled
from ..db.context import request_id_var, session_id_var
from ..db.init_db import init_db
from ..db.middleware import DatabaseMiddleware
from ..db.repository import attach_run_to_request, record_user_events
from ..db.session import session_scope
from ..from_blocks import BlockSubmission, validate_submission
from ..journal_store import (
    begin_run,
    delete_entry,
    entry_to_api,
    find_by_text,
    get_entry,
    list_entries,
    load_input_snapshot,
    load_report_data,
    mark_run_failed,
    rename_entry,
    report_path,
    save_run,
)
from ..llm.config import (
    LLM_MODELS,
    PROVIDER_LABELS,
    effective_default_model,
    is_model_available,
    model_provider,
)
from ..pipeline import _load_dotenv, analyze_blocks
from ..progress import ProgressReporter
from ..spec_validate import ValidationFailed
from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    BlockPayload,
    ErrorResponse,
    JournalDeleteResponse,
    JournalEntryResponse,
    JournalInputResponse,
    JournalListResponse,
    JournalMatchRequest,
    JournalMatchResponse,
    JournalRenameRequest,
    JournalRenameResponse,
    JournalRerunRequest,
    EstimateRequest,
    EstimateResponse,
    CostBreakdownItem,
    LimitsResponse,
    ModelInfo,
    ModelsResponse,
    UserEventsRequest,
    UserEventsResponse,
)

ROOT = Path(__file__).resolve().parent.parent.parent
WEB_DIR = ROOT / "web"

app = FastAPI(
    title="Rhyme Analyzer",
    description="Фонетический разбор рифм: ввод блоками → HTML-отчёт",
    version="0.6.0",
)

if database_enabled():
    app.add_middleware(DatabaseMiddleware)

if (WEB_DIR / "static").is_dir():
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


@app.on_event("startup")
def _on_startup() -> None:
    """Подхватываем .env и создаём таблицы БД."""
    _load_dotenv()
    if database_enabled():
        init_db()


@app.get("/health")
def health() -> dict[str, Any]:
    """Проверка живости для Docker / Caddy (как у IVAN)."""
    return {"status": "ok", "service": "rhyme-analyzer", "db": database_enabled()}


def _http_error(status: int, *, kind: str, errors: list[str]) -> HTTPException:
    return HTTPException(status_code=status, detail={"ok": False, "kind": kind, "errors": errors})


def _parse_submissions(req: AnalyzeRequest) -> list[BlockSubmission]:
    submissions = [
        BlockSubmission(kind=b.kind, text=b.text, title=b.title) for b in req.blocks
    ]
    return [s for s in submissions if s.text.strip()]


def _submissions_from_blocks(blocks: list) -> list[BlockSubmission]:
    return [
        BlockSubmission(kind=b.kind, text=b.text, title=b.title)
        for b in blocks
        if b.text.strip()
    ]


def _resolve_model(model: str | None, *, require_key: bool = True) -> str:
    chosen = (model or effective_default_model()).strip()
    if chosen not in LLM_MODELS:
        allowed = ", ".join(LLM_MODELS)
        raise ValueError(f"неизвестная модель «{chosen}» (допустимо: {allowed})")
    if require_key and not is_model_available(chosen):
        prov = model_provider(chosen)
        env_key = {"openai": "OPENAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}[prov]
        label = PROVIDER_LABELS[prov]
        raise ValueError(
            f"для модели «{chosen}» ({label}) задайте {env_key} в .env"
        )
    return chosen


def _resolve_dual_secondary(req: AnalyzeRequest, primary: str) -> str | None:
    """Вторая модель для dual_mode или None."""
    if not req.dual_model:
        return None
    if not req.model_secondary or not req.model_secondary.strip():
        raise ValueError("в режиме двух моделей укажите model_secondary")
    secondary = _resolve_model(req.model_secondary)
    if secondary == primary:
        raise ValueError("вторая модель должна отличаться от первой")
    return secondary


def _estimate_for_request(req: EstimateRequest, submissions: list[BlockSubmission]):
    """Оценка стоимости: одна или две модели."""
    primary = _resolve_model(req.model, require_key=False)
    if req.dual_model and req.model_secondary:
        secondary = _resolve_model(req.model_secondary, require_key=False)
        if secondary != primary:
            return estimate_dual_analysis_cost(
                submissions,
                model_primary=primary,
                model_secondary=secondary,
                lang=req.lang,
            )
    return estimate_analysis_cost(submissions, model=primary, lang=req.lang)


def _persist_journal(
    req: AnalyzeRequest,
    submissions: list[BlockSubmission],
    report: dict[str, Any],
    meta: dict[str, Any],
    *,
    session_id: str | None = None,
    run_id: str | None = None,
    parent_run_id: str | None = None,
    source: str = "web-form",
    duration_ms: int | None = None,
) -> dict[str, Any]:
    """Сохраняет прогон в журнал (БД или файлы) и возвращает данные для API."""
    model_secondary = None
    if req.dual_model and req.model_secondary:
        model_secondary = req.model_secondary.strip()

    entry = save_run(
        song=req.song,
        lang=req.lang,
        blocks=submissions,
        report=report,
        meta=meta,
        session_id=session_id,
        run_id=run_id,
        parent_run_id=parent_run_id,
        source=source,
        dual_mode=req.dual_model,
        model_secondary=model_secondary,
        duration_ms=duration_ms,
    )

    if database_enabled() and run_id and request_id_var.get():
        with session_scope() as db:
            attach_run_to_request(db, request_id_var.get(), run_id)

    return entry_to_api(entry)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.post("/api/events", response_model=UserEventsResponse)
def track_events(req: UserEventsRequest) -> UserEventsResponse:
    """Продуктовая аналитика: действия пользователя в UI."""
    if not database_enabled():
        return UserEventsResponse(recorded=0)

    with session_scope() as db:
        count = record_user_events(
            db,
            session_id=session_id_var.get(),
            events=[e.model_dump() for e in req.events],
        )
    return UserEventsResponse(recorded=count)


@app.get("/api/limits", response_model=LimitsResponse)
def get_limits() -> LimitsResponse:
    lim = BlockLimits()
    return LimitsResponse(
        max_blocks=lim.max_blocks,
        max_lines=lim.max_lines,
        max_words=lim.max_words,
        max_chars=lim.max_chars,
        allowed_kinds=sorted(ALLOWED_KINDS),
    )


@app.get("/api/models", response_model=ModelsResponse)
def get_models() -> ModelsResponse:
    default = effective_default_model()
    models: list[ModelInfo] = []
    for name, desc in LLM_MODELS.items():
        prov = model_provider(name)
        models.append(
            ModelInfo(
                id=name,
                description=desc,
                provider=prov,
                provider_label=PROVIDER_LABELS[prov],
                is_default=(name == default),
                available=is_model_available(name),
            )
        )
    return ModelsResponse(default=default, models=models)


@app.post("/api/estimate", response_model=EstimateResponse)
def estimate_cost(req: EstimateRequest) -> EstimateResponse:
    """Примерная стоимость LLM-анализа до нажатия кнопки."""
    submissions = _submissions_from_blocks(req.blocks)
    if not submissions:
        model = _resolve_model(req.model, require_key=False)
        empty = estimate_analysis_cost([], model=model, lang=req.lang)
        return EstimateResponse(
            model=empty.model,
            api_calls=0,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            cost_usd_label="—",
            input_cost_usd=0.0,
            output_cost_usd=0.0,
            pricing_input_per_1m=empty.pricing_input_per_1m,
            pricing_output_per_1m=empty.pricing_output_per_1m,
            breakdown=[CostBreakdownItem(title="Текст", detail="Заполните блок, чтобы увидеть оценку.")],
        )

    try:
        est = _estimate_for_request(req, submissions)
    except ValueError as exc:
        raise _http_error(400, kind="input", errors=[str(exc)]) from exc

    return EstimateResponse(
        model=est.model,
        api_calls=est.api_calls,
        input_tokens=est.input_tokens,
        output_tokens=est.output_tokens,
        total_tokens=est.total_tokens,
        cost_usd=est.cost_usd,
        cost_usd_label=est.cost_usd_label,
        input_cost_usd=est.input_cost_usd,
        output_cost_usd=est.output_cost_usd,
        pricing_input_per_1m=est.pricing_input_per_1m,
        pricing_output_per_1m=est.pricing_output_per_1m,
        breakdown=[CostBreakdownItem(**item) for item in est.breakdown],
    )


@app.get("/api/journal", response_model=JournalListResponse)
def journal_list(limit: int = 50) -> JournalListResponse:
    """Локальный журнал сохранённых разборов (новые сверху)."""
    entries = list_entries(limit=min(limit, 200))
    api_entries = [JournalEntryResponse(**entry_to_api(e)) for e in entries]
    return JournalListResponse(entries=api_entries, total=len(api_entries))


@app.post("/api/journal/match", response_model=JournalMatchResponse)
def journal_match(req: JournalMatchRequest) -> JournalMatchResponse:
    """Ищет в журнале разборы с тем же текстом (по хешу)."""
    submissions = _submissions_from_blocks(req.blocks)
    if not submissions:
        return JournalMatchResponse(text_hash=None, matches=[])
    from ..journal import normalize_input_text, text_hash

    th = text_hash(normalize_input_text(submissions))
    matches = [JournalEntryResponse(**entry_to_api(e)) for e in find_by_text(submissions)]
    return JournalMatchResponse(text_hash=th, matches=matches)


@app.delete("/api/journal/{entry_id}", response_model=JournalDeleteResponse)
def journal_delete(entry_id: str) -> JournalDeleteResponse:
    """Удаляет запись журнала и связанные файлы на диске."""
    if not delete_entry(entry_id):
        raise HTTPException(status_code=404, detail="запись не найдена")
    return JournalDeleteResponse(id=entry_id)


@app.patch("/api/journal/{entry_id}", response_model=JournalRenameResponse)
def journal_rename(entry_id: str, req: JournalRenameRequest) -> JournalRenameResponse:
    """Переименовывает запись журнала (отображаемое название песни)."""
    entry = rename_entry(entry_id, req.song)
    if entry is None:
        raise HTTPException(status_code=404, detail="запись не найдена")
    return JournalRenameResponse(entry=JournalEntryResponse(**entry_to_api(entry)))


@app.get("/api/journal/{entry_id}/input", response_model=JournalInputResponse)
def journal_input(entry_id: str) -> JournalInputResponse:
    """Снимок входа: текст, блоки и параметры для повторного прогона."""
    snapshot = load_input_snapshot(entry_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="снимок входа не найден")
    return JournalInputResponse(
        entry_id=snapshot["entry_id"],
        song=snapshot["song"],
        lang=snapshot["lang"],
        model=snapshot["model"],
        blocks=snapshot["blocks"],
    )


def _analyze_request_from_journal(entry_id: str, req: JournalRerunRequest) -> AnalyzeRequest:
    """Собирает AnalyzeRequest из снимка журнала и опций повтора."""
    snapshot = load_input_snapshot(entry_id)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "kind": "input", "errors": ["снимок входа не найден"]},
        )

    model = (req.model or "").strip() or snapshot.get("model") or None
    blocks = [
        BlockPayload(kind=b["kind"], text=b["text"], title=b.get("title"))
        for b in snapshot["blocks"]
        if isinstance(b, dict) and str(b.get("text", "")).strip()
    ]
    if not blocks:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "kind": "input", "errors": ["в снимке нет блоков текста"]},
        )

    return AnalyzeRequest(
        song=snapshot["song"],
        lang=snapshot.get("lang", "ru"),
        model=model,
        blocks=blocks,
    )


def _sse_analysis_stream(req: AnalyzeRequest) -> StreamingResponse:
    """Общий SSE-поток анализа для формы и повтора из журнала."""

    async def event_generator():
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        thread = threading.Thread(
            target=_run_analysis,
            args=(req, queue, loop),
            kwargs={
                "session_id": session_id_var.get(),
                "request_id": request_id_var.get(),
            },
            daemon=True,
        )
        thread.start()

        while True:
            kind, payload = await queue.get()
            event = {"type": kind, **payload}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if kind in ("done", "error"):
                break
        thread.join(timeout=1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/journal/{entry_id}/rerun/stream")
async def journal_rerun_stream(entry_id: str, req: JournalRerunRequest) -> StreamingResponse:
    """Повторный прогон: тот же текст и разбиение на блоки, новая запись в журнале."""
    analyze_req = _analyze_request_from_journal(entry_id, req)

    async def event_generator():
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        thread = threading.Thread(
            target=_run_analysis,
            args=(analyze_req, queue, loop),
            kwargs={
                "session_id": session_id_var.get(),
                "request_id": request_id_var.get(),
                "parent_run_id": entry_id.strip().lower(),
                "source": "rerun",
            },
            daemon=True,
        )
        thread.start()

        while True:
            kind, payload = await queue.get()
            event = {"type": kind, **payload}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if kind in ("done", "error"):
                break
        thread.join(timeout=1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/journal/{entry_id}/data")
def journal_data(entry_id: str) -> dict[str, Any]:
    """JSON-отчёт для рендера на фронтенде."""
    entry = get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="запись не найдена")
    try:
        return load_report_data(entry)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/journal/{entry_id}/export.html")
def journal_export_html(entry_id: str) -> HTMLResponse:
    """Страница отчёта для новой вкладки: тот же JS-рендер, что и в превью."""
    from ..export_shell import generate_export_shell

    entry = get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="запись не найдена")
    try:
        data = load_report_data(entry)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return HTMLResponse(generate_export_shell(data))


@app.get("/api/journal/{entry_id}/report")
def journal_report(entry_id: str) -> FileResponse:
    """Legacy: статический HTML (старые записи файлового журнала)."""
    entry = get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="запись не найдена")
    if database_enabled() and entry.report.startswith("db://"):
        raise HTTPException(
            status_code=404,
            detail="отчёт в БД — используйте /api/journal/{id}/export.html",
        )
    try:
        path = report_path(entry)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="файл отчёта не найден")
    return FileResponse(path, media_type="text/html; charset=utf-8", filename=path.name)


def _run_analysis(
    req: AnalyzeRequest,
    queue: asyncio.Queue[tuple[str, dict[str, Any]]],
    loop: asyncio.AbstractEventLoop,
    *,
    session_id: str | None = None,
    request_id: str | None = None,
    parent_run_id: str | None = None,
    source: str = "web-form",
) -> None:
    started = time.perf_counter()
    run_id: str | None = None
    recorder: ActivityRecorder | None = None

    def on_progress(event: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ("progress", event))
        if recorder:
            recorder.on_progress(event)

    submissions = _parse_submissions(req)
    validation_errors = validate_submission(submissions)
    if validation_errors:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            ("error", {"kind": "input", "errors": validation_errors}),
        )
        return

    try:
        model = _resolve_model(req.model)
        model_secondary = _resolve_dual_secondary(req, model)

        if database_enabled():
            run_id = begin_run(
                song=req.song,
                lang=req.lang,
                blocks=submissions,
                model=model,
                session_id=session_id,
                parent_run_id=parent_run_id,
                source=source,
                dual_mode=req.dual_model,
                model_secondary=model_secondary,
            )
            recorder = ActivityRecorder(
                analysis_run_id=run_id,
                session_id=session_id,
                request_id=request_id,
            )

        reporter = ProgressReporter(on_progress)
        report, meta = analyze_blocks(
            song=req.song,
            blocks=submissions,
            lang=req.lang,
            model=model,
            model_secondary=model_secondary,
            reporter=reporter,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        journal = _persist_journal(
            req,
            submissions,
            report,
            meta,
            session_id=session_id,
            run_id=run_id,
            parent_run_id=parent_run_id,
            source=source,
            duration_ms=duration_ms,
        )
        loop.call_soon_threadsafe(
            queue.put_nowait,
            ("done", {"report": report, "meta": meta, "journal": journal}),
        )
    except ValidationFailed as exc:
        _handle_analysis_error(
            loop, queue, run_id, started, "llm_validation", exc.errors
        )
    except EnvironmentError as exc:
        _handle_analysis_error(loop, queue, run_id, started, "config", [str(exc)])
    except ValueError as exc:
        _handle_analysis_error(loop, queue, run_id, started, "input", [str(exc)])
    except Exception as exc:
        _handle_analysis_error(loop, queue, run_id, started, "server", [str(exc)])


def _handle_analysis_error(
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue[tuple[str, dict[str, Any]]],
    run_id: str | None,
    started: float,
    kind: str,
    errors: list[str],
) -> None:
    if run_id:
        mark_run_failed(
            run_id=run_id,
            error_kind=kind,
            errors=errors,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    loop.call_soon_threadsafe(
        queue.put_nowait,
        ("error", {"kind": kind, "errors": errors}),
    )


@app.post("/api/analyze/stream")
async def analyze_stream(req: AnalyzeRequest) -> StreamingResponse:
    return _sse_analysis_stream(req)


@app.post(
    "/api/analyze",
    response_model=AnalyzeResponse,
    responses={
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    submissions = _parse_submissions(req)
    validation_errors = validate_submission(submissions)
    if validation_errors:
        raise _http_error(400, kind="input", errors=validation_errors)

    try:
        model = _resolve_model(req.model)
        model_secondary = _resolve_dual_secondary(req, model)
        report, meta = analyze_blocks(
            song=req.song,
            blocks=submissions,
            lang=req.lang,
            model=model,
            model_secondary=model_secondary,
        )
        journal = _persist_journal(
            req,
            submissions,
            report,
            meta,
            session_id=session_id_var.get(),
            source="web-form",
        )
        meta = {**meta, "journal": journal}
    except ValidationFailed as exc:
        raise _http_error(422, kind="llm_validation", errors=exc.errors) from exc
    except EnvironmentError as exc:
        raise _http_error(503, kind="config", errors=[str(exc)]) from exc
    except ValueError as exc:
        raise _http_error(400, kind="input", errors=[str(exc)]) from exc
    except Exception as exc:
        raise _http_error(500, kind="server", errors=[str(exc)]) from exc

    return AnalyzeResponse(report=report, meta=meta)
