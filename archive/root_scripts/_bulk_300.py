# -*- coding: utf-8 -*-
"""Create 300 test users + curator cycles, then run conveyor."""
import sys, os, time, random, json, sqlite3, threading
os.chdir('c:/Users/Redmi/Desktop/Новая папка (2)')
sys.path.insert(0, '.')

DB = 'instance/formyla.db'

print("[1/5] Killing old processes...")
os.system('powershell -Command "Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force" 2>nul')
time.sleep(2)

print("[2/5] Cleaning DB...")
db = sqlite3.connect(DB)
db.execute("DELETE FROM gen_conveyor")
db.execute("DELETE FROM daily_task_sets")
db.execute("DELETE FROM daily_generation_jobs")
db.execute("DELETE FROM task_pool")
db.execute("DELETE FROM user_task_assignments")
db.commit()
db.close()

print("[3/5] Starting server...")
def run_server():
    from app import app
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
threading.Thread(target=run_server, daemon=True).start()
time.sleep(5)

from app import app, db as flask_db
from models import User
from models_curator import CuratorState
from curator.monthly_cycle import build_or_get_cycle, _get_monthly_cycle

print("[4/5] Creating 300 test users + curator cycles...")

GRADES = [5,6,7,8,9,10,11]
existing_count = User.query.count()
need = 300 - existing_count + 2  # buffer

created = 0
cycles_created = 0

# First: ensure existing users have cycles
for u in User.query.limit(20).all():
    if u.preferred_grade and u.preferred_grade >= 5:
        cs = CuratorState.query.filter_by(user_id=u.id).first()
        if cs:
            mc = _get_monthly_cycle(cs)
            if not mc.get('themes'):
                build_or_get_cycle(u.id, u.preferred_grade, force_new=True)
                cycles_created += 1
        else:
            cs = CuratorState(user_id=u.id)
            flask_db.session.add(cs)
            flask_db.session.flush()
            build_or_get_cycle(u.id, u.preferred_grade, force_new=True)
            cycles_created += 1

# Create new test users
for i in range(need):
    if User.query.count() >= 300:
        break
    grade = random.choice(GRADES)
    email = f'test{i+10000}@conveyor.local'
    name = f'Test User {i+1}'
    u = User(
        email=email, name=name,
        preferred_grade=grade,
        is_guest=False,
        onboarding_completed=True,
    )
    flask_db.session.add(u)
    flask_db.session.flush()
    
    # Create curator state + cycle
    cs = CuratorState(user_id=u.id)
    flask_db.session.add(cs)
    flask_db.session.flush()
    
    try:
        build_or_get_cycle(u.id, grade, force_new=True)
        cycles_created += 1
    except Exception as e:
        pass
    
    created += 1
    if created % 50 == 0:
        flask_db.session.commit()
        print(f"  Created {created}/{need} users, {cycles_created} cycles...")

flask_db.session.commit()
total_users = User.query.count()
users_with_cycles = CuratorState.query.count()
print(f"  Done! Total users: {total_users}, Users with curator_state: {users_with_cycles}")

print("\n[5/5] Running schedule_all_users + conveyor...")
from daily_tasks.services import schedule_all_users, conveyor_worker
from daily_tasks.models import GenConveyor

result = schedule_all_users()
print(f"  schedule_all_users: {result}")

# Check conveyor table
stats = flask_db.session.query(
    GenConveyor.status, db.func.count()
).group_by(GenConveyor.status).all()
print(f"  GenConveyor entries:")
for s, c in stats:
    print(f"    {s}: {c}")

# Launch first round
launched = conveyor_worker()
print(f"  conveyor_worker launched: {launched}")

# Quick stats
unique_keys = flask_db.session.query(GenConveyor.cache_key).distinct().count()
print(f"\n  Unique cache_keys (unique profile+subtopic combos): {unique_keys}")
print(f"  Estimated AI calls needed: {unique_keys}")
print(f"  Estimated time: {unique_keys / 3 * 5 / 60:.1f} hours at 3 concurrent")

print("\n[DONE] 300 users setup complete! Conveyor running in background.")
print("Open http://127.0.0.1:5000/daily_tasks to check")
