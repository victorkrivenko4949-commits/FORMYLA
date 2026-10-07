"""Check formyla.db for today's daily tasks data."""
import sqlite3

conn = sqlite3.connect('formyla.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

# All daily_task_sets with item counts
print("=== All DailyTaskSets ===")
c.execute("""
    SELECT ds.*, COUNT(di.id) as item_count
    FROM daily_task_sets ds
    LEFT JOIN daily_task_items di ON di.daily_set_id = ds.id
    GROUP BY ds.id
    ORDER BY ds.id DESC
""")
for row in c.fetchall():
    d = dict(row)
    print(f"  id={d['id']}, user_id={d['user_id']}, target_date={d['target_date']}, status={d['status']}, items={d['item_count']}")

# Items for EACH set
print("\n=== Items per set ===")
c.execute("SELECT daily_set_id, position, is_flagged, status, LENGTH(task_text) as txt_len, SUBSTR(task_text,1,60) as preview FROM daily_task_items ORDER BY daily_set_id, position")
for r in c.fetchall():
    d = dict(r)
    flags = []
    if d['is_flagged']: flags.append('FLAGGED')
    if d['status'] != 'active': flags.append(f"status={d['status']}")
    if not d['txt_len'] or d['txt_len']==0: flags.append('EMPTY')
    tag = ' | '.join(flags) if flags else 'OK'
    print(f"  set={d['daily_set_id']}, pos={d['position']}, len={d['txt_len']}, {tag}")
    if d['txt_len'] and d['txt_len'] > 0 and flags:
        print(f"    txt: {d['preview']}")

# Jobs with correct column names
print("\n=== DailyGenerationJobs ===")
c.execute("""
    SELECT id, user_id, target_date, daily_set_id, state, current_step, progress_pct,
           error_message, started_at, finished_at, created_at
    FROM daily_generation_jobs ORDER BY id DESC
""")
for r in c.fetchall():
    d = dict(r)
    err = (d.get('error_message') or '')[:100]
    print(f"  id={d['id']}, date={d['target_date']}, set_id={d['daily_set_id']}, state={d['state']}, err={err}")

conn.close()
print("\nDone")
