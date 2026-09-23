# rhyme_analyzer

Автоматический фонетический разбор рифм: на входе — `.txt` с текстом песни,
на выходе — самодостаточный **HTML** (открывается в любом браузере) или
Cursor Canvas (`.canvas.tsx`) — с подсветкой звуковых цепочек, транскрипцией
и метриками.

## Что делает пайплайн

1. **Чистка** — убирает мусор выгрузок Genius («You might also like», `Embed`).
2. **Секции** — распознаёт куплеты, припевы, hook и т.д. на **RU / EN / ES**:
   `[Verse 1]`, `[Припев]`, `[Coro]`, а также отдельные строки `Chorus`, `Hook`, `Куплет 2`.
   Каждая секция — отдельный блок для LLM.
3. **Нормализация** — числа и латиница превращаются в произношение:
   `8 → восемь`, `i8 → айвосемь`, `Porsche → порше`.
4. **G2P → IPA** с ударениями (через `phonemizer` + `espeak-ng`).
5. **Цепочки рифм** — автодетектор, JSON-эталон или OpenAI (по блокам).
6. **Вывод** — HTML (по умолчанию) или Cursor Canvas.

## Установка

```bash
pip install -r requirements.txt
```

Для **точной** транскрипции нужен системный `espeak-ng`:

```bash
# macOS
brew install espeak-ng
# Ubuntu/Debian
sudo apt-get install espeak-ng
```

Без `espeak-ng` пайплайн работает в приблизительном режиме (эвристические ударения).

> **macOS / Apple Silicon:** если `phonemizer` не находит библиотеку:
> ```bash
> export PHONEMIZER_ESPEAK_LIBRARY=/path/to/libespeak-ng.dylib
> ```

## Веб-сервис

Локальный UI с вводом текста **блоками** (куплет / припев / hook), до **5 блоков**:

| Лимит | Значение |
|---|---|
| Блоков | 5 |
| Строк в блоке | 24 |
| Слов в блоке | 200 |
| Символов в блоке | 1000 |

```bash
./run_server.sh
# → http://127.0.0.1:8000
```

Нужен `OPENAI_API_KEY` и/или `DEEPSEEK_API_KEY` в `.env` — в селекте моделей показываются только провайдеры с настроенным ключом. Каждый веб-прогон **автоматически сохраняется** в журнал (БД или `output/journal/`).

### База данных

По умолчанию сервис создаёт **SQLite** в `data/hiphop.db` и хранит:

| Таблица | Назначение |
|---|---|
| `texts` / `text_blocks` | тексты песен (дедуп по хешу) |
| `analysis_runs` | журнал разборов + JSON-отчёты |
| `analysis_requests` | аудит API-запросов |
| `activity_logs` | этапы пайплайна (SSE progress) |
| `user_events` | действия в UI (клики, submit, удаление) |
| `visitor_sessions` | анонимные сессии (cookie `rhyme_sid`) |

**PostgreSQL** (продакшен):

```bash
cp .env.example .env   # DATABASE_URL=postgresql://...
docker compose up -d db
./run_server.sh
```

Импорт старого файлового журнала:

```bash
python -m rhyme_analyzer.db.migrate_journal
python -m rhyme_analyzer.db.migrate_journal --dry-run
```

Отключить БД: `DISABLE_DATABASE=1` в `.env` — вернётся файловый журнал `output/journal/`.

Схема SQL: `schema.sql`. API событий UI: `POST /api/events`.

### Деплой на VPS (рядом с IVAN)

Продакшен: **`https://hiphop.zatinatscky.com`** — через Caddy IVAN.

```bash
# на сервере
cd ~/hiphop
cp .env.example .env && nano .env
chmod +x deploy/setup-vps.sh && ./deploy/setup-vps.sh
```

Подробно: **`DEPLOY_VPS.md`** (DNS, Caddy, бэкапы, обновление).

Модели DeepSeek (`deepseek-v4-pro`, `deepseek-v4-flash`, `deepseek-chat`, `deepseek-reasoner`) используют тот же пайплайн через OpenAI-совместимый API. Для максимального качества выбирайте `deepseek-v4-pro`.

На кнопке «Разобрать рифмы» показывается **примерная стоимость** LLM-анализа; кнопка «?» рядом объясняет, из чего она складывается (объём текста, модель, число запросов).

**Режим двух моделей** (чекбокс в форме): два полных прогона (например `gpt-5.5` + `deepseek-v4-pro`), результаты объединяются — union рифм без дубликатов по наборам слов.

- `GET /api/journal` — список разборов (название, время, превью текста)
- `GET /api/journal/{id}/report` — открыть сохранённый HTML
- `POST /api/journal/match` — найти прошлые разборы с тем же текстом
- `POST /api/analyze/stream` — анализ с прогрессом + сохранение в журнал
- `POST /api/estimate` — оценка стоимости до запуска анализа
- `GET /api/models` — список LLM

## Запуск (CLI)

**Обязательно укажите название песни** (`-s` / `--song`) — оно попадает в заголовок
отчёта и в имя файла по умолчанию: `output/<slug>-YYYYMMDD-HHMMSS.html`.

```bash
cd /Users/ivanzatinatscky/Documents/hiphop

# LLM-разбор (рекомендуется)
./run.sh text.txt -s "MEZZA" --llm --lang ru

# HTML с явным путём
./run.sh text.txt -s "MEZZA" --llm --out output/mezza.html --lang ru

# Без API — автодетектор
./run.sh text.txt -s "MEZZA" --out output/mezza.html
```

Создание venv (один раз):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### LLM-анализ через OpenAI

```bash
# Ключ: .env.example → .env (настоящий OPENAI_API_KEY)
# Если в shell был export OPENAI_API_KEY=sk-... — сбросьте: unset OPENAI_API_KEY

./run.sh --list-models

./run.sh text.txt -s "MEZZA" --llm -m gpt-5.5 \
  --save-spec output/mezza-spec.json \
  --lang ru

# Повтор без API (из кэша)
./run.sh text.txt -s "MEZZA" \
  --load-spec output/mezza-spec.json
```

Сервис `RhymeLlmService`: IPA считает espeak, **блоки анализируются параллельно** (до 5 одновременных запросов к OpenAI); повторяющиеся припевные цепочки дедуплицируются при слиянии.

### JSON-эталон (опционально)

Флаг `--annotate file.json` применяет ручную разметку рифм. Примеры эталонов
кладите в `rhyme_analyzer/annotations/` (по одному JSON на песню).

### Режимы разметки рифм

| Режим | Флаг | Когда |
|---|---|---|
| OpenAI | `--llm` | основной режим для сервиса |
| Кэш LLM | `--load-spec file.json` | повтор без API |
| Ручной эталон | `--annotate file.json` | детерминированная разметка |
| Автодетектор | *(без флагов)* | быстрый черновик |

### Флаги

- **`-s`, `--song`** — название песни (обязательно).
- **`--out`** — путь к выходному файлу (по умолчанию `output/<slug>-timestamp.html`).
- **`--llm`**, **`-m` / `--llm-model`** — OpenAI (по умолчанию `gpt-5.5`).
- **`--save-spec` / `--load-spec`** — кэш JSON-эталона.
- **`--format`** — `html` или `canvas`.
- **`--lang`** — `ru`, `en`, `es`.
- **`--no-versioned-name`** — без штампа времени в имени файла.
- **`--fallback`** — без espeak; **`--window` / `--threshold`** — автодетектор.

> Canvas отрисовывается в Cursor только из папки `canvases/`. HTML — в любом браузере.

## Структура

```
rhyme_analyzer/
  api/             # FastAPI (веб-сервис)
  block_limits.py  # лимиты блоков формы
  cost_estimate.py # оценка стоимости LLM до анализа
  from_blocks.py   # сборка Block из POST
  pipeline.py      # оркестратор для API
  cleaning.py      # чистка и разбивка на блоки
  sections.py      # мультиязычные заголовки секций
  paths.py         # slug и пути выходных файлов
  normalize.py     # числа/латиница (+ lexicon.json)
  phonetics.py     # G2P → IPA
  rhymes.py        # автодетектор рифм
  annotate.py      # применение JSON-эталона
  llm/             # RhymeLlmService
  html_gen.py      # .html
  canvas_gen.py    # .canvas.tsx
  cli.py           # CLI
  annotations/     # JSON-эталоны (по песням)
```

## Ограничения

- Качество IPA зависит от `espeak-ng`.
- LLM требует `OPENAI_API_KEY`; до 2 повторов при ошибках валидации.
- Латиница в IPA — через `lexicon.json` + espeak.
