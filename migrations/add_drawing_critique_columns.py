# -*- coding: utf-8 -*-
# Migration: add Gemini-critic columns to drawing_generations.
#
# Adds (all nullable / with defaults so existing rows stay valid):
#     critique_rounds         INTEGER  NOT NULL DEFAULT 0
#     critique_accepted       INTEGER  NOT NULL DEFAULT 0
#     critique_rejected       INTEGER  NOT NULL DEFAULT 0
#     critique_findings_json  TEXT     NULL
#
# Idempotent: each ALTER is guarded by a column-existence check.
#
# Usage:
#     python migrations/add_drawing_critique_columns.py            # local SQLite
#     python migrations/add_drawing_critique_columns.py --pg       # production PG

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# columns to add: (name, sql_type, nullable, default_expr or None)
NEW_COLUMNS = [
    ("critique_rounds",        "INTEGER", False, "0"),
    ("critique_accepted",      "INTEGER", False, "0"),
    ("critique_rejected",      "INTEGER", False, "0"),
    ("critique_findings_json", "TEXT",    True,  None),
]


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------
def _sqlite_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "instance",
        "formyla.db",
    )


def _sqlite_columns(cur, table):
    cur.execute("PRAGMA table_info(" + table + ")")
    return {row[1] for row in cur.fetchall()}


def migrate_sqlite():
    import sqlite3

    db_path = _sqlite_path()
    if not os.path.exists(db_path):
        print("SQLite DB not found: " + db_path)
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='drawing_generations'"
    )
    if not cur.fetchone():
        print("  drawing_generations does not exist — run "
              "add_drawing_generations.py first")
        conn.close()
        return

    existing = _sqlite_columns(cur, "drawing_generations")
    for name, sql_type, not_null, default in NEW_COLUMNS:
        if name in existing:
            print("  " + name + " already present, skipped")
            continue
        ddl = "ALTER TABLE drawing_generations ADD COLUMN " + name + " " + sql_type
        if not_null and default is not None:
            ddl += " NOT NULL DEFAULT " + default
        elif default is not None:
            ddl += " DEFAULT " + default
        cur.execute(ddl)
        print("  + " + name)

    conn.commit()
    conn.close()
    print("SQLite migration completed.")


# ---------------------------------------------------------------------------
# Postgres
# ---------------------------------------------------------------------------
def _load_env_migration():
    env_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".env",
    )
    if not os.path.exists(env_file):
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def migrate_pg():
    try:
        import psycopg
    except ImportError:
        print("psycopg not installed; skipping PG migration")
        return

    _load_env_migration()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL not set; skipping PG migration")
        return

    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass('public.drawing_generations')"
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                print("  public.drawing_generations does not exist — run "
                      "add_drawing_generations.py first")
                return

            for name, sql_type, not_null, default in NEW_COLUMNS:
                cur.execute(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='drawing_generations' "
                    "AND column_name=%s",
                    (name,),
                )
                if cur.fetchone():
                    print("  " + name + " already present, skipped")
                    continue
                ddl = ("ALTER TABLE drawing_generations ADD COLUMN "
                       + name + " " + sql_type)
                if default is not None:
                    ddl += " DEFAULT " + default
                if not_null:
                    ddl += " NOT NULL"
                cur.execute(ddl)
                print("  + " + name)

    print("Postgres migration completed.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pg",
        action="store_true",
        help="also run on PostgreSQL via DATABASE_URL",
    )
    args = parser.parse_args()

    print("=== add_drawing_critique_columns (SQLite) ===")
    migrate_sqlite()

    if args.pg:
        print()
        print("=== add_drawing_critique_columns (PostgreSQL) ===")
        migrate_pg()
