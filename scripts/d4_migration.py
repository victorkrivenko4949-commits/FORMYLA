# -*- coding: utf-8 -*-
"""
D4 Migration: figure credits, transaction journal, email subscriptions.

Adds:
  - users.figure_credits (INT, default 3)
  - users.figures_built (INT, default 0)
  - figure_generations table
  - figure_credit_transactions table
  - figure_email_subscriptions table

V11: Uses schema_migration_log for idempotent re-runs.
Run: python scripts/d4_migration.py
"""

import os
import sys
import shutil
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db

MIGRATION_NAME = 'd4_migration.py'


def backup_db():
    """Create a timestamped copy of the database before migration."""
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database.db')
    if not os.path.exists(db_path):
        print("[D4_MIGRATION] database.db not found, skipping backup")
        return
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f'database_backup_d4_{ts}.db')
    shutil.copy2(db_path, backup_path)
    print(f"[D4_MIGRATION] backup created: {backup_path}")


def migrate():
    with app.app_context():
        # V11: Check migration log first
        from services.migration_log import is_migration_applied, register_migration
        if is_migration_applied(MIGRATION_NAME):
            print(f"[D4_MIGRATION] {MIGRATION_NAME} already recorded, skipping")
            return

        # 1. Add figure_credits and figures_built to users
        cols = []
        try:
            result = db.session.execute("PRAGMA table_info('users')")
            cols = [row[1] for row in result.fetchall()]
        except Exception:
            pass

        new_cols = {
            'figure_credits': "ALTER TABLE users ADD COLUMN figure_credits INTEGER NOT NULL DEFAULT 3",
            'figures_built': "ALTER TABLE users ADD COLUMN figures_built INTEGER NOT NULL DEFAULT 0",
        }

        for col_name, sql in new_cols.items():
            if col_name not in cols:
                try:
                    db.session.execute(db.text(sql))
                    print(f"[D4_MIGRATION] added column: users.{col_name}")
                except Exception as e:
                    print(f"[D4_MIGRATION] warning adding {col_name}: {e}")

        # 2. Create new tables
        tables_sql = {
            'figure_generations': """
                CREATE TABLE IF NOT EXISTS figure_generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER REFERENCES users(id),
                    problem_sha256 VARCHAR(64) NOT NULL,
                    problem TEXT NOT NULL,
                    solution TEXT,
                    status VARCHAR(20) NOT NULL DEFAULT 'ok',
                    json_description TEXT,
                    model VARCHAR(120),
                    cost_usd FLOAT NOT NULL DEFAULT 0.0,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """,
            'figure_credit_transactions': """
                CREATE TABLE IF NOT EXISTS figure_credit_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    amount INTEGER NOT NULL,
                    reason VARCHAR(64) NOT NULL,
                    reference VARCHAR(128),
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """,
            'figure_email_subscriptions': """
                CREATE TABLE IF NOT EXISTS figure_email_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email VARCHAR(200) NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """,
        }

        existing_tables = []
        try:
            result = db.session.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = [row[0] for row in result.fetchall()]
        except Exception:
            pass

        for table_name, sql in tables_sql.items():
            if table_name not in existing_tables:
                try:
                    db.session.execute(db.text(sql))
                    print(f"[D4_MIGRATION] created table: {table_name}")
                except Exception as e:
                    print(f"[D4_MIGRATION] error creating {table_name}: {e}")

        # 3. Create indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS ix_figure_generations_user_id ON figure_generations(user_id)",
            "CREATE INDEX IF NOT EXISTS ix_figure_generations_problem_sha256 ON figure_generations(problem_sha256)",
            "CREATE INDEX IF NOT EXISTS ix_figure_generations_status ON figure_generations(status)",
            "CREATE INDEX IF NOT EXISTS ix_figure_generations_created_at ON figure_generations(created_at)",
            "CREATE INDEX IF NOT EXISTS ix_figure_credit_transactions_user_id ON figure_credit_transactions(user_id)",
            "CREATE INDEX IF NOT EXISTS ix_figure_credit_transactions_reason ON figure_credit_transactions(reason)",
            "CREATE INDEX IF NOT EXISTS ix_figure_credit_transactions_created_at ON figure_credit_transactions(created_at)",
            "CREATE INDEX IF NOT EXISTS ix_figure_email_subscriptions_email ON figure_email_subscriptions(email)",
        ]

        for idx_sql in indexes:
            try:
                db.session.execute(db.text(idx_sql))
            except Exception as e:
                print(f"[D4_MIGRATION] warning creating index: {e}")

        # 4. Credit existing users with 3 credits if they don't have any
        try:
            from models import User
            users = User.query.filter(User.figure_credits == None).all()  # noqa
            for u in users:
                u.figure_credits = 3
            db.session.commit()
            print(f"[D4_MIGRATION] credited {len(users)} existing users with 3 credits")
        except Exception as e:
            print(f"[D4_MIGRATION] warning crediting users: {e}")
            db.session.rollback()

        db.session.commit()
        register_migration(MIGRATION_NAME)
        print("[D4_MIGRATION] migration complete")


if __name__ == '__main__':
    backup_db()
    migrate()
