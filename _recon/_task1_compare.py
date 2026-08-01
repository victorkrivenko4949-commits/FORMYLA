# -*- coding: utf-8 -*-
"""TASK 1: Full comparison of root formyla.db vs instance/formyla.db"""
import sqlite3
import shutil
import os
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DB = os.path.join(BASE, 'formyla.db')
INSTANCE_DB = os.path.join(BASE, 'instance', 'formyla.db')
RECON_DIR = os.path.join(BASE, '_recon')

ts = datetime.now().strftime('%Y%m%d_%H%M%S')

print(f"BASE: {BASE}")
print(f"ROOT_DB: {ROOT_DB}  exists={os.path.exists(ROOT_DB)}")
print(f"INSTANCE_DB: {INSTANCE_DB}  exists={os.path.exists(INSTANCE_DB)}")

# ── Step 1: Copy both with timestamp ──
root_copy = os.path.join(RECON_DIR, f'root_formyla_{ts}.db')
instance_copy = os.path.join(RECON_DIR, f'instance_formyla_{ts}.db')

shutil.copy2(ROOT_DB, root_copy)
# Copy WAL/SHM too for instance
for ext in ['-wal', '-shm']:
    src = INSTANCE_DB + ext
    if os.path.exists(src):
        shutil.copy2(src, instance_copy + ext)

shutil.copy2(INSTANCE_DB, instance_copy)
for ext in ['-wal', '-shm']:
    # also for root
    src = ROOT_DB + ext
    if os.path.exists(src):
        shutil.copy2(src, root_copy + ext)

print(f"\nCopies made:")
print(f"  root    -> {root_copy}")
print(f"  instance -> {instance_copy}")

# ── Step 2: List all tables in both ──
def get_tables(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    conn.close()
    return tables

def get_row_count(db_path, table):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        n = cur.fetchone()[0]
    except Exception as e:
        n = f"ERR: {e}"
    conn.close()
    return n

root_tables = get_tables(root_copy)
instance_tables = get_tables(instance_copy)
all_tables = sorted(set(root_tables + instance_tables))

print("\n" + "="*80)
print("TABLE COMPARISON: root vs instance")
print("="*80)
print(f"{'Table':<40} {'Root':>10} {'Instance':>10} {'Diff':>10}")
print("-"*70)

for tbl in all_tables:
    in_root = tbl in root_tables
    in_inst = tbl in instance_tables
    r_cnt = get_row_count(root_copy, tbl) if in_root else "N/A"
    i_cnt = get_row_count(instance_copy, tbl) if in_inst else "N/A"
    
    if in_root and in_inst:
        try:
            diff = int(r_cnt) - int(i_cnt)
            diff_s = str(diff)
        except:
            diff_s = "N/A"
    else:
        diff_s = "N/A"
    
    print(f"{tbl:<40} {str(r_cnt):>10} {str(i_cnt):>10} {diff_s:>10}")

print("\n" + "="*80)
print("TABLES ONLY IN ROOT (not in instance):")
for tbl in sorted(set(root_tables) - set(instance_tables)):
    cnt = get_row_count(root_copy, tbl)
    print(f"  {tbl}: {cnt} rows")

print("\nTABLES ONLY IN INSTANCE (not in root):")
for tbl in sorted(set(instance_tables) - set(root_tables)):
    cnt = get_row_count(instance_copy, tbl)
    print(f"  {tbl}: {cnt} rows")

print("\nDone.")
