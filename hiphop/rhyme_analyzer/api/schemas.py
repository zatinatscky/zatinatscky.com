"""Pydantic-схемы запросов и ответов HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BlockPayload(BaseModel):
    """Один блок текста из формы."""

    kind: str = Field(..., description="verse | chorus | hook")
    text: str = Field(..., description="текст блока (строки через перенос)")
    title: str | None = Field(None, description="опциональный заголовок секции")


class AnalyzeRequest(BaseModel):
    """POST /api/analyze и /api/analyze/stream."""

    song: str = Field(..., min_length=1, max_length=200)
    lang: str = Field("ru", pattern="^(ru|en|es)$")
    model: str | None = Field(None, description="модель LLM; по умолчанию gpt-5.5 или первая с ключом")
    dual_model: bool = Field(False, description="два прогона LLM с объединением рифм")
    model_secondary: str | None = Field(None, description="вторая модель для dual_mode")
    blocks: list[BlockPayload] = Field(..., min_length=1, max_length=5)


class LimitsResponse(BaseModel):
    """GET /api/limits — лимиты для UI."""

    max_blocks: int
    max_lines: int
    max_words: int
    max_chars: int
    allowed_kinds: list[str]


class ModelInfo(BaseModel):
    id: str
    description: str
    provider: str = "openai"
    provider_label: str = "OpenAI"
    is_default: bool = False
    available: bool = True


class ModelsResponse(BaseModel):
    """GET /api/models — список LLM для селекта."""

    default: str
    models: list[ModelInfo]


class JournalEntryResponse(BaseModel):
    """Одна запись журнала."""

    id: str
    song: str
    created_at: str
    created_label: str
    model: str
    lang: str
    blocks: int
    lines: int
    chains: int
    text_hash: str
    text_preview: str
    report: str
    report_format: str = "json"
    data_url: str
    report_url: str
    rerun_url: str = ""
    can_rerun: bool = False


class JournalInputBlock(BaseModel):
    """Блок текста из снимка входа журнала."""

    kind: str
    text: str
    title: str | None = None


class JournalInputResponse(BaseModel):
    """GET /api/journal/{entry_id}/input — данные для повторного прогона."""

    entry_id: str
    song: str
    lang: str
    model: str
    blocks: list[JournalInputBlock]


class JournalRerunRequest(BaseModel):
    """POST /api/journal/{entry_id}/rerun/stream — опции повторного прогона."""

    model: str | None = Field(
        None,
        description="модель LLM; если не задана — из записи журнала",
    )


class JournalListResponse(BaseModel):
    entries: list[JournalEntryResponse]
    total: int


class JournalDeleteResponse(BaseModel):
    """DELETE /api/journal/{entry_id}."""

    ok: bool = True
    id: str


class JournalRenameRequest(BaseModel):
    """PATCH /api/journal/{entry_id} — новое название записи."""

    song: str = Field(..., min_length=1, max_length=200)


class JournalRenameResponse(BaseModel):
    """Ответ после переименования."""

    ok: bool = True
    entry: JournalEntryResponse


class JournalMatchRequest(BaseModel):
    """POST /api/journal/match — поиск прошлых разборов того же текста."""

    blocks: list[BlockPayload] = Field(..., min_length=1, max_length=5)


class JournalMatchResponse(BaseModel):
    text_hash: str | None = None
    matches: list[JournalEntryResponse]


class EstimateRequest(BaseModel):
    """POST /api/estimate — калькулятор стоимости до запуска."""

    lang: str = Field("ru", pattern="^(ru|en|es)$")
    model: str | None = None
    dual_model: bool = False
    model_secondary: str | None = None
    blocks: list[BlockPayload] = Field(..., min_length=1, max_length=5)


class CostBreakdownItem(BaseModel):
    title: str
    detail: str


class EstimateResponse(BaseModel):
    model: str
    api_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    cost_usd_label: str
    input_cost_usd: float
    output_cost_usd: float
    pricing_input_per_1m: float
    pricing_output_per_1m: float
    breakdown: list[CostBreakdownItem]


class AnalyzeResponse(BaseModel):
    """Успешный ответ анализа."""

    ok: bool = True
    report: dict
    meta: dict


class ErrorResponse(BaseModel):
    """Ошибка валидации или пайплайна."""

    ok: bool = False
    kind: str = "unknown"  # input | llm_validation | config | server
    errors: list[str]


class UserEventPayload(BaseModel):
    """Одно событие поведения из UI."""

    event_name: str = Field(..., min_length=1, max_length=64)
    properties: dict | None = None
    page_path: str = Field("/", max_length=256)


class UserEventsRequest(BaseModel):
    """POST /api/events — пакет событий с фронтенда."""

    events: list[UserEventPayload] = Field(..., min_length=1, max_length=50)


class UserEventsResponse(BaseModel):
    ok: bool = True
    recorded: int
