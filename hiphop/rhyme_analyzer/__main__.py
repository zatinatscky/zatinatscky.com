"""Позволяет запускать пакет как `python -m rhyme_analyzer ...`."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
