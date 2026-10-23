# -*- coding: utf-8 -*-
"""t7_migration — create curator_plan_items, user_subtopic_assignments,
add current_month to users."""
import sqlite3
import os
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'instance', 'formyla.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Table 1: curator_plan_items
    c.execute('''
        CREATE TABLE IF NOT EXISTS curator_plan_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subtopic TEXT NOT NULL,
            month_number INTEGER NOT NULL,
            position INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(month_number, position)
        )
    ''')

    # Table 2: user_subtopic_assignments
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_subtopic_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            subtopic TEXT NOT NULL,
            month_number INTEGER NOT NULL,
            position INTEGER NOT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, month_number, position)
        )
    ''')

    # Column: users.current_month
    col_exists = c.execute(
        "SELECT 1 FROM pragma_table_info('users') WHERE name='current_month'"
    ).fetchone()
    if not col_exists:
        c.execute("ALTER TABLE users ADD COLUMN current_month INTEGER DEFAULT 1")
        print("[t7] Added users.current_month DEFAULT 1")

    conn.commit()
    conn.close()
    print("[t7] Migration complete: curator_plan_items, user_subtopic_assignments, users.current_month")

if __name__ == '__main__':
    migrate()
