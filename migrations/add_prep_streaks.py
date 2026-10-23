# -*- coding: utf-8 -*-
"""
Migration: Add streak fields to prep_plans table.
Run: python migrations/add_prep_streaks.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db


def migrate():
    """Add current_streak, longest_streak, last_solved_date to prep_plans."""
    with app.app_context():
        print("Adding streak columns to prep_plans...")
        from sqlalchemy import text, inspect

        inspector = inspect(db.engine)
        existing = [c['name'] for c in inspector.get_columns('prep_plans')]

        stmts = []
        if 'current_streak' not in existing:
            stmts.append("ALTER TABLE prep_plans ADD COLUMN current_streak INTEGER NOT NULL DEFAULT 0")
        if 'longest_streak' not in existing:
            stmts.append("ALTER TABLE prep_plans ADD COLUMN longest_streak INTEGER NOT NULL DEFAULT 0")
        if 'last_solved_date' not in existing:
            stmts.append("ALTER TABLE prep_plans ADD COLUMN last_solved_date DATE")

        if not stmts:
            print("All streak columns already exist. Nothing to do.")
            return

        for stmt in stmts:
            db.session.execute(text(stmt))
            print("  " + stmt)
        db.session.commit()
        print("Done. Streak columns added.")


if __name__ == '__main__':
    migrate()
