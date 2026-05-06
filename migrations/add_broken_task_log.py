# -*- coding: utf-8 -*-
"""
Migration: create `broken_task_log` table.

Used by services/latex_validator.py through services/prep_planner.py to
record AdaptiveTask rows whose `task_text` would not render in KaTeX.
Idempotent — safe to run multiple times.

Usage:
    python migrations/add_broken_task_log.py            # local SQLite
    python migrations/add_broken_task_log.py --pg       # production PG too
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
        "SELECT name FROM sqlite_master WHERE type='table' AND name='broken_task_log'"
    )
    if cur.fetchone():
        print('  broken_task_log already exists')
    else:
        cur.execute(
            """
            CREATE TABLE broken_task_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id     INTEGER NOT NULL
                              REFERENCES adaptive_tasks(id) ON DELETE CASCADE,
                surface     VARCHAR(32) NOT NULL DEFAULT 'prep',
                reasons     TEXT NOT NULL DEFAULT '',
                detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                hits        INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        cur.execute(
            'CREATE INDEX ix_broken_task_log_task_id ON broken_task_log(task_id)'
        )
        cur.execute(
            'CREATE INDEX ix_broken_task_log_surface ON broken_task_log(surface)'
        )
        cur.execute(
            'CREATE INDEX ix_broken_task_log_detected_at ON broken_task_log(detected_at)'
        )
        cur.execute(
            'CREATE INDEX ix_broken_task_log_task_surface '
            'ON broken_task_log(task_id, surface)'
        )
        print('  + broken_task_log (sqlite)')

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
            cur.execute(
                "SELECT to_regclass('public.broken_task_log')"
            )
            if cur.fetchone()[0]:
                print('  broken_task_log already exists')
            else:
                cur.execute(
                    """
                    CREATE TABLE broken_task_log (
                        id           SERIAL PRIMARY KEY,
                        task_id      INTEGER NOT NULL
                                       REFERENCES adaptive_tasks(id) ON DELETE CASCADE,
                        surface      VARCHAR(32) NOT NULL DEFAULT 'prep',
                        reasons      TEXT NOT NULL DEFAULT '',
                        detected_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        hits         INTEGER NOT NULL DEFAULT 1
                    )
                    """
                )
                cur.execute('CREATE INDEX ix_broken_task_log_task_id ON broken_task_log(task_id)')
                cur.execute('CREATE INDEX ix_broken_task_log_surface ON broken_task_log(surface)')
                cur.execute('CREATE INDEX ix_broken_task_log_detected_at ON broken_task_log(detected_at)')
                cur.execute(
                    'CREATE INDEX ix_broken_task_log_task_surface '
                    'ON broken_task_log(task_id, surface)'
                )
                print('  + broken_task_log (pg)')
    print('PostgreSQL migration complete.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pg', action='store_true', help='Migrate production PostgreSQL too')
    args = parser.parse_args()

    print('=== Migration: broken_task_log ===')
    migrate_sqlite()
    if args.pg:
        migrate_pg()
    print('\nDone!')
