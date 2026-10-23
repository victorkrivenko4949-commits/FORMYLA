#!/usr/bin/env python3
"""Migration: Create olympiad_waitlist table for disabled grades/rounds."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_migration():
    from app import app
    with app.app_context():
        from models import db
        db.session.execute(db.text("""
            CREATE TABLE IF NOT EXISTS olympiad_waitlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                olympiad_slug VARCHAR(50) NOT NULL DEFAULT 'vsosh',
                grade INTEGER NOT NULL,
                round VARCHAR(30) NOT NULL,
                email VARCHAR(200),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, olympiad_slug, grade, round)
            )
        """))
        db.session.commit()
        print("Created olympiad_waitlist table")

        cols = db.session.execute(db.text("PRAGMA table_info(olympiad_waitlist)")).fetchall()
        print("Columns:", [c[1] for c in cols])


if __name__ == "__main__":
    run_migration()
