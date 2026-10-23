# -*- coding: utf-8 -*-
"""
Migration: add theme_id to adaptive_tasks, level_by_theme to curator_state.
Run once: python _migrate_theme.py
"""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'database.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Add theme_id to adaptive_tasks
    try:
        cur.execute("ALTER TABLE adaptive_tasks ADD COLUMN theme_id VARCHAR(50)")
        print("[MIG] Added adaptive_tasks.theme_id")
    except sqlite3.OperationalError as e:
        if 'duplicate column' in str(e).lower():
            print("[MIG] adaptive_tasks.theme_id already exists")
        else:
            print(f"[MIG] WARNING: {e}")

    # 1a. Create index
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS ix_adaptive_tasks_theme_id ON adaptive_tasks(theme_id)")
        print("[MIG] Created index on adaptive_tasks.theme_id")
    except sqlite3.OperationalError as e:
        print(f"[MIG] Index warning: {e}")

    # 2. Add level_by_theme to curator_state
    try:
        cur.execute("ALTER TABLE curator_state ADD COLUMN level_by_theme TEXT")
        print("[MIG] Added curator_state.level_by_theme")
    except sqlite3.OperationalError as e:
        if 'duplicate column' in str(e).lower():
            print("[MIG] curator_state.level_by_theme already exists")
        else:
            print(f"[MIG] WARNING: {e}")

    conn.commit()

    # 3. Fill theme_id from taxonomy data
    # Load taxonomy
    tax_path = os.path.join(os.path.dirname(__file__), 'l1_l3_generation', 'taxonomy_by_grade.json')
    if not os.path.exists(tax_path):
        print("[MIG] taxonomy_by_grade.json not found, skipping theme_id fill")
        conn.close()
        return

    with open(tax_path, 'r', encoding='utf-8') as f:
        taxonomy = json.load(f)

    # Build lookup: core_topic -> theme_id (first match per grade)
    # We need to match AdaptiveTask.topic (which is a Russian name) to theme_id
    # Strategy: use the theme field from taxonomy as matching key

    # Build topic_name -> theme_id mapping
    topic_to_theme = {}
    for grade_str, entries in taxonomy.get('grades', {}).items():
        for entry in entries:
            theme_name = entry.get('theme', '')
            theme_id = entry.get('theme_id', '')
            # Store with grade prefix for disambiguation
            key = f"{grade_str}:{theme_name}"
            topic_to_theme[key] = theme_id

            # Also store just the last part after last colon
            parts = theme_name.split(':')
            if len(parts) >= 2:
                short_key = f"{grade_str}:{parts[-1].strip()}"
                if short_key not in topic_to_theme:
                    topic_to_theme[short_key] = theme_id

    # Get all tasks without theme_id
    cur.execute("SELECT id, class_level, topic FROM adaptive_tasks WHERE theme_id IS NULL")
    rows = cur.fetchall()
    print(f"[MIG] {len(rows)} tasks without theme_id")

    filled = 0
    for task_id, class_level, topic in rows:
        if not topic:
            continue

        # Try exact match first
        theme_id = None
        grade_str = str(class_level) if class_level else ''

        # Try grade:topic exact match
        key = f"{grade_str}:{topic}"
        theme_id = topic_to_theme.get(key)

        # Try without grade prefix
        if not theme_id:
            for gk, tid in topic_to_theme.items():
                if gk.endswith(f":{topic}"):
                    theme_id = tid
                    break

        # Try partial match: topic contains theme name
        if not theme_id:
            topic_lower = topic.lower()
            for gk, tid in topic_to_theme.items():
                gk_name = gk.split(':', 1)[1] if ':' in gk else gk
                if gk_name.lower() in topic_lower or topic_lower in gk_name.lower():
                    theme_id = tid
                    break

        if theme_id:
            cur.execute("UPDATE adaptive_tasks SET theme_id = ? WHERE id = ?", (theme_id, task_id))
            filled += 1
            if filled % 100 == 0:
                print(f"[MIG] Filled {filled} tasks...")

    conn.commit()
    print(f"[MIG] Total filled: {filled}")

    # Count remaining
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE theme_id IS NULL")
    remaining = cur.fetchone()[0]
    print(f"[MIG] Remaining without theme_id: {remaining}")

    # Count total
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
    total = cur.fetchone()[0]
    print(f"[MIG] Total tasks: {total}, filled: {filled}, empty: {remaining}")

    conn.close()

if __name__ == '__main__':
    migrate()
