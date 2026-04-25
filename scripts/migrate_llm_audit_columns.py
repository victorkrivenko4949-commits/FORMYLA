# -*- coding: utf-8 -*-
"""
Migraciya: dobavit' llm_* kolonki v adaptive_tasks
Zapuskat': python scripts/migrate_llm_audit_columns.py
"""
import sqlite3
import shutil
import datetime
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = 'instance/formyla.db'
BACKUP_DIR = 'backups'

# --- BACKUP ---
os.makedirs(BACKUP_DIR, exist_ok=True)
stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
backup_path = os.path.join(BACKUP_DIR, f'formyla_before_g7_recalibration_{stamp}.db')
shutil.copy2(DB_PATH, backup_path)
print(f"[OK] Backup created: {backup_path}")
print(f"     Size: {os.path.getsize(backup_path) / 1024 / 1024:.1f} MB")

# --- MIGRATION ---
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Proverka sushchestvuyushchikh kolonok
cur.execute("PRAGMA table_info(adaptive_tasks)")
existing_cols = {row[1] for row in cur.fetchall()}
print(f"\n[INFO] Sushchestvuyushchie kolonki: {len(existing_cols)}")

new_columns = [
    ("llm_suggested_grade",      "INTEGER",   "NULL"),
    ("llm_suggested_difficulty", "INTEGER",   "NULL"),
    ("llm_quality_score",        "REAL",      "NULL"),
    ("llm_rationale",            "TEXT",      "NULL"),
    ("llm_topic_correct",        "INTEGER",   "NULL"),  # 0/1
    ("llm_concerns",             "TEXT",      "NULL"),  # JSON array as text
    ("llm_audited_at",           "TIMESTAMP", "NULL"),
    ("original_grade",           "INTEGER",   "NULL"),
    ("original_difficulty",      "INTEGER",   "NULL"),
]

print("\n[MIGRATION] Dobavlyayu kolonki:")
added = 0
skipped = 0
for col_name, col_type, col_default in new_columns:
    if col_name in existing_cols:
        print(f"  SKIP (uzhe est'): {col_name}")
        skipped += 1
    else:
        sql = f"ALTER TABLE adaptive_tasks ADD COLUMN {col_name} {col_type} DEFAULT {col_default}"
        cur.execute(sql)
        print(f"  ADDED: {col_name} {col_type}")
        added += 1

conn.commit()

# Proverka
cur.execute("PRAGMA table_info(adaptive_tasks)")
final_cols = [row[1] for row in cur.fetchall()]
print(f"\n[OK] Migraciya zavershena:")
print(f"     Dobavleno: {added} kolonok")
print(f"     Propushcheno (uzhe est'): {skipped} kolonok")
print(f"     Vsego kolonok teper': {len(final_cols)}")

# Proverka chto kolonki dobavilis'
llm_cols = [c for c in final_cols if c.startswith('llm_') or c.startswith('original_')]
print(f"     LLM/original kolonki: {', '.join(llm_cols)}")

conn.close()
print("\n[DONE] Gotovo. Teper' mozhno zapuskat' audit_grade7_llm.py")
