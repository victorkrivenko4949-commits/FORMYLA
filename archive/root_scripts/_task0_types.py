import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
conn = sqlite3.connect('formyla.db')
conn.row_factory = sqlite3.Row

print("=== task_type distribution in adaptive_tasks ===")
rows = conn.execute("""
    SELECT task_type, count(*) cnt FROM adaptive_tasks
    WHERE task_type IS NOT NULL
    GROUP BY task_type ORDER BY cnt DESC
""").fetchall()
for r in rows:
    print(f"  {r['task_type']}: {r['cnt']}")

rows = conn.execute("""
    SELECT count(*) FROM adaptive_tasks WHERE task_type IS NULL
""").fetchone()
print(f"NULL task_type: {rows[0]}")

# Also: what tasks are actually used as anchors?
print("\n=== Anchor tasks in adaptive_tasks ===")
rows = conn.execute("""
    SELECT difficulty_level, class_level, count(*) cnt
    FROM adaptive_tasks
    WHERE task_type = 'anchor'
    GROUP BY difficulty_level, class_level
    ORDER BY difficulty_level, class_level
""").fetchall()
for r in rows:
    print(f"  lvl={r['difficulty_level']} class={r['class_level']} cnt={r['cnt']}")

print("\n=== All tasks (non-anchor) ===")
rows = conn.execute("""
    SELECT difficulty_level, class_level, count(*) cnt
    FROM adaptive_tasks
    WHERE task_type IS NULL OR task_type != 'anchor'
    GROUP BY difficulty_level, class_level
    ORDER BY difficulty_level, class_level
""").fetchall()
for r in rows:
    print(f"  lvl={r['difficulty_level']} class={r['class_level']} cnt={r['cnt']}")

conn.close()
