# -*- coding: utf-8 -*-
"""P1 migration: add theme_id + theme_title to adaptive_tasks and populate from JSONL."""
import json
import sqlite3
import os
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), 'formyla.db')
JSONL_PATH = os.path.join(os.path.dirname(__file__), 'FORMYLA_L1_L5_TOP5.jsonl')


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Check existing columns
    cur.execute("PRAGMA table_info(adaptive_tasks)")
    existing = {col[1] for col in cur.fetchall()}
    print(f"Existing columns: theme_id={'theme_id' in existing}, theme_title={'theme_title' in existing}")

    # 2. Add columns if missing
    for col in ['theme_id', 'theme_title']:
        if col not in existing:
            print(f"Adding column: {col}")
            col_type = 'VARCHAR(50)' if col == 'theme_id' else 'VARCHAR(300)'
            cur.execute(f"ALTER TABLE adaptive_tasks ADD COLUMN {col} {col_type}")
            conn.commit()

    # 3. Build task_uid -> (theme_id, theme_title) from JSONL
    uid_to_theme = {}
    print(f"Loading JSONL: {JSONL_PATH}")
    with open(JSONL_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                d = json.loads(line)
                uid = d.get('task_uid', '')
                tid = d.get('theme_id', '')
                title = d.get('theme', '')
                if uid and tid and title and uid not in uid_to_theme:
                    uid_to_theme[uid] = (tid, title)
            except json.JSONDecodeError:
                continue
    print(f"Loaded {len(uid_to_theme)} unique task_uid -> theme mappings from JSONL")

    # 4. Update adaptive_tasks where source_id matches task_uid
    # First check how many have source_id
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE source_id IS NOT NULL AND source_id != ''")
    total_with_source_id = cur.fetchone()[0]
    print(f"Rows with source_id: {total_with_source_id}")

    filled = 0
    not_found = 0
    batch = []
    BATCH_SIZE = 500

    cur.execute("SELECT id, source_id FROM adaptive_tasks WHERE source_id IS NOT NULL AND source_id != ''")
    for row_id, source_id in cur.fetchall():
        if source_id in uid_to_theme:
            tid, title = uid_to_theme[source_id]
            batch.append((tid, title, row_id))
            filled += 1
        else:
            not_found += 1

        if len(batch) >= BATCH_SIZE:
            cur.executemany(
                "UPDATE adaptive_tasks SET theme_id=?, theme_title=? WHERE id=?",
                batch
            )
            conn.commit()
            batch = []

    if batch:
        cur.executemany(
            "UPDATE adaptive_tasks SET theme_id=?, theme_title=? WHERE id=?",
            batch
        )
        conn.commit()

    # 5. Report
    empty = total_with_source_id - filled
    print(f"\n=== MIGRATION REPORT ===")
    print(f"Total rows with source_id: {total_with_source_id}")
    print(f"Filled theme_id + theme_title: {filled}")
    print(f"Not found in JSONL: {not_found}")
    print(f"Empty after migration: {empty}")

    # Verify
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE theme_id IS NOT NULL AND theme_id != ''")
    with_theme = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE theme_title IS NOT NULL AND theme_title != ''")
    with_title = cur.fetchone()[0]
    print(f"Rows with theme_id: {with_theme}")
    print(f"Rows with theme_title: {with_title}")

    # Show sample
    cur.execute("SELECT id, source_id, theme_id, theme_title FROM adaptive_tasks WHERE theme_title IS NOT NULL LIMIT 5")
    for row in cur.fetchall():
        print(f"  id={row[0]}, source_id={row[1]}, theme_id={row[2]}, theme_title={row[3][:60]}")

    conn.close()
    print("\nDone.")


if __name__ == '__main__':
    main()
