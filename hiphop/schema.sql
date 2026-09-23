-- Схема БД rhyme_analyzer (PostgreSQL).
-- Таблицы создаются автоматически через init_db(); файл — для документации и ручного деплоя.

-- Анонимные сессии браузера (cookie rhyme_sid)
CREATE TABLE IF NOT EXISTS visitor_sessions (
    id          VARCHAR(36) PRIMARY KEY,
    token       VARCHAR(64) NOT NULL UNIQUE,
    ip_address  VARCHAR(45),
    user_agent  TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Канонические тексты (дедуп по text_hash)
CREATE TABLE IF NOT EXISTS texts (
    id              VARCHAR(36) PRIMARY KEY,
    text_hash       VARCHAR(16) NOT NULL UNIQUE,
    normalized_text TEXT NOT NULL,
    preview         VARCHAR(72) NOT NULL DEFAULT '',
    lang            VARCHAR(8),
    block_count     INTEGER NOT NULL DEFAULT 0,
    line_count      INTEGER NOT NULL DEFAULT 0,
    word_count      INTEGER NOT NULL DEFAULT 0,
    char_count      INTEGER NOT NULL DEFAULT 0,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS text_blocks (
    id        BIGSERIAL PRIMARY KEY,
    text_id   VARCHAR(36) NOT NULL REFERENCES texts(id) ON DELETE CASCADE,
    ordinal   INTEGER NOT NULL DEFAULT 0,
    kind      VARCHAR(16) NOT NULL,
    title     VARCHAR(120),
    raw_text  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_text_blocks_text_ordinal ON text_blocks(text_id, ordinal);

-- Прогоны анализа (журнал)
CREATE TABLE IF NOT EXISTS analysis_runs (
    id              VARCHAR(8) PRIMARY KEY,
    text_id         VARCHAR(36) NOT NULL REFERENCES texts(id) ON DELETE RESTRICT,
    session_id      VARCHAR(36) REFERENCES visitor_sessions(id) ON DELETE SET NULL,
    parent_run_id   VARCHAR(8) REFERENCES analysis_runs(id) ON DELETE SET NULL,
    song            VARCHAR(200) NOT NULL,
    lang            VARCHAR(8) NOT NULL DEFAULT 'ru',
    model           VARCHAR(64) NOT NULL DEFAULT '',
    model_secondary VARCHAR(64),
    dual_mode       BOOLEAN NOT NULL DEFAULT FALSE,
    source          VARCHAR(32) NOT NULL DEFAULT 'web-form',
    status          VARCHAR(16) NOT NULL DEFAULT 'done',
    blocks          INTEGER NOT NULL DEFAULT 0,
    lines           INTEGER NOT NULL DEFAULT 0,
    chains          INTEGER NOT NULL DEFAULT 0,
    report_json     JSONB,
    meta_json       JSONB,
    error_kind      VARCHAR(32),
    errors_json     JSONB,
    duration_ms     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_runs_created ON analysis_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_runs_text ON analysis_runs(text_id);

-- Аудит API-запросов
CREATE TABLE IF NOT EXISTS analysis_requests (
    id                  VARCHAR(36) PRIMARY KEY,
    session_id          VARCHAR(36) REFERENCES visitor_sessions(id) ON DELETE SET NULL,
    analysis_run_id     VARCHAR(8) REFERENCES analysis_runs(id) ON DELETE SET NULL,
    request_type        VARCHAR(32) NOT NULL,
    method              VARCHAR(8) NOT NULL DEFAULT 'GET',
    path                VARCHAR(512) NOT NULL,
    ip_address          VARCHAR(45),
    user_agent          TEXT,
    request_body        JSONB,
    response_status     INTEGER,
    response_summary    JSONB,
    duration_ms         INTEGER,
    estimated_cost_usd  DOUBLE PRECISION,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_requests_created ON analysis_requests(created_at DESC);

-- Технические логи пайплайна
CREATE TABLE IF NOT EXISTS activity_logs (
    id              BIGSERIAL PRIMARY KEY,
    session_id      VARCHAR(36) REFERENCES visitor_sessions(id) ON DELETE SET NULL,
    analysis_run_id   VARCHAR(8) REFERENCES analysis_runs(id) ON DELETE SET NULL,
    request_id      VARCHAR(36) REFERENCES analysis_requests(id) ON DELETE SET NULL,
    level           VARCHAR(8) NOT NULL DEFAULT 'info',
    category        VARCHAR(16) NOT NULL DEFAULT 'pipeline',
    stage           VARCHAR(32),
    message         TEXT NOT NULL,
    payload         JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_activity_created ON activity_logs(created_at DESC);

-- Продуктовая аналитика (действия в UI)
CREATE TABLE IF NOT EXISTS user_events (
    id          BIGSERIAL PRIMARY KEY,
    session_id  VARCHAR(36) REFERENCES visitor_sessions(id) ON DELETE SET NULL,
    event_name  VARCHAR(64) NOT NULL,
    properties  JSONB,
    page_path   VARCHAR(256) NOT NULL DEFAULT '/',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_user_events_session ON user_events(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_user_events_name ON user_events(event_name);
