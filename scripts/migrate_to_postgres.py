"""
Migrates ALL data from local SQLite to Render PostgreSQL.
Auto-discovers tables and SQLAlchemy models via metadata registry.

Usage: python scripts/migrate_to_postgres.py [optional_url]
"""
import os
import sys
import sqlite3

# Add parent dir to path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_USER = "formyla_user"
DEFAULT_PASS = "HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGea"
DEFAULT_HOST = "dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com"
DEFAULT_DB = "formyla"
DEFAULT_URL = "postgresql://" + DEFAULT_USER + ":" + DEFAULT_PASS + "@" + DEFAULT_HOST + "/" + DEFAULT_DB

EXTERNAL = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL

# Apply same URL rewrite as app.py uses for psycopg3 driver
if EXTERNAL.startswith("postgres://"):
    EXTERNAL = EXTERNAL.replace("postgres://", "postgresql+psycopg://", 1)
elif EXTERNAL.startswith("postgresql://") and "+psycopg" not in EXTERNAL:
    EXTERNAL = EXTERNAL.replace("postgresql://", "postgresql+psycopg://", 1)

os.environ["DATABASE_URL"] = EXTERNAL
print("Target: " + EXTERNAL.split("@")[0] + "@***")

print("Loading app...")
from app import app, db

src = sqlite3.connect("instance/formyla.db")
src.row_factory = sqlite3.Row

table_names = [
    r[0] for r in src.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
]
print("SQLite tables: " + str(len(table_names)))

with app.app_context():
    print("Creating tables in Postgres...")
    db.create_all()

    # Build mapping table_name -> Model class via SQLAlchemy registry
    models_by_table = {}
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if hasattr(cls, "__tablename__"):
            models_by_table[cls.__tablename__] = cls

    print("Models: " + str(len(models_by_table)))

    total_ok = 0
    total_fail = 0

    for table in table_names:
        Model = models_by_table.get(table)
        if not Model:
            print("[" + table + "] no SQLAlchemy model, skip")
            continue

        rows = src.execute('SELECT * FROM "' + table + '"').fetchall()
        if not rows:
            print("[" + table + "] empty, skip")
            continue

        existing = db.session.query(Model).count()
        if existing > 0:
            print("[" + table + "] already has " + str(existing) + ", skip")
            continue

        ok = 0
        fail = 0
        for r in rows:
            data = {k: r[k] for k in r.keys()}
            try:
                db.session.add(Model(**data))
                ok += 1
            except Exception as e:
                db.session.rollback()
                # Try without id (let Postgres autogenerate)
                data.pop("id", None)
                try:
                    db.session.add(Model(**data))
                    ok += 1
                except Exception as e2:
                    fail += 1
                    if fail <= 3:
                        print("  err: " + str(e2)[:200])
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print("[" + table + "] commit err: " + str(e)[:200])

        total_ok += ok
        total_fail += fail
        print("[" + table + "] OK=" + str(ok) + " FAIL=" + str(fail))

    print("=" * 50)
    print("TOTAL: OK=" + str(total_ok) + " FAIL=" + str(total_fail))
    print("DONE")
