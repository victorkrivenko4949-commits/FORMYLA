#!/usr/bin/env python3
"""
Migration: Drop legacy duplicate columns from daily_variants.

Duplicates found:
  - stack VARCHAR(5)        vs  generation_stack VARCHAR(1)  -> keep generation_stack
  - total_cost REAL         vs  total_cost_usd REAL          -> keep total_cost_usd

SQLite doesn't support DROP COLUMN before 3.35.0, so we recreate the table.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_migration():
    from app import app
    with app.app_context():
        from models import db
        import sqlite3

        # Check SQLite version for DROP COLUMN support
        sqlite_version = sqlite3.sqlite_version_info
        print(f"SQLite version: {sqlite3.sqlite_version}")

        if sqlite_version >= (3, 35, 0):
            # Modern SQLite: just DROP COLUMN
            try:
                db.session.execute(db.text("ALTER TABLE daily_variants DROP COLUMN stack"))
                print("  Dropped column: stack")
            except Exception as e:
                print(f"  stack: {e}")

            try:
                db.session.execute(db.text("ALTER TABLE daily_variants DROP COLUMN total_cost"))
                print("  Dropped column: total_cost")
            except Exception as e:
                print(f"  total_cost: {e}")

            db.session.commit()
        else:
            # Old SQLite: recreate table
            print("  SQLite < 3.35.0, using table recreation...")

            # Get current data
            rows = db.session.execute(db.text("SELECT * FROM daily_variants")).fetchall()
            cols = db.session.execute(db.text("PRAGMA table_info(daily_variants)")).fetchall()
            col_names = [c[1] for c in cols]
            print(f"  Current columns: {col_names}")

            # Columns to keep (remove 'stack' and 'total_cost')
            keep_cols = [c for c in col_names if c not in ('stack', 'total_cost')]
            print(f"  Keeping columns: {keep_cols}")

            # Recreate
            db.session.execute(db.text("ALTER TABLE daily_variants RENAME TO daily_variants_old"))

            db.session.execute(db.text("""
                CREATE TABLE daily_variants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    olympiad_slug VARCHAR(50) NOT NULL,
                    olympiad_title VARCHAR(200),
                    grade INTEGER NOT NULL,
                    round VARCHAR(30) NOT NULL,
                    round_title VARCHAR(200),
                    variant_date DATE NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    generation_stack VARCHAR(1) DEFAULT 'A',
                    quality_report TEXT,
                    meta_review TEXT,
                    total_cost_usd REAL DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    approved_at DATETIME,
                    UNIQUE(olympiad_slug, grade, round, variant_date)
                )
            """))

            # Copy data
            cols_str = ", ".join(keep_cols)
            db.session.execute(db.text(f"INSERT INTO daily_variants ({cols_str}) SELECT {cols_str} FROM daily_variants_old"))
            db.session.execute(db.text("DROP TABLE daily_variants_old"))
            db.session.commit()
            print("  Table recreated successfully")

        # Verify
        final_cols = db.session.execute(db.text("PRAGMA table_info(daily_variants)")).fetchall()
        final_names = [c[1] for c in final_cols]
        print(f"\nFinal columns: {final_names}")

        assert 'stack' not in final_names, "stack column still exists!"
        assert 'total_cost' not in final_names, "total_cost column still exists!"
        assert 'generation_stack' in final_names, "generation_stack missing!"
        assert 'total_cost_usd' in final_names, "total_cost_usd missing!"

        row_count = db.session.execute(db.text("SELECT COUNT(*) FROM daily_variants")).fetchone()[0]
        print(f"Rows preserved: {row_count}")
        print("\nMigration complete!")


if __name__ == "__main__":
    run_migration()
