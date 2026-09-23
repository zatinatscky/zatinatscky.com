"""Импорт файлового output/journal/ в PostgreSQL / SQLite."""

from __future__ import annotations

import json
from pathlib import Path

from ..journal import INDEX_PATH, JOURNAL_DIR, INPUTS_DIR, JournalEntry
from .init_db import init_db
from .journal_db import save_run
from .repository import get_run
from .session import session_scope
from ..from_blocks import BlockSubmission


def _load_index() -> list[dict]:
    if not INDEX_PATH.is_file():
        return []
    data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return data.get("entries") or []


def _load_blocks_from_input(entry_id: str) -> list[BlockSubmission] | None:
    matches = sorted(INPUTS_DIR.glob(f"*-{entry_id}.json"))
    if not matches:
        return None
    data = json.loads(matches[0].read_text(encoding="utf-8"))
    blocks_raw = data.get("blocks")
    if not isinstance(blocks_raw, list):
        return None
    blocks = [
        BlockSubmission(kind=str(b["kind"]), text=str(b["text"]), title=b.get("title"))
        for b in blocks_raw
        if isinstance(b, dict) and str(b.get("text", "")).strip()
    ]
    return blocks or None


def _load_report(entry: JournalEntry) -> dict | None:
    path = JOURNAL_DIR / entry.report
    if not path.is_file():
        return None
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def migrate(*, dry_run: bool = False) -> dict[str, int]:
    """Переносит записи из output/journal/ в БД. Пропускает уже импортированные id."""
    init_db()
    stats = {"total": 0, "imported": 0, "skipped": 0, "failed": 0}

    for raw in _load_index():
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        stats["total"] += 1
        entry_id = str(raw["id"]).lower()

        with session_scope() as db:
            if get_run(db, entry_id):
                stats["skipped"] += 1
                continue

        if dry_run:
            stats["imported"] += 1
            continue

        try:
            entry = JournalEntry(**{**raw, "report_format": raw.get("report_format", "json")})
            blocks = _load_blocks_from_input(entry_id)
            if not blocks:
                stats["failed"] += 1
                continue
            report = _load_report(entry)
            if not report:
                stats["failed"] += 1
                continue

            meta = report.get("meta") if isinstance(report.get("meta"), dict) else {}
            meta = {
                **meta,
                "model": entry.model,
                "blocks": entry.blocks,
                "lines": entry.lines,
                "chains": entry.chains,
            }

            save_run(
                song=entry.song,
                lang=entry.lang,
                blocks=blocks,
                report=report,
                meta=meta,
                run_id=entry_id,
                source="import",
            )
            stats["imported"] += 1
        except Exception:
            stats["failed"] += 1

    return stats


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Импорт output/journal/ → БД")
    parser.add_argument("--dry-run", action="store_true", help="только подсчёт, без записи")
    args = parser.parse_args()
    result = migrate(dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
