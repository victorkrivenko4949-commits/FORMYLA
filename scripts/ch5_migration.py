# -*- coding: utf-8 -*-
"""
CH5 Migration: figure_build_jobs table for the new /figures/generate queue.

Adds:
  - figure_build_jobs table (separate from figure_jobs — new generator queue)

Run: python scripts/ch5_migration.py
"""

import os
import sys
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from sqlalchemy import inspect, text


def backup_db():
    """Create a timestamped copy of the database before migration."""
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           'instance', 'formyla.db')
    if not os.path.exists(db_path):
        print("[CH5_MIGRATION] formyla.db not found, skipping backup")
        return
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                              'backups')
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f'formyla.db.bak_CH5_{ts}.db')
    shutil.copy2(db_path, backup_path)
    print(f"[CH5_MIGRATION] backup created: {backup_path}")


def migrate():
    with app.app_context():
        inspector = inspect(db.engine)
        existing = inspector.get_table_names()

        if 'figure_build_jobs' in existing:
            print("[CH5_MIGRATION] figure_build_jobs table already exists, skipping")
            return

        is_pg = os.environ.get('DATABASE_URL', '').startswith('postgresql')

        if is_pg:
            db.session.execute(text("""
                CREATE TABLE figure_build_jobs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    problem_text TEXT NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'queued',
                    model_name VARCHAR(120),
                    svg_path TEXT,
                    error TEXT,
                    credit_charged BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            db.session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_figure_build_jobs_status "
                "ON figure_build_jobs(status)"
            ))
            db.session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_figure_build_jobs_user_id "
                "ON figure_build_jobs(user_id)"
            ))
            db.session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_figure_build_jobs_created_at "
                "ON figure_build_jobs(created_at)"
            ))
        else:
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS figure_build_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    problem_text TEXT NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'queued',
                    model_name VARCHAR(120),
                    svg_path TEXT,
                    error TEXT,
                    credit_charged BOOLEAN NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_figure_build_jobs_status "
                "ON figure_build_jobs(status)"
            ))
            db.session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_figure_build_jobs_user_id "
                "ON figure_build_jobs(user_id)"
            ))
            db.session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_figure_build_jobs_created_at "
                "ON figure_build_jobs(created_at)"
            ))

        db.session.commit()
        print("[CH5_MIGRATION] created figure_build_jobs table")


if __name__ == '__main__':
    backup_db()
    migrate()
    print("[CH5_MIGRATION] done")
