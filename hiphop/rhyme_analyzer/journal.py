"""Локальный журнал разборов: JSON-отчёты + индекс с привязкой к тексту.

Файлы:
  output/journal/index.json      — метаданные всех прогонов
  output/journal/reports/*.json  — структурированные отчёты (UI рендерит на клиенте)
  output/journal/inputs/*.json   — снимок входного текста (для сопоставления)

Старые записи с reports/*.html конвертируются в JSON на лету при просмотре.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .from_blocks import BlockSubmission
from .html_to_report import html_file_to_report
from .paths import slugify

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
JOURNAL_DIR = _PROJECT_ROOT / "output" / "journal"
REPORTS_DIR = JOURNAL_DIR / "reports"
INPUTS_DIR = JOURNAL_DIR / "inputs"
INDEX_PATH = JOURNAL_DIR / "index.json"

_INDEX_LOCK = threading.Lock()
_INDEX_VERSION = 2


@dataclass
class JournalEntry:
    """Одна запись журнала."""

    id: str
    song: str
    created_at: str  # ISO
    model: str
    lang: str
    blocks: int
    lines: int
    chains: int
    text_hash: str
    text_preview: str
    report: str  # reports/….json или legacy reports/….html
    report_format: str = "json"  # json | html


def _ensure_dirs() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    INPUTS_DIR.mkdir(parents=True, exist_ok=True)


def normalize_input_text(blocks: list[BlockSubmission]) -> str:
    parts: list[str] = []
    for block in blocks:
        if not block.text.strip():
            continue
        lines = [ln.strip() for ln in block.text.splitlines() if ln.strip()]
        if lines:
            parts.append("\n".join(lines))
    return "\n\n".join(parts)


def text_hash(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest[:16]


def text_preview(text: str, *, max_len: int = 72) -> str:
    first = ""
    for line in text.splitlines():
        line = line.strip()
        if line:
            first = line
            break
    if len(first) <= max_len:
        return first
    return first[: max_len - 1] + "…"


def _load_index() -> dict[str, Any]:
    _ensure_dirs()
    if not INDEX_PATH.exists():
        return {"version": _INDEX_VERSION, "entries": []}
    data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    if not isinstance(data.get("entries"), list):
        return {"version": _INDEX_VERSION, "entries": []}
    return data


def _save_index(data: dict[str, Any]) -> None:
    _ensure_dirs()
    INDEX_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _infer_format(entry: JournalEntry) -> str:
    if entry.report_format in ("json", "html"):
        return entry.report_format
    return "html" if entry.report.lower().endswith(".html") else "json"


def save_run(
    *,
    song: str,
    lang: str,
    blocks: list[BlockSubmission],
    report: dict[str, Any],
    meta: dict[str, Any],
) -> JournalEntry:
    """Сохраняет JSON-отчёт и добавляет запись в журнал."""
    _ensure_dirs()
    created = datetime.now().astimezone()
    entry_id = secrets.token_hex(4)
    stamp = created.strftime("%Y%m%d-%H%M%S")
    slug = slugify(song)
    report_name = f"{stamp}-{entry_id}-{slug}.json"
    report_rel = f"reports/{report_name}"
    report_path = JOURNAL_DIR / report_rel

    norm_text = normalize_input_text(blocks)
    th = text_hash(norm_text)

    entry = JournalEntry(
        id=entry_id,
        song=song.strip(),
        created_at=created.isoformat(timespec="seconds"),
        model=str(meta.get("model", "")),
        lang=lang,
        blocks=int(meta.get("blocks", 0)),
        lines=int(meta.get("lines", 0)),
        chains=int(meta.get("chains", 0)),
        text_hash=th,
        text_preview=text_preview(norm_text),
        report=report_rel,
        report_format="json",
    )

    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    input_path = INPUTS_DIR / f"{stamp}-{entry_id}.json"
    input_path.write_text(
        json.dumps(
            {
                "id": entry_id,
                "song": entry.song,
                "text_hash": th,
                "normalized_text": norm_text,
                "blocks": [
                    {"kind": b.kind, "title": b.title, "text": b.text}
                    for b in blocks
                    if b.text.strip()
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    with _INDEX_LOCK:
        index = _load_index()
        entries: list[dict] = index.setdefault("entries", [])
        entries.insert(0, asdict(entry))
        index["version"] = _INDEX_VERSION
        _save_index(index)

    return entry


def list_entries(*, limit: int = 100) -> list[JournalEntry]:
    with _INDEX_LOCK:
        index = _load_index()
    result: list[JournalEntry] = []
    for raw in index.get("entries", [])[:limit]:
        if isinstance(raw, dict) and raw.get("id"):
            raw.setdefault("report_format", "html" if str(raw.get("report", "")).endswith(".html") else "json")
            result.append(JournalEntry(**raw))
    return result


def get_entry(entry_id: str) -> JournalEntry | None:
    entry_id = entry_id.strip().lower()
    for e in list_entries(limit=10_000):
        if e.id.lower() == entry_id:
            return e
    return None


def delete_entry(entry_id: str) -> bool:
    """Удаляет запись из индекса и связанные файлы (отчёт, снимок входа).

    Возвращает True, если запись была найдена и снята с индекса.
    """
    entry_id = entry_id.strip().lower()
    with _INDEX_LOCK:
        index = _load_index()
        entries: list[dict] = index.get("entries", [])
        kept: list[dict] = []
        removed: dict | None = None
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            if str(raw.get("id", "")).lower() == entry_id:
                removed = raw
            else:
                kept.append(raw)
        if removed is None:
            return False

        index["entries"] = kept
        _save_index(index)

        # Файлы удаляем после обновления индекса (индекс уже консистентен).
        raw_fmt = removed.get("report_format")
        if raw_fmt not in ("json", "html"):
            raw_fmt = "html" if str(removed.get("report", "")).endswith(".html") else "json"
        removed.setdefault("report_format", raw_fmt)
        try:
            entry = JournalEntry(**removed)
            path = report_path(entry)
            if path.is_file():
                path.unlink()
        except (ValueError, OSError, TypeError):
            pass

        for input_path in INPUTS_DIR.glob(f"*-{entry_id}.json"):
            try:
                if input_path.is_file():
                    input_path.unlink()
            except OSError:
                pass

        return True


def rename_entry(entry_id: str, song: str) -> JournalEntry | None:
    """Переименовывает запись журнала (индекс, снимок входа, JSON-отчёт)."""
    entry_id = entry_id.strip().lower()
    new_song = song.strip()
    if not new_song:
        return None

    with _INDEX_LOCK:
        index = _load_index()
        entries: list[dict] = index.get("entries", [])
        updated_raw: dict | None = None
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            if str(raw.get("id", "")).lower() == entry_id:
                raw["song"] = new_song
                updated_raw = raw
                break
        if updated_raw is None:
            return None
        _save_index(index)

    # Снимок входа — для повторного прогона с новым названием.
    input_path = find_input_path(entry_id)
    if input_path is not None and input_path.is_file():
        try:
            data = json.loads(input_path.read_text(encoding="utf-8"))
            data["song"] = new_song
            input_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    try:
        entry = JournalEntry(**updated_raw)
    except (ValueError, TypeError):
        return None

    # JSON-отчёт — поле song в шапке превью.
    if _infer_format(entry) == "json":
        try:
            path = report_path(entry)
            if path.is_file():
                report = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(report, dict):
                    report["song"] = new_song
                    path.write_text(
                        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            pass

    return entry


def find_input_path(entry_id: str) -> Path | None:
    """Путь к снимку входа (blocks + song) для записи журнала."""
    entry_id = entry_id.strip().lower()
    matches = sorted(INPUTS_DIR.glob(f"*-{entry_id}.json"))
    return matches[0] if matches else None


def has_input_snapshot(entry_id: str) -> bool:
    """Есть ли сохранённый снимок для повторного прогона."""
    path = find_input_path(entry_id)
    return path is not None and path.is_file()


def load_input_snapshot(entry_id: str) -> dict[str, Any] | None:
    """Загружает song, lang, model и blocks для повторного анализа."""
    path = find_input_path(entry_id)
    if path is None or not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    blocks = data.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        return None

    entry = get_entry(entry_id)
    song = str(data.get("song") or (entry.song if entry else "")).strip()
    if not song:
        return None

    return {
        "entry_id": entry_id.strip().lower(),
        "song": song,
        "lang": entry.lang if entry else "ru",
        "model": entry.model if entry else "",
        "blocks": blocks,
    }


def report_path(entry: JournalEntry) -> Path:
    path = (JOURNAL_DIR / entry.report).resolve()
    if not str(path).startswith(str(JOURNAL_DIR.resolve())):
        raise ValueError("недопустимый путь отчёта")
    return path


def load_report_data(entry: JournalEntry) -> dict[str, Any]:
    """Загружает JSON-отчёт; legacy HTML конвертируется на лету."""
    path = report_path(entry)
    if not path.is_file():
        raise FileNotFoundError("файл отчёта не найден")
    if _infer_format(entry) == "json":
        return json.loads(path.read_text(encoding="utf-8"))
    return html_file_to_report(path)


def find_by_text(blocks: list[BlockSubmission]) -> list[JournalEntry]:
    norm = normalize_input_text(blocks)
    if not norm:
        return []
    th = text_hash(norm)
    return [e for e in list_entries() if e.text_hash == th]


def entry_to_api(entry: JournalEntry) -> dict[str, Any]:
    fmt = _infer_format(entry)
    return {
        **asdict(entry),
        "report_format": fmt,
        "data_url": f"/api/journal/{entry.id}/data",
        "report_url": f"/api/journal/{entry.id}/report",
        "rerun_url": f"/api/journal/{entry.id}/rerun/stream",
        "can_rerun": has_input_snapshot(entry.id),
        "created_label": _format_created(entry.created_at),
    }


def _format_created(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.astimezone().strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return iso
