"""STEP 5: Deduplicate task pairs — merge history to smaller id, delete larger id."""
import sqlite3, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, 'instance', 'formyla.db')

PAIRS = [
    (5316, 7945),
    (5493, 7981),
    (5892, 5911),
    (5843, 5899),
    (5166, 5185),
]

con = sqlite3.connect(DB)
cur = con.cursor()

# Disable FK checks temporarily
cur.execute("PRAGMA foreign_keys = OFF")

total_moved = 0

for keep_id, remove_id in PAIRS:
    print(f"\n=== Pair: keep={keep_id}, remove={remove_id} ===")
    
    # Check both exist
    cur.execute("SELECT id, class_level, difficulty_level, subject FROM adaptive_tasks WHERE id IN (?, ?)",
                (keep_id, remove_id))
    rows = cur.fetchall()
    print(f"  Tasks: {rows}")
    
    if len(rows) < 2:
        print("  SKIP: one task missing")
        continue
    
    # Move task_solutions: update task_id from remove_id → keep_id
    # First check for conflicts: same user_id has both keep and remove
    cur.execute("""
        SELECT user_id FROM task_solutions WHERE task_id = ?
        INTERSECT
        SELECT user_id FROM task_solutions WHERE task_id = ?
    """, (keep_id, remove_id))
    conflicts = cur.fetchall()
    
    if conflicts:
        print(f"  Conflicts (user has both tasks): {len(conflicts)} users")
        # Delete the remove_id solutions where user also has keep_id
        for (uid,) in conflicts:
            cur.execute("DELETE FROM task_solutions WHERE user_id=? AND task_id=?", (uid, remove_id))
            print(f"    Deleted solution for user={uid} task={remove_id} (duplicate)")
    
    # Now update remaining remove_id → keep_id
    cur.execute("UPDATE task_solutions SET task_id = ? WHERE task_id = ?", (keep_id, remove_id))
    n_sol = cur.rowcount
    print(f"  task_solutions rows moved: {n_sol}")
    
    # Move task_assignment_history
    cur.execute("""
        SELECT user_id FROM task_assignment_history WHERE task_id = ?
        INTERSECT
        SELECT user_id FROM task_assignment_history WHERE task_id = ?
    """, (keep_id, remove_id))
    hist_conflicts = cur.fetchall()
    
    if hist_conflicts:
        print(f"  History conflicts: {len(hist_conflicts)} users")
        for (uid,) in hist_conflicts:
            cur.execute("DELETE FROM task_assignment_history WHERE user_id=? AND task_id=?", (uid, remove_id))
    
    cur.execute("UPDATE task_assignment_history SET task_id = ? WHERE task_id = ?", (keep_id, remove_id))
    n_hist = cur.rowcount
    print(f"  task_assignment_history rows moved: {n_hist}")
    
    # Delete the duplicate task
    cur.execute("DELETE FROM adaptive_tasks WHERE id = ?", (remove_id,))
    print(f"  Deleted adaptive_tasks id={remove_id}: {cur.rowcount}")
    
    total_moved += n_sol + n_hist

con.commit()

# Final stats
cur.execute("SELECT COUNT(*) FROM task_solutions")
print(f"\n=== FINAL ===")
print(f"  task_solutions total: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM task_assignment_history")
print(f"  task_assignment_history total: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(DISTINCT user_id), COUNT(DISTINCT task_id) FROM task_assignment_history")
r = cur.fetchone()
print(f"  distinct users in history: {r[0]}, distinct tasks: {r[1]}")
cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
print(f"  adaptive_tasks total: {cur.fetchone()[0]}")
print(f"  Total rows moved: {total_moved}")

con.close()
