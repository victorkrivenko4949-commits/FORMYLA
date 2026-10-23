# -*- coding: utf-8 -*-
"""
T8: Create streak_records table.

Idempotent: IF NOT EXISTS.
"""
import sqlite3
import os
import sys

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'formyla.db')

SQL = """
CREATE TABLE IF NOT EXISTS streak_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    current_streak INTEGER NOT NULL DEFAULT 0,
    max_streak INTEGER NOT NULL DEFAULT 0,
    days_off_available INTEGER NOT NULL DEFAULT 0,
    last_solved_date DATE,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

def run():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(SQL)
        conn.commit()
        print("T8: streak_records table created (or already exists).")
    except Exception as exc:
        print(f"T8 migration error: {exc}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    run()
