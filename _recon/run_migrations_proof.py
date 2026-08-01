"""Run all 6 migrations on a separate empty test DB, twice, to prove idempotency."""
import os
import sys
import subprocess
import datetime
import sqlite3

BASE = r"c:\Users\Redmi\Desktop\Новая папка (2)"
TEST_DB = os.path.join(BASE, "instance", "test_migration_4.db")

# Clean up previous
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)
for ext in ['-shm', '-wal']:
    p = TEST_DB + ext
    if os.path.exists(p):
        os.remove(p)

# Create fresh empty DB with schema
print("=== Creating fresh test DB ===")
# Copy instance schema only (no data)
WORK_DB = os.path.join(BASE, "instance", "formyla.db")
import shutil
shutil.copy2(WORK_DB, TEST_DB)
print(f"Test DB: {TEST_DB} ({os.path.getsize(TEST_DB)} bytes)")

# Clear all data from all tables
conn = sqlite3.connect(TEST_DB)
conn.execute("PRAGMA foreign_keys = OFF")
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
skip_tables = {'alembic_version', 'sqlite_sequence'}
for t in tables:
    if t in skip_tables:
        continue
    try:
        c.execute(f"DELETE FROM {t}")
        print(f"  Cleared {t}: {c.rowcount} rows")
    except Exception as e:
        print(f"  Skipped {t}: {e}")
conn.commit()
conn.close()
print("Test DB is now empty with full schema.")

# Count tasks before
conn = sqlite3.connect(TEST_DB)
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM adaptive_tasks")
before = c.fetchone()[0]
print(f"adaptive_tasks BEFORE: {before}")
conn.close()

# Verify working DB is untouched
conn = sqlite3.connect(WORK_DB)
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM adaptive_tasks")
work_before = c.fetchone()[0]
conn.close()
print(f"WORKING DB adaptive_tasks BEFORE: {work_before}")

env = os.environ.copy()
env['DATABASE_URL'] = f'sqlite:///{TEST_DB.replace(chr(92), "/")}'

MIGRATIONS = [
    ("1_scale", "scripts/migrate_8to5_scale.py"),
    ("2_history", "scripts/migrate_P2_task_assignment_history.py"),
    ("3_pool", "scripts/migrate_pool_to_instance.py"),
    ("4_debt", "scripts/p4_debt_migration.py"),
    ("5_intake", "scripts/p9_intake_migration.py"),
    ("6_import", "scripts/import_formyla_jsonl.py"),
]

for run_num in [1, 2]:
    print(f"\n{'='*60}")
    print(f"RUN #{run_num}")
    print(f"{'='*60}")
    
    for label, script in MIGRATIONS:
        script_path = os.path.join(BASE, script)
        if not os.path.exists(script_path):
            print(f"  SKIP {label}: {script} not found")
            continue
        
        print(f"\n--- {label} ({script}) ---")
        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                cwd=BASE,
                env=env,
                timeout=60
            )
            # Print last 10 lines
            lines = (result.stderr + result.stdout).strip().split('\n')
            for line in lines[-15:]:
                print(f"  {line}")
            if result.returncode != 0:
                print(f"  RETURN CODE: {result.returncode}")
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT after 60s")
        except Exception as e:
            print(f"  ERROR: {e}")

# Final check
print(f"\n{'='*60}")
print("FINAL VERIFICATION")
print(f"{'='*60}")

conn = sqlite3.connect(TEST_DB)
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM adaptive_tasks")
after = c.fetchone()[0]
print(f"TEST DB adaptive_tasks AFTER: {after}")

c.execute("PRAGMA table_info(adaptive_tasks)")
cols = [r[1] for r in c.fetchall()]
has_src = 'difficulty_level_src' in cols
print(f"  difficulty_level_src exists: {has_src}")

c.execute("PRAGMA table_info(daily_task_items)")
cols_dti = [r[1] for r in c.fetchall()]
print(f"  debt_status exists: {'debt_status' in cols_dti}")
print(f"  debt_until exists: {'debt_until' in cols_dti}")

c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_assignment_history'")
has_history = bool(c.fetchone())
print(f"  task_assignment_history exists: {has_history}")

conn.close()

# Verify working DB still untouched
conn = sqlite3.connect(WORK_DB)
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM adaptive_tasks")
work_after = c.fetchone()[0]
conn.close()
print(f"\nWORKING DB adaptive_tasks AFTER: {work_after}")
print(f"WORKING DB UNCHANGED: {work_before == work_after} ({work_before} -> {work_after})")

print("\nDONE")
