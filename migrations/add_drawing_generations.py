# -*- coding: utf-8 -*-
"""
Migration: create `drawing_generations` table.

Stores one row per call to services.drawing_service.generate_drawing
(or per request to /api/drawing/generate). Used for analytics and
prompt-tuning: which problems work first try, which require repair,
which fail entirely.

Idempotent — safe to run multiple times.

Usage:
    python migrations/add_drawing_generations.py            # local SQLite
    python migrations/add_drawing_generations.py --pg       # production PG too
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------
def _sqlite_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'instance',
        'formyla.db',
    )


def migrate_sqlite():
    import sqlite3

    db_path = _sqlite_path()
    if not os.path.exists(db_path):
        print(f'SQLite DB not found: {db_path}')
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='drawing_generations'"
    )
    if cur.fetchone():
        print('  drawing_generations already exists')
    else:
        cur.execute(
            """
            CREATE TABLE drawing_generations (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NULL
                                  REFERENCES users(id) ON DELETE SET NULL,
                problem_sha256  VARCHAR(64) NOT NULL,
                problem         TEXT NOT NULL,
                generated_code  TEXT NULL,
                model           VARCHAR(120) NULL,
                status          VARCHAR(20) NOT NULL DEFAULT 'ok',
                error           TEXT NULL,
                repair_iters    INTEGER NOT NULL DEFAULT 0,
                render_ms       INTEGER NULL,
                cost_usd        REAL NOT NULL DEFAULT 0.0,
                image_path      VARCHAR(500) NULL,
                image_size      INTEGER NULL,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            'CREATE INDEX ix_drawing_generations_user_id '
            'ON drawing_generations(user_id)'
        )
        cur.execute(
            'CREATE INDEX ix_drawing_generations_sha '
            'ON drawing_generations(problem_sha256)'
        )
        cur.execute(
            'CREATE INDEX ix_drawing_generations_status '
            'ON drawing_generations(status)'
        )
        cur.execute(
            'CREATE INDEX ix_drawing_generations_created_at '
            'ON drawing_generations(created_at)'
        )
        print('  + drawing_generations (sqlite)')

    conn.commit()
    conn.close()
    print('SQLite migration complete.')


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
def _load_env_migration():
    env_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        '.env.migration',
    )
    if not os.path.exists(env_file):
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ[k] = v


def migrate_pg():
    _load_env_migration()
    dsn = os.environ.get('EXTERNAL_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if not dsn:
        print('  EXTERNAL_DATABASE_URL / DATABASE_URL not set — skipping PG.')
        return

    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.drawing_generations')")
            if cur.fetchone()[0]:
                print('  drawing_generations already exists')
            else:
                cur.execute(
                    """
                    CREATE TABLE drawing_generations (
                        id              SERIAL PRIMARY KEY,
                        user_id         INTEGER NULL
                                          REFERENCES users(id) ON DELETE SET NULL,
                        problem_sha256  VARCHAR(64) NOT NULL,
                        problem         TEXT NOT NULL,
                        generated_code  TEXT NULL,
                        model           VARCHAR(120) NULL,
                        status          VARCHAR(20) NOT NULL DEFAULT 'ok',
                        error           TEXT NULL,
                        repair_iters    INTEGER NOT NULL DEFAULT 0,
                        render_ms       INTEGER NULL,
                        cost_usd        DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                        image_path      VARCHAR(500) NULL,
                        image_size      INTEGER NULL,
                        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cur.execute(
                    'CREATE INDEX ix_drawing_generations_user_id '
                    'ON drawing_generations(user_id)'
                )
                cur.execute(
                    'CREATE INDEX ix_drawing_generations_sha '
                    'ON drawing_generations(problem_sha256)'
                )
                cur.execute(
                    'CREATE INDEX ix_drawing_generations_status '
                    'ON drawing_generations(status)'
                )
                cur.execute(
                    'CREATE INDEX ix_drawing_generations_created_at '
                    'ON drawing_generations(created_at)'
                )
                print('  + drawing_generations (pg)')
    print('PostgreSQL migration complete.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pg', action='store_true',
                        help='Migrate production PostgreSQL too')
    args = parser.parse_args()

    print('=== Migration: drawing_generations ===')
    migrate_sqlite()
    if args.pg:
        migrate_pg()
    print('\nDone!')
