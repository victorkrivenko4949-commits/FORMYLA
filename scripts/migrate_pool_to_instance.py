# -*- coding: utf-8 -*-
"""
TASK 4: Pool migration from root formyla.db -> instance/formyla.db.

Works with SQLAlchemy for the instance DB (compatible with SQLite and PostgreSQL).
Root DB read uses sqlite3 (root is always SQLite).
No PRAGMA, no INSERT OR IGNORE on PG path.

IDEMPOTENT: ON CONFLICT (id) DO NOTHING / INSERT OR IGNORE on PK id.
Conflict policy: instance row wins, root row is skipped (idempotent).

Transferred:
1. adaptive_tasks — all rows incl. difficulty_level and difficulty_level_src.
   Column difficulty_level_src added to instance if missing.
   Instance-only columns (theme_id, theme_title, methods_json, origin) = NULL.
2. task_assignment_history — all rows. Schemas identical.
"""
import sys
import os

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import sqlite3
import datetime

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DB = os.path.join(BASE, 'formyla.db')
INST_DB = os.path.join(BASE, 'instance', 'formyla.db')

sys.path.insert(0, BASE)

log(f"ROOT_DB: {ROOT_DB}")
log(f"INST_DB: {INST_DB}")

for path, label in [(ROOT_DB, 'root'), (INST_DB, 'instance')]:
    if not os.path.exists(path):
        log(f"ERROR: {label} DB not found at {path}")
        sys.exit(1)
    log(f"  {label}: {os.path.getsize(path)/1024:.1f} KB")

# Read root data via sqlite3 (root is always SQLite)
conn_root = sqlite3.connect(ROOT_DB)
cur_root = conn_root.cursor()

# Connect to instance via SQLAlchemy (compatible with PG)
from dotenv import load_dotenv
load_dotenv()

from app import app as flask_app
from models import db as _db
from sqlalchemy import text, inspect

with flask_app.app_context():
    engine = _db.engine
    dialect_name = engine.dialect.name
    inspector = inspect(engine)
    conn = engine.connect()

    try:
        # === STEP 1: Ensure difficulty_level_src column ===
        log("Step 1: Checking difficulty_level_src column...")
        inst_cols = {c['name'] for c in inspector.get_columns('adaptive_tasks')}
        if 'difficulty_level_src' not in inst_cols:
            log("  Adding difficulty_level_src column to instance adaptive_tasks...")
            if dialect_name == 'postgresql':
                conn.execute(text("ALTER TABLE adaptive_tasks ADD COLUMN IF NOT EXISTS difficulty_level_src INTEGER"))
            else:
                try:
                    conn.execute(text("ALTER TABLE adaptive_tasks ADD COLUMN difficulty_level_src INTEGER"))
                except Exception:
                    pass  # already exists
            conn.execute(text("COMMIT"))
            log("  [OK] Added")
        else:
            log("  Column difficulty_level_src already exists — skip ALTER")

        # === STEP 2: Map columns ===
        inst_cols_list = [c['name'] for c in inspector.get_columns('adaptive_tasks')]
        inst_cols_set = set(inst_cols_list)

        cur_root.execute("PRAGMA table_info('adaptive_tasks')")
        root_cols_list = [c[1] for c in cur_root.fetchall()]
        root_cols_set = set(root_cols_list)

        common_cols = [c for c in root_cols_list if c in inst_cols_set]
        instance_only = [c for c in inst_cols_list if c not in root_cols_set]
        log(f"  Common columns ({len(common_cols)})")
        log(f"  Instance-only (will be NULL): {instance_only}")

        # === STEP 3: Read root rows ===
        cols_str = ', '.join(f'"{c}"' for c in common_cols)
        cur_root.execute(f'SELECT {cols_str} FROM adaptive_tasks ORDER BY id')
        root_rows = cur_root.fetchall()
        log(f"Read {len(root_rows)} rows from root adaptive_tasks")

        # === STEP 4: Insert with conflict handling ===
        cols_joined = ', '.join(f'"{c}"' for c in common_cols)
        placeholders = ', '.join(f':c{i}' for i in range(len(common_cols)))

        if dialect_name == 'postgresql':
            insert_sql = text(
                f'INSERT INTO adaptive_tasks ({cols_joined}) VALUES ({placeholders}) '
                f'ON CONFLICT (id) DO NOTHING'
            )
        else:
            insert_sql = text(
                f'INSERT OR IGNORE INTO adaptive_tasks ({cols_joined}) VALUES ({placeholders})'
            )

        inserted = 0
        skipped = 0
        for row in root_rows:
            params = {f'c{i}': row[i] for i in range(len(common_cols))}
            r = conn.execute(insert_sql, params)
            if r.rowcount > 0:
                inserted += 1
            else:
                skipped += 1

        conn.execute(text("COMMIT"))
        log(f"  adaptive_tasks: inserted={inserted}, skipped={skipped}")

        # === STEP 5: task_assignment_history ===
        log("--- task_assignment_history ---")
        hist_cols = [c['name'] for c in inspector.get_columns('task_assignment_history')]
        cols_str_h = ', '.join(f'"{c}"' for c in hist_cols)
        placeholders_h = ', '.join(f':c{i}' for i in range(len(hist_cols)))
        cur_root.execute(f'SELECT {cols_str_h} FROM task_assignment_history ORDER BY id')
        hist_rows = cur_root.fetchall()
        log(f"  Read {len(hist_rows)} rows from root")

        if dialect_name == 'postgresql':
            insert_sql_h = text(
                f'INSERT INTO task_assignment_history ({cols_str_h}) VALUES ({placeholders_h}) '
                f'ON CONFLICT (id) DO NOTHING'
            )
        else:
            insert_sql_h = text(
                f'INSERT OR IGNORE INTO task_assignment_history ({cols_str_h}) VALUES ({placeholders_h})'
            )

        inserted_h = 0
        skipped_h = 0
        for row in hist_rows:
            params = {f'c{i}': row[i] for i in range(len(hist_cols))}
            r = conn.execute(insert_sql_h, params)
            if r.rowcount > 0:
                inserted_h += 1
            else:
                skipped_h += 1

        conn.execute(text("COMMIT"))
        log(f"  task_assignment_history: inserted={inserted_h}, skipped={skipped_h}")

        # === STEP 6: Verification ===
        log("=== VERIFICATION ===")
        r = conn.execute(text("SELECT COUNT(*) FROM adaptive_tasks"))
        log(f"  adaptive_tasks total: {r.scalar()}")

        r = conn.execute(text(
            "SELECT class_level, COUNT(*) FROM adaptive_tasks GROUP BY class_level ORDER BY class_level"
        ))
        log("  By class_level:")
        for cls, cnt in r.fetchall():
            log(f"    class {cls}: {cnt}")

        r = conn.execute(text(
            "SELECT difficulty_level, COUNT(*) FROM adaptive_tasks "
            "WHERE difficulty_level IS NOT NULL GROUP BY difficulty_level ORDER BY difficulty_level"
        ))
        log("  By difficulty_level:")
        for lvl, cnt in r.fetchall():
            log(f"    level {lvl}: {cnt}")

        r = conn.execute(text("SELECT COUNT(*) FROM adaptive_tasks WHERE difficulty_level IS NULL"))
        log(f"  NULL difficulty_level: {r.scalar()}")

        r = conn.execute(text("SELECT MIN(difficulty_level), MAX(difficulty_level) FROM adaptive_tasks"))
        min_l, max_l = r.fetchone()
        log(f"  difficulty_level range: {min_l} .. {max_l}")

        r = conn.execute(text(
            "SELECT COUNT(*) FROM adaptive_tasks WHERE difficulty_level NOT BETWEEN 1 AND 5"
        ))
        log(f"  Out of 1..5 range: {r.scalar()}")

        r = conn.execute(text("SELECT COUNT(*) FROM adaptive_tasks WHERE difficulty_level_src IS NOT NULL"))
        log(f"  difficulty_level_src non-null: {r.scalar()}")

        r = conn.execute(text("SELECT DISTINCT difficulty_level_src FROM adaptive_tasks ORDER BY 1"))
        log(f"  difficulty_level_src values: {[row[0] for row in r.fetchall()]}")

        r = conn.execute(text("SELECT COUNT(*) FROM task_assignment_history"))
        log(f"  task_assignment_history: {r.scalar()} rows")

        # === STEP 7: Idempotency test ===
        log("=== IDEMPOTENCY TEST (re-insert same data) ===")
        reinserted = 0
        for row in root_rows:
            params = {f'c{i}': row[i] for i in range(len(common_cols))}
            r = conn.execute(insert_sql, params)
            reinserted += r.rowcount
        log(f"  Re-insert adaptive_tasks: {reinserted} (expect 0)")

        reinserted_h = 0
        for row in hist_rows:
            params = {f'c{i}': row[i] for i in range(len(hist_cols))}
            r = conn.execute(insert_sql_h, params)
            reinserted_h += r.rowcount
        log(f"  Re-insert history: {reinserted_h} (expect 0)")

        conn.execute(text("COMMIT"))

    except Exception as e:
        conn.execute(text("ROLLBACK"))
        log(f"ERROR: {e}")
        raise
    finally:
        conn.close()
        conn_root.close()

log("=== DONE ===")
