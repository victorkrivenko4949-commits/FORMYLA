"""
Migrates ALL data from local SQLite (instance/formyla.db) to Render PostgreSQL.

Uses raw SQL approach (no SQLAlchemy models) for maximum reliability.

Usage:
    python scripts/migrate_to_postgres.py "EXTERNAL_POSTGRES_URL"

Get EXTERNAL URL from: Render Dashboard -> formyla-db -> Connect -> External tab.
"""
import os
import sys
import sqlite3

if len(sys.argv) < 2:
    print("ERROR: provide PostgreSQL URL as argument")
    print("Usage: python scripts/migrate_to_postgres.py POSTGRES_URL")
    sys.exit(1)

EXTERNAL = sys.argv[1]

if EXTERNAL.startswith('postgres://'):
    EXTERNAL = EXTERNAL.replace('postgres://', 'postgresql+psycopg://', 1)
elif EXTERNAL.startswith('postgresql://') and '+psycopg' not in EXTERNAL:
    EXTERNAL = EXTERNAL.replace('postgresql://', 'postgresql+psycopg://', 1)

os.environ['DATABASE_URL'] = EXTERNAL

print('Loading app...')
from app import app, db

src = sqlite3.connect('instance/formyla.db')
src.row_factory = sqlite3.Row

cur = src.cursor()
all_tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
print('Tables in SQLite:', all_tables)

with app.app_context():
    print('Creating all tables in Postgres...')
    db.create_all()

    from sqlalchemy import text, inspect
    insp = inspect(db.engine)
    pg_tables = insp.get_table_names()
    print('Tables in Postgres:', pg_tables)

    total_ok = 0
    total_fail = 0

    for table_name in all_tables:
        if table_name not in pg_tables:
            print('SKIP: ' + table_name + ' (not in Postgres)')
            continue

        rows = cur.execute('SELECT * FROM ' + table_name).fetchall()
        if not rows:
            print('EMPTY: ' + table_name)
            continue

        existing = db.session.execute(text('SELECT COUNT(*) FROM ' + table_name)).scalar()
        if existing > 0:
            print('SKIP: ' + table_name + ' (already has ' + str(existing) + ' rows)')
            continue

        ok = 0
        fail = 0
        for r in rows:
            d = dict(r)
            cols = list(d.keys())
            placeholders = ', '.join([':' + c for c in cols])
            sql = 'INSERT INTO ' + table_name + ' (' + ', '.join(cols) + ') VALUES (' + placeholders + ')'
            try:
                db.session.execute(text(sql), d)
                ok += 1
            except Exception as e:
                fail += 1
                if fail <= 3:
                    print('  err: ' + str(e)[:200])
        try:
            db.session.commit()
        except Exception as e:
            print('  COMMIT err: ' + str(e)[:200])
            db.session.rollback()
        total_ok += ok
        total_fail += fail
        print(table_name + ': OK=' + str(ok) + ' FAIL=' + str(fail))

    print('=' * 50)
    print('TOTAL: OK=' + str(total_ok) + ' FAIL=' + str(total_fail))
    print('DONE')