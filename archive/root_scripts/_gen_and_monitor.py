# -*- coding: utf-8 -*-
"""Запуск сервера + перегенерация + мониторинг."""

import sys, os, time, json, threading, sqlite3

os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')
sys.path.insert(0, '.')

DB_PATH = 'instance/formyla.db'

# Clean stale jobs
db = sqlite3.connect(DB_PATH)
db.execute("UPDATE daily_task_sets SET status='failed' WHERE status='generating'")
db.execute("UPDATE daily_generation_jobs SET state='failed',error_message='stale',finished_at=datetime('now') WHERE state='running'")
db.commit()
print("[OK] DB cleaned", flush=True)

# Start server in background
def run_server():
    from app import app
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()
time.sleep(4)  # Wait for server to boot

# Now trigger generation via Flask app context
from app import app, db
from models import User
from daily_tasks.services import enqueue_daily_generation

with app.app_context():
    user = db.session.get(User, 1)
    print(f"[OK] User: id={user.id} email={user.email}", flush=True)
    result = enqueue_daily_generation(user_id=user.id, triggered_by='manual', skip_bank=True)
    job_id = result.get('job_id')
    print(f"[GEN] STARTED job_id={job_id}", flush=True)

# Monitor progress
print("\n[MONITOR] Watching job progress...\n", flush=True)
last_step = ''
last_pct = ''
t0 = time.time()
while True:
    time.sleep(2)
    elapsed = int(time.time() - t0)
    db2 = sqlite3.connect(DB_PATH)
    rows = db2.execute(
        "SELECT state, progress_pct, current_step, error_message, finished_at "
        "FROM daily_generation_jobs WHERE id=?",
        (job_id,)
    ).fetchall()
    db2.close()
    
    if not rows:
        continue
    
    state, pct, step, err, finished = rows[0]
    step_str = step or '—'
    pct_str = f"{pct}%" if pct else '—'
    
    if step_str != last_step or pct_str != last_pct:
        print(f"[{elapsed}s] STATE={state} STEP={step_str} PCT={pct_str}", flush=True)
        last_step = step_str
        last_pct = pct_str
    
    if state in ('completed', 'failed'):
        print(f"\n[RESULT] STATE={state}", flush=True)
        if err:
            print(f"[ERROR] {err}", flush=True)
        
        # Check generated tasks
        db3 = sqlite3.connect(DB_PATH)
        items = db3.execute(
            "SELECT dti.position, dti.task_text, dti.correct_answer, dti.status "
            "FROM daily_task_items dti "
            "JOIN daily_task_sets dts ON dti.daily_set_id = dts.id "
            "WHERE dts.id = (SELECT daily_set_id FROM daily_generation_jobs WHERE id=?) "
            "ORDER BY dti.position",
            (job_id,)
        ).fetchall()
        db3.close()
        
        print(f"\n[TASKS] Generated {len(items)} tasks:")
        for pos, txt, ans, st in items:
            txt_preview = (txt or 'N/A')[:80].replace('\n', ' ')
            print(f"  pos={pos} status={st} text={txt_preview!r} ans={ans!r}")
        
        break

print(f"\n[DONE] Total time: {int(time.time()-t0)}s", flush=True)
os._exit(0)
