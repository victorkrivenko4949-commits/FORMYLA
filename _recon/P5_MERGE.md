# P5_MERGE — Pool Migration Report
**Date:** 2026-08-01 01:15 MSK  
**Databases:** root `formyla.db` → active `instance/formyla.db`  
**Principle:** Local only. No prod. No deletes. Copies only.

---

## TASK 1 — FULL COMPARISON

### Copies created in `_recon\`
| File | Size |
|------|------|
| `root_formyla_20260801_010441.db` | 31.2 MB |
| `instance_formyla_20260801_010441.db` | 25.0 MB |

### Row counts: all tables

| Table | Root | Instance | Diff |
|-------|------|----------|------|
| adaptive_tasks | 8773 | 0 | **+8773** |
| adaptive_test_problems | 0 | 0 | 0 |
| adaptive_test_results | 7 | 0 | +7 |
| adaptive_tests | 0 | 0 | 0 |
| alembic_version | 1 | — | — |
| assistant_knowledge | — | 9 | — |
| assistant_logs | — | 0 | — |
| broken_task_log | 0 | 0 | 0 |
| chat_messages | 39 | 0 | +39 |
| chat_settings | 0 | — | — |
| cost_log | 4247 | — | — |
| curator_state | — | 3 | — |
| daily_generation_jobs | 5 | 0 | +5 |
| daily_quests | 5 | 0 | +5 |
| daily_task_items | 50 | 0 | +50 |
| daily_task_sets | 5 | 0 | +5 |
| direct_messages | 0 | 0 | 0 |
| drawing_generations | 2 | 0 | +2 |
| events | 3 | — | — |
| friendships | 1 | 0 | +1 |
| grade_tasks | 1600 | — | — |
| group_chats | 3 | 0 | +3 |
| group_members | 6 | 0 | +6 |
| group_messages | 1 | 0 | +1 |
| learning_plans | — | 0 | — |
| manual_review_queue | 336 | — | — |
| mentorships | 0 | 0 | 0 |
| message_reactions | 0 | 0 | 0 |
| method_tasks | 1434 | 860 | +574 |
| mock_exam_tasks | 0 | 0 | 0 |
| mock_exams | 0 | 0 | 0 |
| notifications | 2 | 0 | +2 |
| oauth_accounts | 0 | 0 | 0 |
| olympiad_generation_log | 0 | 0 | 0 |
| olympiad_prep | 18 | 10 | +8 |
| olympiad_probnik_theory | 0 | 0 | 0 |
| olympiad_probniks | 15 | 43 | -28 |
| olympiad_secrets | 127 | 102 | +25 |
| olympiad_stage_attempts | 0 | 0 | 0 |
| olympiad_task_attempts | 0 | 0 | 0 |
| olympiad_tasks | 140 | 860 | -720 |
| olympiad_theory | 102 | 102 | 0 |
| pre_gen_queue | — | 0 | — |
| prep_days | 0 | 0 | 0 |
| prep_plans | 0 | 0 | 0 |
| progress_log | — | 0 | — |
| push_subscriptions | 1 | 0 | +1 |
| reviews | 6 | — | — |
| secret_topics | 0 | 0 | 0 |
| site_reviews | — | 0 | — |
| sqlite_sequence | 10 | 3 | +7 |
| starred_messages | 0 | — | — |
| student_diagnostics | — | 0 | — |
| subscriptions | 5 | — | — |
| subtopic_progress | — | 0 | — |
| subtopics | — | 0 | — |
| support_messages | 3 | 0 | +3 |
| **task_assignment_history** | **106** | **0** | **+106** |
| task_attempts | — | 0 | — |
| task_bank | — | 0 | — |
| task_generation_log | 720 | — | — |
| task_pool | 1 | 0 | +1 |
| task_solutions | 84 | 0 | +84 |
| test_results_detail | 0 | 0 | 0 |
| test_sessions | 1 | 1 | 0 |
| topic_mastery | 9 | 0 | +9 |
| tutor_calls | 22 | 0 | +22 |
| usage_daily | 0 | — | — |
| user_presence | 1 | 0 | +1 |
| user_progress | 0 | 0 | 0 |
| user_streaks | 1 | 0 | +1 |
| user_task_assignments | 1 | 0 | +1 |
| user_topic_progress | 0 | 0 | 0 |
| users | 7 | 3 | +4 |
| vsosh_course_entries | — | 0 | — |

### Tables ONLY in root (not in instance)
- `alembic_version` (1 row)
- `chat_settings` (0 rows)
- `cost_log` (4247 rows)
- `events` (3 rows)
- `grade_tasks` (1600 rows)
- `manual_review_queue` (336 rows)
- `reviews` (6 rows)
- `starred_messages` (0 rows)
- `subscriptions` (5 rows)
- `task_generation_log` (720 rows)
- `usage_daily` (0 rows)

### Tables ONLY in instance (not in root)
- `assistant_knowledge`, `assistant_logs`, `curator_state`, `learning_plans`, `pre_gen_queue`, `progress_log`, `site_reviews`, `student_diagnostics`, `subtopic_progress`, `subtopics`, `task_attempts`, `task_bank`, `vsosh_course_entries` — all new features/empty.

### VERDICT: Besides `adaptive_tasks` (8773 rows), root also holds:
`task_assignment_history` (106), `task_solutions` (84), `grade_tasks` (1600), `cost_log` (4247), `manual_review_queue` (336), `task_generation_log` (720), `chat_messages` (39), `daily_task_items` (50), `daily_quests` (5), `daily_task_sets` (5), `daily_generation_jobs` (5), `topic_mastery` (9), `tutor_calls` (22), `drawing_generations` (2), `notifications` (2), `support_messages` (3), among others. **But the canonical migration target defined in the task is `adaptive_tasks` and `task_assignment_history` only.**

---

## TASK 2 — REFERENTIAL INTEGRITY

### Instance DB: all `task_id` columns
| Table | Rows with task_id | Unique IDs |
|-------|------------------|------------|
| broken_task_log | 0 | — |
| direct_messages | 0 | — |
| olympiad_task_attempts | 0 | — |
| task_assignment_history | 0 | — |
| task_attempts | 0 | — |
| task_solutions | 0 | — |
| test_results_detail | 0 | — |
| tutor_calls | 0 | — |

### Root `adaptive_tasks` ID range
- **Total:** 8773 rows
- **ID range:** 1 … 8778
- **Gaps:** 5 missing IDs: 5185, 5899, 5911, 7945, 7981

### Conflict assessment
**ZERO conflict.** The instance `adaptive_tasks` table is empty (0 rows). All `task_id` foreign key columns in instance are also empty. No ID collision possible.

### `adaptive_tasks` schema in root
- **Columns:** id, class_level, difficulty_level, topic, subtopic, task_text, solution, criteria_1_point, criteria_2_points, created_at, correct_answer, is_flagged, reports_count, flagged_reason, attempts_count, solves_count, actual_solve_rate, suggested_level, needs_reclassification, last_calibrated_at, subject, source_id, needs_review, llm_suggested_answer, llm_suggested_solution, review_reason, review_flagged_at, task_type, source, **difficulty_level_src**
- `difficulty_level`: strictly **1..5**, 0 NULLs, 0 out of range
- `difficulty_level_src`: values **[1, 2, 3, 4, 5, 6, 7, 8]** — preserves original 8-point scale

### Schema diff: root vs instance `adaptive_tasks`
- **Root only:** `difficulty_level_src`
- **Instance only:** `origin`, `methods_json`, `theme_id`, `theme_title`

### Migration conflict plan
- `INSERT OR IGNORE` by primary key `id` — if a row with the same `id` already exists in instance, it is skipped (instance wins). Since instance is empty, all 8773 rows are inserted.
- `difficulty_level_src` column added to instance schema before insert.
- Instance-only columns (`origin`, `methods_json`, `theme_id`, `theme_title`) receive NULL.

---

## TASK 3 — ABSOLUTE PATH

### Diff applied to `app.py` (lines 177–182)
```diff
- _database_url = os.environ.get('DATABASE_URL', 'sqlite:///formyla.db')
+ # АБСОЛЮТНЫЙ ПУТЬ: всегда вычисляется от корня проекта (app.py),
+ # независимо от папки запуска и от instance_path Flask.
+ _default_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'formyla.db')
+ _default_db_uri = 'sqlite:///' + _default_db_path.replace('\\', '/')
+ _database_url = os.environ.get('DATABASE_URL', _default_db_uri)
```

### Verification — `db.engine.url`
| Launch from | Engine URL |
|-------------|------------|
| Root (`c:\...\Новая папка (2)`) | `sqlite:///c:/Users/Redmi/Desktop/Новая папка (2)/instance/formyla.db` |
| `_recon\` | `sqlite:///c:/Users/Redmi/Desktop/Новая папка (2)/instance/formyla.db` |

**MATCH:** Both identical. Ambiguity eliminated permanently.

---

## TASK 4 — POOL MIGRATION

### Script: [`scripts\migrate_pool_to_instance.py`](../scripts/migrate_pool_to_instance.py)

### Migration plan
1. Add `difficulty_level_src INTEGER` to instance `adaptive_tasks` (if missing)
2. Map 30 common columns (all root columns except `difficulty_level_src` are also in instance; `difficulty_level_src` added in step 1)
3. Instance-only columns (`origin`, `methods_json`, `theme_id`, `theme_title`) → NULL
4. `INSERT OR IGNORE` all 8773 rows by `id` (PK)
5. `INSERT OR IGNORE` all 106 rows of `task_assignment_history`

### Conflict resolution
Instance row wins (already present `id` → skipped). Since instance was empty, all rows inserted.

### Results
```
adaptive_tasks total: 8773
By class_level:
  class 5: 1128
  class 6: 1128
  class 7: 1324
  class 8: 1384
  class 9: 1300
  class 10: 1277
  class 11: 1232
By difficulty_level:
  level 1: 3756
  level 2: 1332
  level 3: 1624
  level 4: 1434
  level 5: 627
NULL difficulty_level: 0
difficulty_level range: 1 .. 5
Out of 1..5 range: 0
difficulty_level_src non-null: 8773
difficulty_level_src values: [1, 2, 3, 4, 5, 6, 7, 8]
task_assignment_history: 106 rows
```

### Idempotency
```
Re-insert adaptive_tasks: 0 (expect 0)
Re-insert history: 0 (expect 0)
```
Repeated execution produces zero new rows. Safe to re-run.

---

## TASK 5 — LIVE TEST

### Endpoints
| Route | STATUS | Notes |
|-------|--------|-------|
| GET /login | 200 | Login form present |
| GET / (home) | 200 | Home page renders |
| GET /daily_tasks | 200 | ~2 task cards |
| GET /olympiads | 200 | Olympiads page |
| GET /olympiads/vsosh-9-2027 | 404 | Expected — no SERVER_NAME match in test_client |

### Data integrity
```
Users: 3 (d1_no_onb@x.test, d2_sect@x.test, d4_zero@x.test)
Task solutions: 0
Task assignment history: 106 (5 latest: ids 108, 107, 106, 104, 103)
Adaptive tasks: 8773
Olympiad tasks: 860
Olympiad probniks: 43
```
Accounts and progress are intact. The `[LATEX-ROOT-DB-FIX]` internal scan confirmed: `adaptive_tasks: updated 0 / 8773 rows`.

---

## TASK 6 — FILE INVENTORY

**133 total DB-related files** found across the project (`.db`, `.db-shm`, `.db-wal`, `.bak`).

### Breakdown by category
| Category | Count | Total Size |
|----------|-------|------------|
| CANONICAL active (`instance/formyla.db`) | 1 | 25.0 MB |
| Root pool (`formyla.db`) | 2 | 31.2 MB |
| Recon copies (`_recon\`) | 8 | ~175 MB |
| Backup copies (`backups\`, `instance\backups\`) | 71+ | ~2.5 GB |
| Instance auxiliary/test (`instance\*.db`) | 7 | ~7.5 MB |
| Python `.bak` files | 3 | ~44 MB |
| Empty/zero-byte dbs | 6 | 0 B |
| WAL/SHM journals | ~40 | ~1.3 MB |

### Candidates for deletion
| Priority | Files | Reason |
|----------|-------|--------|
| **YES** | `_recon\*.db` (8 files, ~175 MB) | Recon copies, served their purpose |
| **YES** | `_recon\database_backup_P2.db` (0 B) | Empty |
| **PROBABLY** | `backups\` directory (71+ files, ~2.5 GB) | Pre-migration snapshots, old |
| **PROBABLY** | `instance\backups\` directory (8 files, ~250 MB) | Old pre-migration snapshots |
| **NO** | `instance/formyla.db` + shm/wal | **ACTIVE — DO NOT DELETE** |
| **NO (canon)** | `formyla.db` + bak | Canonical root — keep |
| **NO** | WAL/SHM journals | Auto-generated, harmless |

---

## CHANGES MADE

| File | Change | Lines |
|------|--------|-------|
| [`app.py`](../app.py) | Absolute path: `sqlite:///relative` → `sqlite:///absolute/from/__file__` | 177-182 |
| [`scripts/migrate_pool_to_instance.py`](../scripts/migrate_pool_to_instance.py) | **NEW** — idempotent migration script | 166 lines |
| [`_recon/task1_compare.py`](../_recon/task1_compare.py) | **NEW** — comparison script | — |
| [`_recon/task2_integrity.py`](../_recon/task2_integrity.py) | **NEW** — integrity check | — |
| [`_recon/task3_verify_url.py`](../_recon/task3_verify_url.py) | **NEW** — URL verification | — |
| [`_recon/task4_precheck.py`](../_recon/task4_precheck.py) | **NEW** — pre-migration check | — |
| [`_recon/task5_live.py`](../_recon/task5_live.py) | **NEW** — live test | — |
| [`_recon/task6_inventory.py`](../_recon/task6_inventory.py) | **NEW** — file inventory | — |

### Backups created
| File | Size |
|------|------|
| `_recon/root_formyla_20260801_010441.db` | 31.2 MB |
| `_recon/instance_formyla_20260801_010441.db` | 25.0 MB |
| `_recon/instance_pre_migrate_20260801_011208.db` | 25.0 MB |

### Migration script: `scripts/migrate_pool_to_instance.py`

```python
# -*- coding: utf-8 -*-
"""
TASK 4: Pool migration from root formyla.db -> instance/formyla.db.

IDEMPOTENT: INSERT OR IGNORE on PK id. Re-runs do not duplicate.
Conflict policy: instance row wins, root row is skipped (idempotent).

Transferred:
1. adaptive_tasks — all 8773 rows incl. difficulty_level and difficulty_level_src.
   Column difficulty_level_src added to instance if missing.
   Instance-only columns (theme_id, theme_title, methods_json, origin) = NULL.
2. task_assignment_history — all 106 rows. Schemas identical.
"""
import sys, os
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
import sqlite3, datetime

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DB = os.path.join(BASE, 'formyla.db')
INST_DB = os.path.join(BASE, 'instance', 'formyla.db')

conn_inst = sqlite3.connect(INST_DB)
conn_root = sqlite3.connect(ROOT_DB)
cur = conn_inst.cursor()

# Add difficulty_level_src column if missing
cur.execute("PRAGMA table_info('adaptive_tasks')")
if 'difficulty_level_src' not in {c[1] for c in cur.fetchall()}:
    cur.execute("ALTER TABLE adaptive_tasks ADD COLUMN difficulty_level_src INTEGER")
    conn_inst.commit()

# Map common columns
cur.execute("PRAGMA table_info('adaptive_tasks')")
inst_cols = [c[1] for c in cur.fetchall()]
cur_root = conn_root.cursor()
cur_root.execute("PRAGMA table_info('adaptive_tasks')")
root_cols = [c[1] for c in cur_root.fetchall()]
common = [c for c in root_cols if c in set(inst_cols)]

# Insert adaptive_tasks
cols_s = ', '.join(f'"{c}"' for c in common)
ph = ', '.join('?' * len(common))
cur_root.execute(f'SELECT {cols_s} FROM adaptive_tasks ORDER BY id')
root_rows = cur_root.fetchall()
sql = f'INSERT OR IGNORE INTO adaptive_tasks ({cols_s}) VALUES ({ph})'
inserted = sum(cur.execute(sql, r).rowcount for r in root_rows)
conn_inst.commit()
log(f"adaptive_tasks: inserted={inserted}")

# Insert task_assignment_history
cur.execute("PRAGMA table_info('task_assignment_history')")
hcols = [c[1] for c in cur.fetchall()]
hcs = ', '.join(f'"{c}"' for c in hcols)
hp = ', '.join('?' * len(hcols))
cur_root.execute(f'SELECT {hcs} FROM task_assignment_history ORDER BY id')
hrows = cur_root.fetchall()
hsql = f'INSERT OR IGNORE INTO task_assignment_history ({hcs}) VALUES ({hp})'
hins = sum(cur.execute(hsql, r).rowcount for r in hrows)
conn_inst.commit()
log(f"task_assignment_history: inserted={hins}")

# Verification
cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
log(f"Total: {cur.fetchone()[0]}")
cur.execute("SELECT difficulty_level, COUNT(*) FROM adaptive_tasks WHERE difficulty_level IS NOT NULL GROUP BY 1 ORDER BY 1")
for lvl, cnt in cur.fetchall():
    log(f"  level {lvl}: {cnt}")
cur.execute("SELECT MIN(difficulty_level), MAX(difficulty_level) FROM adaptive_tasks")
log(f"Range: {cur.fetchone()}")
cur.execute("SELECT COUNT(*) FROM task_assignment_history")
log(f"History rows: {cur.fetchone()[0]}")

# Idempotency test
log(f"Re-insert: {sum(cur.execute(sql, r).rowcount for r in root_rows)} (expect 0)")
log(f"Re-insert history: {sum(cur.execute(hsql, r).rowcount for r in hrows)} (expect 0)")

conn_inst.close()
conn_root.close()
```

---

## CONSOLE OUTPUT (task4 migration)
```
[01:13:39] ROOT_DB: c:\Users\Redmi\Desktop\Новая папка (2)\formyla.db
[01:13:39] INST_DB: c:\Users\Redmi\Desktop\Новая папка (2)\instance\formyla.db
[01:13:39]   root: 31924.0 KB
[01:13:39]   instance: 25596.0 KB
[01:13:39] Column difficulty_level_src already exists — skip ALTER
[01:13:39]   Common columns (30)
[01:13:39]   Instance-only (will be NULL): ['origin', 'methods_json', 'theme_id', 'theme_title']
[01:13:39] Read 8773 rows from root adaptive_tasks
[01:13:39]   adaptive_tasks: inserted=8773, skipped=0
[01:13:39] --- task_assignment_history ---
[01:13:39]   Read 106 rows from root
[01:13:39]   task_assignment_history: inserted=106, skipped=0
[01:13:39] === VERIFICATION ===
[01:13:39]   adaptive_tasks total: 8773
[01:13:39]   By class_level:
[01:13:39]     class 5: 1128
[01:13:39]     class 6: 1128
[01:13:39]     class 7: 1324
[01:13:39]     class 8: 1384
[01:13:39]     class 9: 1300
[01:13:39]     class 10: 1277
[01:13:39]     class 11: 1232
[01:13:39]   By difficulty_level:
[01:13:39]     level 1: 3756
[01:13:39]     level 2: 1332
[01:13:39]     level 3: 1624
[01:13:39]     level 4: 1434
[01:13:39]     level 5: 627
[01:13:39]   NULL difficulty_level: 0
[01:13:39]   difficulty_level range: 1 .. 5
[01:13:39]   Out of 1..5 range: 0
[01:13:39]   difficulty_level_src non-null: 8773
[01:13:39]   difficulty_level_src values: [1, 2, 3, 4, 5, 6, 7, 8]
[01:13:39]   task_assignment_history: 106 rows
[01:13:39] === IDEMPOTENCY TEST (re-insert same data) ===
[01:13:39]   Re-insert adaptive_tasks: 0 (expect 0)
[01:13:39]   Re-insert history: 0 (expect 0)
[01:13:39] === DONE ===
```

---

## FINAL STATUS

| Check | Result |
|-------|--------|
| 8773 tasks in active DB | ✅ |
| Difficulty strictly 1..5 | ✅ |
| difficulty_level_src preserved [1..8] | ✅ |
| 106 history rows | ✅ |
| 7 class levels, all populated | ✅ |
| Idempotent migration | ✅ |
| Absolute path (same from any cwd) | ✅ |
| Users & data intact | ✅ |
| Zero deletions | ✅ |
| Backups created (3 copies) | ✅ |
