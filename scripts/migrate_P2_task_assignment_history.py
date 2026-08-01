# -*- coding: utf-8 -*-
"""
scripts/migrate_P2_task_assignment_history.py

Migration: create task_assignment_history table and backfill from existing data.

Works with SQLAlchemy — compatible with both SQLite and PostgreSQL.
No direct sqlite3, no PRAGMA, no INSERT OR IGNORE.

Idempotent: safe to run multiple times.
"""

import sys
import os
import json
import logging
from datetime import date, datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

MSK_TZ = timezone(timedelta(hours=3))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()


def ensure_table(conn, dialect_name):
    """Create table if not exists, compatible with SQLite and PostgreSQL."""
    from sqlalchemy import text

    if dialect_name == 'postgresql':
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS task_assignment_history (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                task_id INTEGER NOT NULL,
                assigned_date DATE NOT NULL,
                source VARCHAR(32) NOT NULL DEFAULT 'daily_set',
                result VARCHAR(16) DEFAULT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(user_id, task_id)
            )
        """))
    else:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS task_assignment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task_id INTEGER NOT NULL,
                assigned_date DATE NOT NULL,
                source VARCHAR(32) NOT NULL DEFAULT 'daily_set',
                result VARCHAR(16) DEFAULT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, task_id)
            )
        """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tah_user_id ON task_assignment_history(user_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tah_task_id ON task_assignment_history(task_id)"))
    logger.info("Table task_assignment_history ensured with indices.")


def backfill_from_task_solutions(conn, dialect_name):
    """Backfill from task_solutions: 1 row = 1 (user_id, task_id) pair."""
    from sqlalchemy import text

    if dialect_name == 'postgresql':
        insert_sql = text("""
            INSERT INTO task_assignment_history
                (user_id, task_id, assigned_date, source, result, created_at)
            SELECT
                user_id,
                task_id,
                DATE(created_at) AS assigned_date,
                'diagnostic' AS source,
                CASE
                    WHEN is_correct = 1 THEN 'correct'
                    WHEN is_correct = 0 THEN 'incorrect'
                    ELSE NULL
                END AS result,
                created_at
            FROM task_solutions
            WHERE user_id IS NOT NULL AND task_id IS NOT NULL
            ON CONFLICT (user_id, task_id) DO NOTHING
        """)
    else:
        insert_sql = text("""
            INSERT OR IGNORE INTO task_assignment_history
                (user_id, task_id, assigned_date, source, result, created_at)
            SELECT
                user_id,
                task_id,
                DATE(created_at) AS assigned_date,
                'diagnostic' AS source,
                CASE
                    WHEN is_correct = 1 THEN 'correct'
                    WHEN is_correct = 0 THEN 'incorrect'
                    ELSE NULL
                END AS result,
                created_at
            FROM task_solutions
            WHERE user_id IS NOT NULL AND task_id IS NOT NULL
        """)
    result = conn.execute(insert_sql)
    n = result.rowcount
    logger.info("Backfill from task_solutions: %d rows inserted", n)
    return n


def backfill_from_daily_items(conn, dialect_name):
    """Backfill from daily_task_items + daily_task_sets."""
    from sqlalchemy import text

    result = conn.execute(text("""
        SELECT
            dts.user_id,
            dts.target_date,
            dti.subject,
            dti.topic,
            dti.difficulty_level,
            dti.task_text,
            dti.is_correct,
            dti.answered_at,
            dts.class_level
        FROM daily_task_items dti
        JOIN daily_task_sets dts ON dti.daily_set_id = dts.id
        WHERE dti.status = 'approved'
            AND dts.user_id IS NOT NULL
    """))
    items = result.fetchall()
    if not items:
        logger.info("No daily_task_items to backfill.")
        return 0

    combos = set()
    for row in items:
        user_id, tdate, subject, topic, diff, ttext, is_correct, answered_at, cls_lvl = row
        combos.add((cls_lvl or 9, subject or '', topic or '', diff or 1))

    combo_to_tasks = {}
    for cls_lvl, subject, topic, diff in combos:
        result = conn.execute(text("""
            SELECT id FROM adaptive_tasks
            WHERE class_level = :cls AND difficulty_level = :diff AND subject = :subj
            ORDER BY id
        """), {'cls': cls_lvl, 'diff': diff, 'subj': subject})
        ids = [r[0] for r in result.fetchall()]
        if ids:
            combo_to_tasks[(cls_lvl, subject, topic, diff)] = ids

    if dialect_name == 'postgresql':
        insert_sql = text("""
            INSERT INTO task_assignment_history
                (user_id, task_id, assigned_date, source, result, created_at)
            VALUES (:uid, :tid, :adate, 'daily_set', :result, :cat)
            ON CONFLICT (user_id, task_id) DO NOTHING
        """)
    else:
        insert_sql = text("""
            INSERT OR IGNORE INTO task_assignment_history
                (user_id, task_id, assigned_date, source, result, created_at)
            VALUES (:uid, :tid, :adate, 'daily_set', :result, :cat)
        """)

    inserted = 0
    combo_used_count = {}

    for row in items:
        user_id, tdate, subject, topic, diff, ttext, is_correct, answered_at, cls_lvl = row
        cls_lvl = cls_lvl or 9
        subject = subject or ''
        topic = topic or ''
        diff = diff or 1

        task_ids = combo_to_tasks.get((cls_lvl, subject, topic, diff), [])
        if not task_ids:
            result2 = conn.execute(text("""
                SELECT id FROM adaptive_tasks
                WHERE class_level = :cls AND difficulty_level = :diff AND topic = :tpc
                ORDER BY id
            """), {'cls': cls_lvl, 'diff': diff, 'tpc': topic})
            task_ids = [r[0] for r in result2.fetchall()]

        if not task_ids:
            continue

        combo_key = (cls_lvl, subject, topic, diff)
        idx = combo_used_count.get(combo_key, 0) % len(task_ids)
        task_id = task_ids[idx]
        combo_used_count[combo_key] = idx + 1

        assigned_date = tdate or answered_at or '2026-01-01'
        if isinstance(assigned_date, str):
            try:
                assigned_date = assigned_date[:10]
            except:
                assigned_date = '2026-01-01'
        else:
            assigned_date = str(assigned_date)[:10]

        result_val = None
        if is_correct == 1:
            result_val = 'correct'
        elif is_correct == 0:
            result_val = 'incorrect'

        created_at = answered_at or datetime.now(MSK_TZ).isoformat()
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()

        r = conn.execute(insert_sql, {
            'uid': user_id, 'tid': task_id, 'adate': assigned_date,
            'result': result_val, 'cat': created_at
        })
        if r.rowcount > 0:
            inserted += 1

    logger.info("Backfill from daily_task_items: %d rows inserted (of %d items)", inserted, len(items))
    return inserted


def main():
    from app import app as flask_app
    from models import db as _db
    from sqlalchemy import text

    with flask_app.app_context():
        engine = _db.engine
        dialect_name = engine.dialect.name
        conn = engine.connect()
        trans = conn.begin()

        try:
            ensure_table(conn, dialect_name)
            trans.commit()
            trans = conn.begin()

            # Check if already backfilled
            result = conn.execute(text("SELECT COUNT(*) FROM task_assignment_history"))
            existing = result.scalar()
            if existing > 0:
                logger.info("task_assignment_history already has %d rows — skipping backfill", existing)
            else:
                n1 = backfill_from_task_solutions(conn, dialect_name)
                n2 = backfill_from_daily_items(conn, dialect_name)
                trans.commit()
                logger.info("Total backfilled: %d rows (task_solutions: %d, daily_items: %d)", n1 + n2, n1, n2)
                trans = conn.begin()

            # Final stats
            for query_name, query in [
                ("total rows", "SELECT COUNT(*) FROM task_assignment_history"),
                ("distinct users", "SELECT COUNT(DISTINCT user_id) FROM task_assignment_history"),
                ("distinct tasks", "SELECT COUNT(DISTINCT task_id) FROM task_assignment_history"),
            ]:
                result = conn.execute(text(query))
                val = result.scalar()
                logger.info("  %s: %s", query_name, val)

            trans.commit()
        except Exception as e:
            trans.rollback()
            logger.error("Migration failed: %s", e)
            raise
        finally:
            conn.close()

    logger.info("Migration complete.")


if __name__ == '__main__':
    main()
