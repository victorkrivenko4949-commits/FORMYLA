# -*- coding: utf-8 -*-
"""
Migration: Add target_grade column to prep_plans.
Works with both SQLite and PostgreSQL.

Usage:
    python migrations/add_prep_target_grade.py [--pg]
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

    cur.execute("PRAGMA table_info(prep_plans)")
    cols = [r[1] for r in cur.fetchall()]

    if 'target_grade' not in cols:
        cur.execute("ALTER TABLE prep_plans ADD COLUMN target_grade INTEGER")
        print("  + prep_plans.target_grade")

        # Backfill from user.preferred_grade
        cur.execute("""
            UPDATE prep_plans SET target_grade = (
                SELECT COALESCE(u.preferred_grade, 9)
                FROM users u WHERE u.id = prep_plans.user_id
            ) WHERE target_grade IS NULL
        """)
        updated = cur.rowcount
        print(f"  Backfilled {updated} plans")
    else:
        print("  prep_plans.target_grade already exists")

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

    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'prep_plans' AND column_name = 'target_grade'
    """)
    if not cur.fetchone():
        cur.execute("ALTER TABLE prep_plans ADD COLUMN target_grade INTEGER")
        print("  + prep_plans.target_grade")

        # Backfill from user.preferred_grade
        cur.execute("""
            UPDATE prep_plans SET target_grade = COALESCE(
                (SELECT u.preferred_grade FROM users u WHERE u.id = prep_plans.user_id),
                9
            ) WHERE target_grade IS NULL
        """)
        print(f"  Backfilled existing plans")
    else:
        print("  prep_plans.target_grade already exists")

    cur.close()
    conn.close()
    print("PostgreSQL migration complete.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pg', action='store_true', help='Migrate production PostgreSQL')
    args = parser.parse_args()

    print("=== Migration: prep_plans.target_grade ===")
    migrate_sqlite()
    if args.pg:
        migrate_pg()
    print("\nDone!")
