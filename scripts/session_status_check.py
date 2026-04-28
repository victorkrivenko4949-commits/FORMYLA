# -*- coding: utf-8 -*-
import sqlite3, os, sys, io, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = 'instance/formyla.db'
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("=== DIAGNOSTIKA SOSTOYANIYA BD ===")
print(f"Vremya: {datetime.datetime.now().isoformat()}")

# 1. Primenena li rekalibratsiya?
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE original_grade IS NOT NULL")
recalib_count = cur.fetchone()[0]
print(f"\n1. original_grade IS NOT NULL: {recalib_count}")
print(f"   --> Rekalibratsiya {'PRIMENENA' if recalib_count > 0 else 'NE PRIMENENA'}")

# 2. Skol'ko zadach v 7 klasse?
cur.execute("SELECT class_level, COUNT(*) FROM adaptive_tasks WHERE class_level=7 GROUP BY class_level")
rows = cur.fetchall()
print(f"\n2. Zadach v 7 klasse: {rows[0][1] if rows else 0}")

# Raspredelenie po klassam (original_grade=7)
cur.execute("SELECT class_level, COUNT(*) FROM adaptive_tasks WHERE original_grade=7 GROUP BY class_level ORDER BY class_level")
print("   Raspredelenie (original_grade=7):")
for r in cur.fetchall():
    print(f"   class_level={r[0]}: {r[1]}")

# 3. Tablicy v BD
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print(f"\n3. Tablicy v BD ({len(tables)}):")
for t in tables:
    print(f"   {t}")

new_tables = ['user_test_history', 'user_task_progress', 'user_achievements', 'user_xp_log']
for t in new_tables:
    status = 'SOZDANA' if t in tables else 'NE SOZDANA'
    print(f"   --> {t}: {status}")

conn.close()

# 4. Data modifikatsii BD
stat = os.stat(DB_PATH)
mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
size_mb = stat.st_size / 1024 / 1024
print(f"\n4. formyla.db: {size_mb:.1f} MB, posled. izm.: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")

# 5. Bekapi
print("\n5. Bekapi v backups/:")
backup_dir = 'backups'
if os.path.exists(backup_dir):
    files = []
    for f in os.listdir(backup_dir):
        fp = os.path.join(backup_dir, f)
        if os.path.isfile(fp) and f.endswith('.db'):
            files.append((os.path.getmtime(fp), f, os.path.getsize(fp)))
    files.sort(reverse=True)
    for mtime, fname, size in files[:5]:
        dt = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
        print(f"   {fname} ({size/1024/1024:.1f} MB) [{dt}]")

print("\n=== DONE ===")
