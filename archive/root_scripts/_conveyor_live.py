# -*- coding: utf-8 -*-
"""Боевой запуск конвейера: сервер + 3 потока генерации + мониторинг."""
import sys, os, time, threading, sqlite3
os.chdir('c:/Users/Redmi/Desktop/Новая папка (2)')
sys.path.insert(0, '.')

DB = 'instance/formyla.db'

# ── Чистка ──
db = sqlite3.connect(DB)
db.execute("DELETE FROM gen_conveyor")
db.execute("UPDATE daily_task_sets SET status='failed' WHERE status='generating'")
db.execute("UPDATE daily_generation_jobs SET state='failed',error_message='stale',finished_at=datetime('now') WHERE state='running'")
db.commit()
db.close()
print("[OK] DB cleaned (gen_conveyor wiped)\n")

# ── Сервер ──
def run_server():
    from app import app
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
threading.Thread(target=run_server, daemon=True).start()
time.sleep(5)

# ── Планирование + конвейер ──
from app import app
with app.app_context():
    from daily_tasks.services import schedule_all_users, conveyor_worker
    from daily_tasks.models import GenConveyor
    
    # Ручной первый запуск schedule_all_users (не ждём cron)
    result = schedule_all_users()
    print(f"[SCHEDULE] {result['entries_created']} new entries\n")
    
    # Запускаем первый раунд конвейера
    launched = conveyor_worker()
    print(f"[WORKER] Launched {launched} generations\n")

# ── Мониторинг ──
print(f"{'='*60}")
print("МОНИТОРИНГ (каждые 5 сек + запуск воркера каждые 30 сек)")
print(f"{'='*60}\n")

t_mon = time.time()
last_worker = 0
last_state = {}

while True:
    time.sleep(3)
    elapsed = int(time.time() - t_mon)
    
    db = sqlite3.connect(DB)
    rows = db.execute(
        "SELECT status, COUNT(*) FROM gen_conveyor GROUP BY status"
    ).fetchall()
    db.close()
    
    statuses = {r[0]: r[1] for r in rows}
    total = sum(statuses.values())
    pending = statuses.get('pending', 0)
    generating = statuses.get('generating', 0)
    ready = statuses.get('ready', 0)
    failed = statuses.get('failed', 0)
    
    key = f"p{pending}g{generating}r{ready}f{failed}"
    if key != last_state.get('key', ''):
        bar = '█' * ready + '▓' * generating + '▒' * pending + ' ' * (total - ready - generating - pending)
        bar = bar[:total]
        pct = int((ready / total * 100)) if total else 0
        print(f"[{elapsed}s] [{bar}] {pct}% | "
              f"ready={ready} generating={generating} pending={pending} failed={failed}", flush=True)
        last_state['key'] = key
    
    # Запуск воркера каждые 30 сек
    if elapsed - last_worker >= 30 and pending > 0:
        with app.app_context():
            launched = conveyor_worker()
            if launched:
                print(f"  ── WORKER запустил {launched} генераций", flush=True)
        last_worker = elapsed
    
    if ready + failed == total and total > 0:
        break

total_t = time.time() - t_mon
print(f"\n{'='*60}")
print(f"ГОТОВО! {total} записей обработано за {int(total_t)} сек ({total_t/60:.1f} мин)")
print(f"  ready={ready}  failed={failed}")
print(f"{'='*60}")
