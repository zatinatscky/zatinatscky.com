"""CLI: связывает весь пайплайн и пишет готовый .canvas.tsx.

Пример:
    python -m rhyme_analyzer text.txt --out output/rhymes.canvas.tsx --title "MEZZA"
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import annotate as annotate_mod
from . import canvas_gen, cleaning, html_gen, llm_analyze, rhymes
from .normalize import Normalizer
from .paths import default_html_output, slugify
from .phonetics import get_transcriber, transcribe_blocks


def _load_dotenv() -> None:
    """Подхватывает OPENAI_API_KEY из .env в корне проекта (если установлен python-dotenv)."""
    try:
        from dotenv import load_dotenv

        # Ищем .env рядом с проектом (на уровень выше пакета rhyme_analyzer).
        env_path = Path(__file__).resolve().parent.parent / ".env"
        # override=True: .env важнее случайного export OPENAI_API_KEY=sk-... из README.
        load_dotenv(env_path, override=True)
    except ImportError:
        pass


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rhyme_analyzer",
        description="Фонетический разбор рифм: текст -> Canvas (.canvas.tsx).",
    )
    p.add_argument("input", type=Path, nargs="?", default=None, help="входной .txt с текстом песни")
    p.add_argument(
        "-s",
        "--song",
        default=None,
        metavar="TITLE",
        help='название песни (заголовок отчёта и имя файла: output/<slug>-YYYYMMDD-HHMMSS.html)',
    )
    p.add_argument("-o", "--out", type=Path, default=None, help="куда писать результат (по умолчанию output/<slug>-timestamp.html)")
    p.add_argument("-f", "--format", choices=["html", "canvas"], default=None,
                   help="формат вывода: html (по умолчанию) или canvas (.canvas.tsx). Если не задан — определяется по расширению --out")
    p.add_argument(
        "-t",
        "--title",
        default=None,
        help="(устар.) то же, что --song; если задан вместе с --song — игнорируется",
    )
    p.add_argument("-a", "--annotate", type=Path, default=None,
                   help="JSON-эталон разметки рифм: дословно воспроизводит ручной разбор")
    p.add_argument("--llm", action="store_true",
                   help="анализ рифм через LLM (OpenAI или DeepSeek; ключи в .env)")
    p.add_argument("-m", "--llm-model", default=llm_analyze.DEFAULT_MODEL, metavar="MODEL",
                   help=f"модель для --llm (по умолчанию {llm_analyze.DEFAULT_MODEL}). "
                        f"См. --list-models")
    p.add_argument("--list-models", action="store_true",
                   help="показать рекомендуемые модели (OpenAI + DeepSeek) и выйти")
    p.add_argument("--save-spec", type=Path, default=None,
                   help="сохранить JSON-эталон от LLM в файл (кэш/отладка)")
    p.add_argument("--load-spec", type=Path, default=None,
                   help="взять готовый JSON-эталон вместо вызова API (если файл существует)")
    p.add_argument("-l", "--lang", default="ru", help="язык песни и G2P (espeak): ru, en, es")
    p.add_argument("--fallback", action="store_true", help="принудительно использовать приблизительный режим (без espeak)")
    p.add_argument("--window", type=int, default=None, help="окно поиска рифм по строкам (по умолчанию 3)")
    p.add_argument("--threshold", type=float, default=None, help="порог похожести хвостов 0..1 (по умолчанию 0.6)")
    p.add_argument("--no-versioned-name", action="store_true",
                   help="не добавлять дату-время в имя HTML-файла (только внутри HTML)")
    return p


def _default_output_path(
    song: str,
    input_path: Path,
    fmt: str,
    generated_at: datetime,
    versioned: bool,
) -> Path:
    """Путь вывода по умолчанию: HTML — output/<slug>-timestamp; canvas — рядом с входом."""
    if fmt == "canvas":
        slug = slugify(song)
        return input_path.parent / "output" / f"{slug}.canvas.tsx"
    output_dir = input_path.parent / "output"
    return default_html_output(song, output_dir=output_dir, generated_at=generated_at, versioned=versioned)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = build_parser().parse_args(argv)

    if args.list_models:
        print(llm_analyze.models_help())
        print(f"\nПо умолчанию: {llm_analyze.DEFAULT_MODEL}")
        print('Пример: ./run.sh text.txt -s "MEZZA" --llm -m gpt-5.4')
        return 0

    if args.input is None:
        print("[error] укажите входной .txt и название песни: -s \"Название\"", file=sys.stderr)
        return 1
    if not args.song or not args.song.strip():
        print("[error] обязательный флаг --song / -s (название песни)", file=sys.stderr)
        return 1

    if not args.input.exists():
        print(f"[error] файл не найден: {args.input}", file=sys.stderr)
        return 1

    # Параметры детектора (переопределяем модульные дефолты при необходимости).
    if args.window is not None:
        rhymes._LINE_WINDOW = args.window
    if args.threshold is not None:
        rhymes._RHYME_THRESHOLD = args.threshold

    raw = args.input.read_text(encoding="utf-8")
    # Название песни — обязательный аргумент; --title оставлен для обратной совместимости.
    song = args.song.strip()
    if args.title and args.title.strip() != song:
        print("[warn] --title игнорируется: используйте --song", file=sys.stderr)
    title = song
    generated_at = datetime.now().astimezone()

    # Определяем формат вывода: явный --format > расширение --out > html по умолчанию.
    if args.format is not None:
        fmt = args.format
    elif args.out is not None and str(args.out).endswith(".canvas.tsx"):
        fmt = "canvas"
    elif args.out is not None and args.out.suffix == ".html":
        fmt = "html"
    else:
        fmt = "html"

    # Путь вывода: явный --out; иначе output/<slug>-timestamp по названию песни.
    versioned_name = not args.no_versioned_name
    if args.out is not None:
        out = args.out
    else:
        out = _default_output_path(song, args.input, fmt, generated_at, versioned_name)

    # Режим разметки рифм (для метаданных HTML).
    analysis_mode = "autodetect"
    llm_model: str | None = None

    # 1) Чистка -> блоки.
    blocks = cleaning.clean(raw)
    if not blocks:
        print("[error] после чистки не осталось текста", file=sys.stderr)
        return 1

    # 2) Нормализация + G2P (нужно ДО LLM: IPA уходит в промпт).
    Normalizer().apply(blocks)
    transcriber = get_transcriber(args.lang, force_fallback=args.fallback)
    transcribe_blocks(blocks, transcriber)

    # 3) Источник цепочек: эталон / кэш LLM / OpenAI / автодетектор.
    spec: dict | None = None
    if args.annotate is not None:
        if not args.annotate.exists():
            print(f"[error] эталон не найден: {args.annotate}", file=sys.stderr)
            return 1
        spec = annotate_mod.load_spec(args.annotate)
        analysis_mode = "annotate"
    elif args.load_spec is not None and args.load_spec.exists():
        spec = llm_analyze.load_spec(args.load_spec)
        analysis_mode = "cached"
        llm_model = spec.get("_meta", {}).get("model") or args.llm_model
        print(f"[ok] эталон загружен из кэша: {args.load_spec}")
    elif args.llm:
        llm_model = args.llm_model
        analysis_mode = "llm-blocks"
        spec = llm_analyze.analyze_with_openai(
            blocks,
            lang=args.lang,
            model=llm_model,
            title=title,
        )
        print(f"[ok] LLM ({llm_model}) вернул {len(spec.get('chains', []))} цепочек")
        if args.save_spec is not None:
            spec["_meta"] = {
                "model": llm_model,
                "mode": "per-block+ipa",
                "generated_at": generated_at.isoformat(timespec="seconds"),
                "lang": args.lang,
                "blocks": len(blocks),
            }
            llm_analyze.save_spec(spec, args.save_spec)
            print(f"[ok] эталон сохранён: {args.save_spec}")
    elif args.load_spec is not None:
        print(f"[error] кэш эталона не найден: {args.load_spec}", file=sys.stderr)
        return 1

    # 4) Применяем цепочки.
    if spec is not None:
        chains = annotate_mod.annotate(blocks, spec)
    else:
        chains = rhymes.detect_chains(blocks)

    # 5) Генерация результата в выбранном формате.
    if fmt == "canvas":
        content = canvas_gen.generate(blocks, chains, title=title, source=args.input.name)
    else:
        content = html_gen.generate(
            blocks,
            chains,
            title=title,
            source=args.input.name,
            meta=html_gen.ReportMeta(
                generated_at=generated_at,
                analysis_mode=analysis_mode,
                llm_model=llm_model,
            ),
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")

    n_lines = sum(len(b.lines) for b in blocks)
    print(f"[ok] строк: {n_lines} · блоков: {len(blocks)} · цепочек: {len(chains)}")
    if fmt == "canvas":
        print(f"[ok] Canvas записан: {out}")
        print("     Чтобы он отрисовался в Cursor, файл должен лежать в папке canvases/ проекта.")
    else:
        print(f"[ok] HTML записан: {out}")
        print(f"     Сформировано: {html_gen.format_timestamp(generated_at)}")
        print("     Откройте файл двойным кликом в любом браузере.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
