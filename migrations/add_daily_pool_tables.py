#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция: создание таблиц для Daily Olympiad Pool.

Запуск:
    python migrations/add_daily_pool_tables.py

Таблицы:
  - problems_archive       — архив реальных задач из olympiads.py
  - olympiad_analysis      — кэш анализа комбинаций (Opus 4.1)
  - daily_variants         — сгенерированные варианты (5 задач/день/комбинация)
  - daily_problems         — отдельные задачи в варианте
  - problem_embeddings     — векторные эмбеддинги для дедупликации (pgvector)
  - user_daily_attempts    — попытки пользователей
  - generation_costs       — трекинг стоимости API-вызовов

Примечание: pgvector extension создаётся только на PostgreSQL.
На SQLite таблица problem_embeddings создаётся без VECTOR-типа (для локальной разработки).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


RAW_SQL_POSTGRES = """
-- Enable pgvector extension (requires superuser or extension already installed)
CREATE EXTENSION IF NOT EXISTS vector;

-- Archive of real problems from olympiads.py
CREATE TABLE IF NOT EXISTS problems_archive (
    id              SERIAL PRIMARY KEY,
    olympiad_slug   VARCHAR(50) NOT NULL,
    olympiad_title  VARCHAR(200),
    grade           INTEGER NOT NULL,
    round           VARCHAR(30) NOT NULL,
    round_title     VARCHAR(200),
    year            INTEGER,
    num             INTEGER,
    text            TEXT NOT NULL,
    answer          TEXT,
    solution        TEXT,
    source          VARCHAR(50) DEFAULT 'olympiads.py',
    combo_id        INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_archive_combo 
    ON problems_archive(olympiad_slug, grade, round);
CREATE INDEX IF NOT EXISTS ix_archive_year 
    ON problems_archive(year);

-- Analysis cache (1 per combo, valid 30 days)
CREATE TABLE IF NOT EXISTS olympiad_analysis (
    id              SERIAL PRIMARY KEY,
    olympiad_slug   VARCHAR(50) NOT NULL,
    grade           INTEGER NOT NULL,
    round           VARCHAR(30) NOT NULL,
    analysis_json   JSONB NOT NULL,
    model_used      VARCHAR(100),
    tokens_used     INTEGER DEFAULT 0,
    cost_usd        NUMERIC(8,4) DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    UNIQUE(olympiad_slug, grade, round)
);

-- Daily variants (5 problems each)
CREATE TABLE IF NOT EXISTS daily_variants (
    id              SERIAL PRIMARY KEY,
    olympiad_slug   VARCHAR(50) NOT NULL,
    olympiad_title  VARCHAR(200),
    grade           INTEGER NOT NULL,
    round           VARCHAR(30) NOT NULL,
    round_title     VARCHAR(200),
    variant_date    DATE NOT NULL,
    status          VARCHAR(20) DEFAULT 'pending',
    generation_stack VARCHAR(1) DEFAULT 'A',
    quality_report  JSONB,
    meta_review     JSONB,
    total_cost_usd  NUMERIC(8,4) DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    approved_at     TIMESTAMPTZ,
    UNIQUE(olympiad_slug, grade, round, variant_date, generation_stack)
);
CREATE INDEX IF NOT EXISTS ix_daily_variants_date 
    ON daily_variants(variant_date);
CREATE INDEX IF NOT EXISTS ix_daily_variants_status 
    ON daily_variants(status);
CREATE INDEX IF NOT EXISTS ix_daily_variants_combo 
    ON daily_variants(olympiad_slug, grade, round);

-- Individual problems in a variant
CREATE TABLE IF NOT EXISTS daily_problems (
    id              SERIAL PRIMARY KEY,
    variant_id      INTEGER NOT NULL REFERENCES daily_variants(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    text            TEXT NOT NULL,
    solution        TEXT,
    answer          TEXT,
    topic           VARCHAR(100),
    difficulty      INTEGER,
    quality_scores  JSONB,
    generation_log  JSONB,
    status          VARCHAR(20) DEFAULT 'pending',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(variant_id, position)
);
CREATE INDEX IF NOT EXISTS ix_daily_problems_variant 
    ON daily_problems(variant_id);

-- Embeddings for deduplication (pgvector)
CREATE TABLE IF NOT EXISTS problem_embeddings (
    id              SERIAL PRIMARY KEY,
    problem_id      INTEGER REFERENCES daily_problems(id) ON DELETE CASCADE,
    archive_id      INTEGER REFERENCES problems_archive(id),
    olympiad_slug   VARCHAR(50) NOT NULL,
    grade           INTEGER NOT NULL,
    round           VARCHAR(30) NOT NULL,
    embedding       VECTOR(3072) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_embeddings_combo 
    ON problem_embeddings(olympiad_slug, grade, round);

-- User attempts on daily variants
CREATE TABLE IF NOT EXISTS user_daily_attempts (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    variant_id      INTEGER NOT NULL REFERENCES daily_variants(id),
    problem_id      INTEGER NOT NULL REFERENCES daily_problems(id),
    user_answer     TEXT,
    is_correct      BOOLEAN,
    time_spent_sec  INTEGER,
    attempted_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_attempts_user 
    ON user_daily_attempts(user_id, variant_id);

-- Generation cost tracking
CREATE TABLE IF NOT EXISTS generation_costs (
    id              SERIAL PRIMARY KEY,
    task_type       VARCHAR(50) NOT NULL,
    model           VARCHAR(100) NOT NULL,
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    cost_usd        NUMERIC(8,6) NOT NULL DEFAULT 0,
    variant_id      INTEGER REFERENCES daily_variants(id),
    problem_id      INTEGER REFERENCES daily_problems(id),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_costs_date 
    ON generation_costs(created_at);
CREATE INDEX IF NOT EXISTS ix_costs_model 
    ON generation_costs(model);
"""

RAW_SQL_SQLITE = """
-- Archive of real problems from olympiads.py
CREATE TABLE IF NOT EXISTS problems_archive (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    olympiad_slug   VARCHAR(50) NOT NULL,
    olympiad_title  VARCHAR(200),
    grade           INTEGER NOT NULL,
    round           VARCHAR(30) NOT NULL,
    round_title     VARCHAR(200),
    year            INTEGER,
    num             INTEGER,
    text            TEXT NOT NULL,
    answer          TEXT,
    solution        TEXT,
    source          VARCHAR(50) DEFAULT 'olympiads.py',
    combo_id        INTEGER,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_archive_combo 
    ON problems_archive(olympiad_slug, grade, round);
CREATE INDEX IF NOT EXISTS ix_archive_year 
    ON problems_archive(year);

-- Analysis cache
CREATE TABLE IF NOT EXISTS olympiad_analysis (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    olympiad_slug   VARCHAR(50) NOT NULL,
    grade           INTEGER NOT NULL,
    round           VARCHAR(30) NOT NULL,
    analysis_json   TEXT NOT NULL,
    model_used      VARCHAR(100),
    tokens_used     INTEGER DEFAULT 0,
    cost_usd        REAL DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at      DATETIME,
    UNIQUE(olympiad_slug, grade, round)
);

-- Daily variants
CREATE TABLE IF NOT EXISTS daily_variants (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    olympiad_slug   VARCHAR(50) NOT NULL,
    olympiad_title  VARCHAR(200),
    grade           INTEGER NOT NULL,
    round           VARCHAR(30) NOT NULL,
    round_title     VARCHAR(200),
    variant_date    DATE NOT NULL,
    status          VARCHAR(20) DEFAULT 'pending',
    generation_stack VARCHAR(1) DEFAULT 'A',
    quality_report  TEXT,
    meta_review     TEXT,
    total_cost_usd  REAL DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    approved_at     DATETIME,
    UNIQUE(olympiad_slug, grade, round, variant_date, generation_stack)
);

-- Daily problems
CREATE TABLE IF NOT EXISTS daily_problems (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    variant_id      INTEGER NOT NULL REFERENCES daily_variants(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    text            TEXT NOT NULL,
    solution        TEXT,
    answer          TEXT,
    topic           VARCHAR(100),
    difficulty      INTEGER,
    quality_scores  TEXT,
    generation_log  TEXT,
    status          VARCHAR(20) DEFAULT 'pending',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(variant_id, position)
);

-- Embeddings (SQLite: store as BLOB, no vector search)
CREATE TABLE IF NOT EXISTS problem_embeddings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id      INTEGER REFERENCES daily_problems(id) ON DELETE CASCADE,
    archive_id      INTEGER REFERENCES problems_archive(id),
    olympiad_slug   VARCHAR(50) NOT NULL,
    grade           INTEGER NOT NULL,
    round           VARCHAR(30) NOT NULL,
    embedding       BLOB,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- User attempts
CREATE TABLE IF NOT EXISTS user_daily_attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    variant_id      INTEGER NOT NULL REFERENCES daily_variants(id),
    problem_id      INTEGER NOT NULL REFERENCES daily_problems(id),
    user_answer     TEXT,
    is_correct      BOOLEAN,
    time_spent_sec  INTEGER,
    attempted_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Generation costs
CREATE TABLE IF NOT EXISTS generation_costs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type       VARCHAR(50) NOT NULL,
    model           VARCHAR(100) NOT NULL,
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    cost_usd        REAL NOT NULL DEFAULT 0,
    variant_id      INTEGER REFERENCES daily_variants(id),
    problem_id      INTEGER REFERENCES daily_problems(id),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


def split_sql_statements(sql_text):
    """
    Split SQL into individual statements, respecting parentheses.
    A semicolon inside CREATE TABLE (...) should NOT split the statement.
    """
    statements = []
    current = []
    paren_depth = 0

    for line in sql_text.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('--'):
            continue

        paren_depth += line.count('(') - line.count(')')
        current.append(line)

        if stripped.endswith(';') and paren_depth <= 0:
            stmt = '\n'.join(current).strip().rstrip(';').strip()
            if stmt:
                statements.append(stmt)
            current = []
            paren_depth = 0

    if current:
        stmt = '\n'.join(current).strip().rstrip(';').strip()
        if stmt:
            statements.append(stmt)

    return statements


def run_migration():
    """Creates Daily Pool tables."""
    from app import app
    from models import db

    with app.app_context():
        db_url = str(db.engine.url)
        is_postgres = 'postgresql' in db_url or 'postgres' in db_url

        if is_postgres:
            print("PostgreSQL detected - using pgvector + JSONB")
            sql = RAW_SQL_POSTGRES
        else:
            print("SQLite detected - using TEXT/BLOB fallbacks")
            sql = RAW_SQL_SQLITE

        statements = split_sql_statements(sql)
        success = 0
        errors = 0

        for stmt in statements:
            try:
                db.session.execute(db.text(stmt))
                db.session.commit()
                success += 1
            except Exception as e:
                db.session.rollback()
                err_msg = str(e)
                if 'already exists' in err_msg:
                    print(f"  [skip] Already exists: {stmt[:60]}...")
                else:
                    print(f"  [ERR] {err_msg[:120]}")
                    errors += 1

        print(f"\nMigration complete: {success} statements OK, {errors} errors")

        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        expected = [
            'problems_archive', 'olympiad_analysis', 'daily_variants',
            'daily_problems', 'problem_embeddings', 'user_daily_attempts',
            'generation_costs'
        ]
        for t in expected:
            if t in tables:
                cols = [c['name'] for c in inspector.get_columns(t)]
                print(f"  [OK] {t} ({len(cols)} columns)")
            else:
                print(f"  [FAIL] {t} - NOT FOUND")

        return True


if __name__ == '__main__':
    run_migration()
