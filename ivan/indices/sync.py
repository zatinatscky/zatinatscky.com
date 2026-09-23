"""
Ежедневная синхронизация рядов индексов.

Запуск:
    python -m indices.sync              # все индексы
    python -m indices.sync vix spx      # только указанные
    python -m indices.sync --report     # без загрузки, только состояние БД

Тот же sync_all() вызывается из app.py по расписанию (эндпоинт /jobs/indexes-sync)
и systemd-таймером на VPS (deploy/fng-sync.sh).

Главное свойство: каждый индекс синхронизируется независимо. Падение одного
источника не отменяет остальные, ошибка пишется в index_meta.last_error, а джоб
завершается успешно, если хотя бы часть индексов обновилась. Иначе один
недоступный сторонний API ломал бы всю ежедневную выгрузку.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

from sqlalchemy.engine import Engine

from . import sources, volumes
from .registry import SPECS, IndexSpec
from .store import (
    coverage,
    init_db,
    load_sync_status,
    mark_sync,
    upsert_meta,
    upsert_points,
)

_log = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Итог синхронизации одного индекса."""

    index_id: str
    ok: bool
    points: int = 0
    last_day: str | None = None
    error: str | None = None
    # Сколько точек ряда получили сопоставленный объём (0, если у индекса его нет).
    volume_points: int = 0


def sync_one(engine: Engine, spec: IndexSpec) -> SyncResult:
    """Тянет ряд одного индекса вместе с объёмом его рынка и пишет в БД."""
    _log.info("[%s] синхронизация через %s…", spec.id, spec.fetcher)
    try:
        points = sources.fetch(spec.fetcher, spec.params)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        _log.error("[%s] источник недоступен: %s", spec.id, message)
        mark_sync(engine, spec.id, error=message, point_count=0)
        return SyncResult(spec.id, ok=False, error=message)

    # Объём — по рынку, который описывает индекс (см. volumes.py). Отсутствие или
    # сбой объёма не должны терять сам ряд: это дополнительный слой на графике.
    volume_by_day: dict[str, float] = {}
    if spec.volume_market:
        try:
            volume_by_day = dict(volumes.series_for(spec.volume_market))
        except Exception as exc:
            _log.warning("[%s] объём рынка %s недоступен: %s", spec.id, spec.volume_market, exc)

    written = upsert_points(engine, spec.id, points, volumes=volume_by_day)
    last_day = points[-1][0] if points else None
    matched = sum(1 for d, _ in points if d in volume_by_day) if volume_by_day else 0
    mark_sync(engine, spec.id, error=None, point_count=written, last_observation=last_day)
    _log.info(
        "[%s] записано %s точек (последняя %s), с объёмом %s",
        spec.id,
        written,
        last_day,
        matched if spec.volume_market else "—",
    )
    return SyncResult(spec.id, ok=True, points=written, last_day=last_day, volume_points=matched)


def sync_all(engine: Engine, only: list[str] | None = None) -> list[SyncResult]:
    """
    Синхронизирует все индексы (или подмножество по id).

    Перед загрузкой обновляет справочник index_meta из registry.py, чтобы правки
    названий и описаний доезжали до БД без отдельной миграции.
    """
    init_db(engine)
    upsert_meta(engine)
    # Один рынок обслуживает несколько индексов, поэтому объёмы кэшируются на
    # прогон; сбрасываем кэш на входе, чтобы повторный вызов брал свежие данные.
    volumes.reset_cache()

    specs = [s for s in SPECS if not only or s.id in set(only)]
    if only:
        unknown = set(only) - {s.id for s in SPECS}
        if unknown:
            _log.warning("Неизвестные id индексов пропущены: %s", ", ".join(sorted(unknown)))

    results = [sync_one(engine, spec) for spec in specs]

    ok = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]
    _log.info(
        "Синхронизация завершена: успешно %s из %s%s",
        len(ok),
        len(results),
        f"; с ошибкой: {', '.join(r.index_id for r in failed)}" if failed else "",
    )
    return results


def print_report(engine: Engine) -> None:
    """Печатает покрытие, объём и состояние последней синхронизации по индексам."""
    cov = {row[0]: row for row in coverage(engine)}
    status = load_sync_status(engine)

    header = f"\n{'индекс':<12} {'точек':>7}  {'первая':<12} {'последняя':<12} {'объём':<16} состояние"
    print(header)
    print("-" * len(header))
    for spec in SPECS:
        row = cov.get(spec.id)
        st = status.get(spec.id) or {}
        err = st.get("last_error")
        # row[4] — сколько строк ряда имеют непустой volume.
        vol = f"{row[4]} точек" if row and row[4] else ("—" if not spec.volume_market else "НЕТ")
        if spec.volume_market and row and row[4]:
            vol = f"{spec.volume_market} {row[4]}"
        if row:
            state = "OK" if not err else f"ОШИБКА: {str(err)[:30]}"
            print(f"{spec.id:<12} {row[1]:>7}  {row[2]:<12} {row[3]:<12} {vol:<16} {state}")
        else:
            print(
                f"{spec.id:<12} {0:>7}  {'—':<12} {'—':<12} {'—':<16} "
                f"НЕТ ДАННЫХ: {str(err or '')[:28]}"
            )
    print()


def main(argv: list[str]) -> int:
    """CLI: разбор аргументов и запуск синхронизации."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Импорт здесь: fng_data тянет pandas, а для --report он не нужен.
    from fng_data import get_engine

    engine = get_engine()

    args = [a for a in argv if not a.startswith("-")]
    if "--report" in argv:
        print_report(engine)
        return 0

    results = sync_all(engine, only=args or None)
    print_report(engine)

    # Ненулевой код только если не обновился ни один индекс: частичный успех для
    # ежедневного джоба — нормальная ситуация, ошибки видны в отчёте и в БД.
    return 0 if any(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
