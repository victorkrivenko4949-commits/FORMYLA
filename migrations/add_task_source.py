# -*- coding: utf-8 -*-
"""
Migration: Add source, source_url, original_difficulty to adaptive_tasks.
Run: python migrations/add_task_source.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db


def migrate():
    with app.app_context():
        print("Adding source columns to adaptive_tasks...")
        from sqlalchemy import text, inspect

        inspector = inspect(db.engine)
        existing = [c['name'] for c in inspector.get_columns('adaptive_tasks')]

        stmts = []
        if 'source' not in existing:
            stmts.append("ALTER TABLE adaptive_tasks ADD COLUMN source VARCHAR(50) DEFAULT 'deepseek'")
        if 'source_url' not in existing:
            stmts.append("ALTER TABLE adaptive_tasks ADD COLUMN source_url VARCHAR(500)")
        if 'original_difficulty' not in existing:
            stmts.append("ALTER TABLE adaptive_tasks ADD COLUMN original_difficulty VARCHAR(50)")

        if not stmts:
            print("All source columns already exist.")
            return

        for stmt in stmts:
            db.session.execute(text(stmt))
            print("  " + stmt)
        db.session.commit()
        print("Done.")


if __name__ == '__main__':
    migrate()
