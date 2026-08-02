"""Compare bank (grade_tasks) BEFORE vs AFTER migration using bak_v8bank."""
import sqlite3, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def header(s):
    print(f"\n{'='*60}\n{s}\n{'='*60}")

# --- BEFORE migration (v8bank) ---
bak = sqlite3.connect('formyla.db.bak_v8bank')
bak.row_factory = sqlite3.Row

header("BEFORE MIGRATION: grade_tasks in formyla.db.bak_v8bank")

# Level distribution
rows = bak.execute("""
    SELECT level, grade, count(*) cnt
    FROM grade_tasks
    GROUP BY level, grade
    ORDER BY level, grade
""").fetchall()
print("grade_tasks: level × grade distribution BEFORE:")
for r in rows:
    print(f"  level={r['level']} grade={r['grade']} cnt={r['cnt']}")

# Total
total = bak.execute("SELECT count(*) FROM grade_tasks").fetchone()[0]
print(f"\nTotal grade_tasks BEFORE: {total}")

# Check if levels 6,7 exist
for lvl in [6, 7]:
    cnt = bak.execute("SELECT count(*) FROM grade_tasks WHERE level=?", [lvl]).fetchone()[0]
    print(f"  level={lvl}: {cnt} tasks")

# Samples from each level 1..7
header("BEFORE: 3 samples from each level (1-7)")
for lvl in range(1, 8):
    rows = bak.execute("""
        SELECT id, grade, level, topic, substr(statement,1,100) stmt,
               length(solution) sol_len, length(statement) stmt_len, status
        FROM grade_tasks WHERE level=?
        ORDER BY id LIMIT 3
    """, [lvl]).fetchall()
    print(f"\n--- Level {lvl} ({len(rows)} samples) ---")
    if not rows:
        print("  (empty)")
    for r in rows:
        print(f"  id={r['id']} grade={r['grade']} topic={r['topic']} "
              f"sol_len={r['sol_len']} stmt_len={r['stmt_len']} status={r['status']}")
        print(f"    stmt: {r['stmt']}")

# Solution length stats by level
header("BEFORE: solution length stats by level")
rows = bak.execute("""
    SELECT level, count(*) cnt,
           avg(length(solution)) avg_sol,
           avg(length(statement)) avg_stmt
    FROM grade_tasks WHERE solution IS NOT NULL
    GROUP BY level ORDER BY level
""").fetchall()
for r in rows:
    print(f"  level={r['level']} cnt={r['cnt']} avg_sol={r['avg_sol']:.0f} avg_stmt={r['avg_stmt']:.0f}")

# --- NOW: grade_tasks source_id pattern ---
header("BEFORE: source_id patterns")
rows = bak.execute("""
    SELECT source_id, level, grade
    FROM grade_tasks
    ORDER BY level, id LIMIT 5
""").fetchall()
for r in rows:
    print(f"  {r['source_id']} level={r['level']} grade={r['grade']}")

# adaptive_tasks in bak
header("BEFORE: adaptive_tasks difficulty_level_src distribution")
rows = bak.execute("""
    SELECT difficulty_level_src, difficulty_level, count(*) cnt
    FROM adaptive_tasks
    GROUP BY difficulty_level_src, difficulty_level
    ORDER BY difficulty_level_src
""").fetchall()
print("adaptive_tasks src → current mapping BEFORE:")
for r in rows:
    print(f"  src={r['difficulty_level_src']} cur={r['difficulty_level']} cnt={r['cnt']}")

bak.close()

# --- AFTER migration ---
now = sqlite3.connect('formyla.db')
now.row_factory = sqlite3.Row

header("AFTER MIGRATION: grade_tasks in formyla.db")
rows = now.execute("""
    SELECT level, grade, count(*) cnt
    FROM grade_tasks GROUP BY level, grade ORDER BY level, grade
""").fetchall()
print("grade_tasks: level × grade AFTER:")
for r in rows:
    print(f"  level={r['level']} grade={r['grade']} cnt={r['cnt']}")

total = now.execute("SELECT count(*) FROM grade_tasks").fetchone()[0]
print(f"\nTotal grade_tasks AFTER: {total}")

# Samples after
header("AFTER: 3 samples from each level (1-5)")
for lvl in range(1, 6):
    rows = now.execute("""
        SELECT id, grade, level, topic, substr(statement,1,100) stmt,
               length(solution) sol_len, status
        FROM grade_tasks WHERE level=?
        ORDER BY id LIMIT 3
    """, [lvl]).fetchall()
    print(f"\n--- Level {lvl} ({len(rows)} samples) ---")
    for r in rows:
        print(f"  id={r['id']} grade={r['grade']} topic={r['topic']} "
              f"sol_len={r['sol_len']} status={r['status']}")
        print(f"    stmt: {r['stmt']}")

# Solution length stats after
header("AFTER: solution length stats by level")
rows = now.execute("""
    SELECT level, count(*) cnt,
           avg(length(solution)) avg_sol,
           avg(length(statement)) avg_stmt
    FROM grade_tasks WHERE solution IS NOT NULL
    GROUP BY level ORDER BY level
""").fetchall()
for r in rows:
    print(f"  level={r['level']} cnt={r['cnt']} avg_sol={r['avg_sol']:.0f} avg_stmt={r['avg_stmt']:.0f}")

# adaptive_tasks in now
header("AFTER: adaptive_tasks distribution")
rows = now.execute("""
    SELECT difficulty_level, difficulty_level_src, count(*) cnt
    FROM adaptive_tasks
    GROUP BY difficulty_level, difficulty_level_src
    ORDER BY difficulty_level
""").fetchall()
print("adaptive_tasks cur → src AFTER:")
for r in rows:
    print(f"  cur={r['difficulty_level']} src={r['difficulty_level_src']} cnt={r['cnt']}")

now.close()
print("\nDone.")
