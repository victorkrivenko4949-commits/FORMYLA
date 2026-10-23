# -*- coding: utf-8 -*-
"""Idempotent migration: WhatsApp-style features for direct_messages.

Adds columns:
  - reply_to_id INTEGER NULL  (FK direct_messages.id, soft)
  - edited_at TIMESTAMP NULL
  - deleted_at TIMESTAMP NULL
  - forwarded_from_id INTEGER NULL

Safe to run multiple times. Works on SQLite and PostgreSQL.
"""
from sqlalchemy import inspect, text


def _has_column(conn, table, column):
    insp = inspect(conn)
    try:
        cols = [c["name"] for c in insp.get_columns(table)]
    except Exception:
        return False
    return column in cols


def run(db):
    conn = db.session.connection()
    bind = db.engine
    dialect = bind.dialect.name  # 'sqlite' or 'postgresql'

    table = "direct_messages"
    cols = [
        ("reply_to_id", "INTEGER NULL"),
        ("edited_at", "TIMESTAMP NULL"),
        ("deleted_at", "TIMESTAMP NULL"),
        ("forwarded_from_id", "INTEGER NULL"),
    ]
    added = []
    for name, typ in cols:
        if _has_column(bind, table, name):
            continue
        sql = f"ALTER TABLE {table} ADD COLUMN {name} {typ}"
        try:
            conn.execute(text(sql))
            db.session.commit()
            added.append(name)
        except Exception as e:
            db.session.rollback()
            print(f"[migration add_chat_features] failed to add {name}: {e}")

    if added:
        print(f"[migration add_chat_features] added columns: {added}")
    else:
        print("[migration add_chat_features] schema already up to date")
