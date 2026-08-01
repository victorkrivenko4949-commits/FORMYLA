"""Restore adaptive_tasks from root formyla.db to instance/formyla.db."""
import sqlite3
import os
import datetime
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DB = os.path.join(ROOT, 'formyla.db')
INST_DB = os.path.join(ROOT, 'instance', 'formyla.db')

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")

# 1. Backup instance DB
backup_path = os.path.join(ROOT, 'backups', f'instance_before_restore_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
os.makedirs(os.path.dirname(backup_path), exist_ok=True)
shutil.copy2(INST_DB, backup_path)
log(f"Backup: {backup_path}")

# 2. Count BEFORE
conn_inst = sqlite3.connect(INST_DB)
conn_root = sqlite3.connect(ROOT_DB)
ci = conn_inst.cursor()
cr = conn_root.cursor()

ci.execute("SELECT COUNT(*) FROM adaptive_tasks")
before = ci.fetchone()[0]
cr.execute("SELECT COUNT(*) FROM adaptive_tasks")
root_count = cr.fetchone()[0]
log(f"BEFORE: instance={before}, root={root_count}")

# 3. Get column info
ci.execute("PRAGMA table_info('adaptive_tasks')")
inst_cols = [c[1] for c in ci.fetchall()]
inst_cols_set = set(inst_cols)

cr.execute("PRAGMA table_info('adaptive_tasks')")
root_cols = [c[1] for c in cr.fetchall()]
root_cols_set = set(root_cols)

common_cols = [c for c in root_cols if c in inst_cols_set]
instance_only = [c for c in inst_cols if c not in root_cols_set]
root_only = [c for c in root_cols if c not in inst_cols_set]

log(f"Common columns ({len(common_cols)}): {common_cols}")
log(f"Instance-only (will be NULL for new rows): {instance_only}")
log(f"Root-only (will be skipped): {root_only}")

# 4. Add difficulty_level_src to instance if missing
if 'difficulty_level_src' not in inst_cols_set:
    log("Adding difficulty_level_src column to instance...")
    ci.execute("ALTER TABLE adaptive_tasks ADD COLUMN difficulty_level_src INTEGER")
    conn_inst.commit()
    common_cols.append('difficulty_level_src')
    log("  [OK] Added")

# 5. Read root rows
cols_str = ', '.join(f'"{c}"' for c in common_cols)
placeholders = ', '.join('?' * len(common_cols))
cr.execute(f'SELECT {cols_str} FROM adaptive_tasks ORDER BY id')
root_rows = cr.fetchall()
log(f"Read {len(root_rows)} rows from root")

# 6. INSERT OR IGNORE
insert_sql = f'INSERT OR IGNORE INTO adaptive_tasks ({cols_str}) VALUES ({placeholders})'
inserted = 0
skipped = 0
for row in root_rows:
    try:
        ci.execute(insert_sql, row)
        if ci.rowcount > 0:
            inserted += 1
        else:
            skipped += 1
    except Exception as e:
        log(f"ERROR on row {row[0]}: {e}")

conn_inst.commit()
log(f"Inserted: {inserted}, Skipped (already exist): {skipped}")

# 7. Verify
ci.execute("SELECT COUNT(*) FROM adaptive_tasks")
after = ci.fetchone()[0]
log(f"AFTER: instance={after}")

# 8. Breakdown
ci.execute("SELECT class_level, difficulty_level, COUNT(*) FROM adaptive_tasks GROUP BY class_level, difficulty_level ORDER BY class_level, difficulty_level")
log("GRADE/LEVEL breakdown:")
for r in ci.fetchall():
    log(f"  grade={r[0]} level={r[1]}: {r[2]}")

# 9. Count other tables (should be unchanged)
for table in ['users', 'task_assignment_history', 'task_solutions', 'curator_state']:
    try:
        ci.execute(f"SELECT COUNT(*) FROM {table}")
        log(f"  {table}: {ci.fetchone()[0]}")
    except:
        log(f"  {table}: N/A")

conn_inst.close()
conn_root.close()
log("DONE")
