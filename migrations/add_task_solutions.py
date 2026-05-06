# -*- coding: utf-8 -*-
"""
Migration: Create task_solutions table + add ml_training_consent to users.
Works with both SQLite and PostgreSQL.

Usage:
    python migrations/add_task_solutions.py [--pg]
"""
import os, sys, argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def migrate_sqlite():
    """Apply migration to local SQLite."""
    import sqlite3
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'instance', 'formyla.db')
    if not os.path.exists(db_path):
        print(f"SQLite DB not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. Add ml_training_consent to users
    cur.execute("PRAGMA table_info(users)")
    user_cols = [r[1] for r in cur.fetchall()]
    if 'ml_training_consent' not in user_cols:
        cur.execute("ALTER TABLE users ADD COLUMN ml_training_consent BOOLEAN DEFAULT 0 NOT NULL")
        print("  + users.ml_training_consent")

    # 2. Create task_solutions table
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_solutions'")
    if not cur.fetchone():
        cur.execute("""
            CREATE TABLE task_solutions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                task_id INTEGER NOT NULL REFERENCES adaptive_tasks(id),
                user_answer VARCHAR(500) DEFAULT '',
                user_solution_text TEXT DEFAULT '',
                original_photo_url VARCHAR(500),
                photo_hash CHAR(64),
                ocr_raw_output TEXT,
                ocr_corrected TEXT,
                was_corrected BOOLEAN DEFAULT 0 NOT NULL,
                is_correct BOOLEAN DEFAULT 0 NOT NULL,
                score INTEGER DEFAULT 0,
                ai_feedback TEXT,
                consent_for_training BOOLEAN DEFAULT 0 NOT NULL,
                quality_score FLOAT,
                plan_id INTEGER REFERENCES prep_plans(id),
                day_id INTEGER REFERENCES prep_days(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX idx_task_solutions_user_id ON task_solutions(user_id)")
        cur.execute("CREATE INDEX idx_task_solutions_task_id ON task_solutions(task_id)")
        cur.execute("CREATE INDEX idx_task_solutions_photo_hash ON task_solutions(photo_hash)")
        print("  + task_solutions table created with indexes")
    else:
        print("  task_solutions already exists")

    conn.commit()
    conn.close()
    print("SQLite migration complete.")


def migrate_pg():
    """Apply migration to production PostgreSQL."""
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            '.env.migration')
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k] = v

    import psycopg2
    conn = psycopg2.connect(os.environ['EXTERNAL_DATABASE_URL'])
    conn.autocommit = True
    cur = conn.cursor()

    # 1. Add ml_training_consent to users
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'ml_training_consent'
    """)
    if not cur.fetchone():
        cur.execute("ALTER TABLE users ADD COLUMN ml_training_consent BOOLEAN NOT NULL DEFAULT FALSE")
        print("  + users.ml_training_consent")

    # 2. Create task_solutions table
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename='task_solutions'")
    if not cur.fetchone():
        cur.execute("""
            CREATE TABLE task_solutions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                task_id INTEGER NOT NULL REFERENCES adaptive_tasks(id),
                user_answer VARCHAR(500) DEFAULT '',
                user_solution_text TEXT DEFAULT '',
                original_photo_url VARCHAR(500),
                photo_hash CHAR(64),
                ocr_raw_output TEXT,
                ocr_corrected TEXT,
                was_corrected BOOLEAN NOT NULL DEFAULT FALSE,
                is_correct BOOLEAN NOT NULL DEFAULT FALSE,
                score INTEGER DEFAULT 0,
                ai_feedback TEXT,
                consent_for_training BOOLEAN NOT NULL DEFAULT FALSE,
                quality_score FLOAT,
                plan_id INTEGER REFERENCES prep_plans(id),
                day_id INTEGER REFERENCES prep_days(id),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("CREATE INDEX idx_task_solutions_user_id ON task_solutions(user_id)")
        cur.execute("CREATE INDEX idx_task_solutions_task_id ON task_solutions(task_id)")
        cur.execute("CREATE INDEX idx_task_solutions_photo_hash ON task_solutions(photo_hash)")
        print("  + task_solutions table created with indexes")
    else:
        print("  task_solutions already exists")

    cur.close()
    conn.close()
    print("PostgreSQL migration complete.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pg', action='store_true', help='Migrate production PostgreSQL')
    args = parser.parse_args()

    print("=== Migration: task_solutions + ml_training_consent ===")
    migrate_sqlite()
    if args.pg:
        migrate_pg()
    print("\nDone!")
