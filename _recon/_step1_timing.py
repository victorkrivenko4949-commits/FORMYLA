"""STEP 1: Fixed timing test - clean runs."""
import sys, os, time, logging

os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')
sys.path.insert(0, '.')
os.environ['FLASK_DEBUG'] = '0'

logging.basicConfig(level=logging.ERROR)
for name in list(logging.root.manager.loggerDict.keys()):
    logging.getLogger(name).setLevel(logging.ERROR)

from app import app
with app.app_context():
    from services.daily_task_rotation import pick_daily_set
    from models import db
    from models_curator import CuratorState
    from daily_tasks.models import DailyTaskSet
    
    all_cs = CuratorState.query.all()
    test_users = [cs.user_id for cs in all_cs if cs.user_id and cs.prep_state]
    
    if not test_users:
        from models import User
        test_users = [u.id for u in User.query.limit(3).all()]
    
    print(f"Test users: {test_users}")
    print(f"Test with force_regenerate=True, cleaning up between runs\n")
    
    all_times = []
    for uid in test_users:
        for run_i in range(5):
            # Delete any existing daily_set for this user today
            from datetime import date, timezone, timedelta
            MSK_TZ = timezone(timedelta(hours=3))
            today = __import__('datetime').datetime.now(MSK_TZ).date()
            
            existing = DailyTaskSet.query.filter_by(user_id=uid, target_date=today).all()
            for s in existing:
                from daily_tasks.models import DailyTaskItem
                DailyTaskItem.query.filter_by(daily_set_id=s.id).delete()
                db.session.delete(s)
            db.session.commit()
            
            t0 = time.perf_counter()
            try:
                result = pick_daily_set(uid, force_regenerate=True)
                elapsed = time.perf_counter() - t0
                all_times.append(elapsed)
                n_tasks = result.get('count', 0)
                print(f"  user={uid} run={run_i+1:02d} time={elapsed:.4f}s tasks={n_tasks}")
            except Exception as e:
                elapsed = time.perf_counter() - t0
                db.session.rollback()
                print(f"  user={uid} run={run_i+1:02d} ERROR: {e} elapsed={elapsed:.4f}s")
    
    if all_times:
        avg = sum(all_times) / len(all_times)
        print(f"\n{'='*60}")
        print(f"SUMMARY: avg={avg:.4f}s min={min(all_times):.4f}s max={max(all_times):.4f}s over {len(all_times)} runs")
        print(f"{'='*60}")
    else:
        print("No successful runs")
