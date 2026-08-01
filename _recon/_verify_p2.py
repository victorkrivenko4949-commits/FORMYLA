"""Quick verification of the new exclusion mechanism."""
import sys, os, time, logging, json
os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')
sys.path.insert(0, '.')
os.environ['FLASK_DEBUG'] = '0'
logging.basicConfig(level=logging.CRITICAL)
for name in list(logging.root.manager.loggerDict.keys()):
    logging.getLogger(name).setLevel(logging.CRITICAL)

from app import app
with app.app_context():
    from models import db, User, AdaptiveTask, TaskAssignmentHistory
    from models_curator import CuratorState
    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    from services.daily_task_rotation import (
        pick_daily_set, _get_seen_task_ids, _record_assignment,
        cell_deficit_report
    )

    print("=== VERIFICATION ===")
    print(f"AdaptiveTask count: {AdaptiveTask.query.count()}")
    print(f"TaskAssignmentHistory count: {TaskAssignmentHistory.query.count()}")
    
    # Test: create a student, pick daily set, check history
    email = "verify_P2@test.local"
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email, name="verify_P2", nickname="verify_P2", preferred_grade=9)
        db.session.add(user)
        db.session.flush()
    
    uid = user.id
    
    cs = CuratorState.query.filter_by(user_id=uid).first()
    if not cs:
        cs = CuratorState(user_id=uid, grade=9,
            prep_state={'onboarding': {'grade':9,'daily_tasks':10,'route_ceiling':5,'target_level':3}},
            level_mu=2.0, level_sigma=1.0,
            level_by_section=json.dumps({s:{'mu':2.0,'sigma':1.0,'n':0}
                for s in ['algebra','geometry','combinatorics','logic','number_theory']}),
            summary='verify_P2')
        db.session.add(cs)
        db.session.flush()
    db.session.commit()
    
    # Clean any old daily sets
    existing = DailyTaskSet.query.filter_by(user_id=uid).all()
    for s in existing:
        DailyTaskItem.query.filter_by(daily_set_id=s.id).delete()
        db.session.delete(s)
    TaskAssignmentHistory.query.filter_by(user_id=uid).delete()
    db.session.commit()
    
    # Pick daily set
    t0 = time.perf_counter()
    r = pick_daily_set(uid, force_regenerate=True)
    elapsed = time.perf_counter() - t0
    n = r.get('count', 0)
    print(f"\nPick result: {n} tasks in {elapsed:.4f}s")
    
    # Check history
    history = TaskAssignmentHistory.query.filter_by(user_id=uid).all()
    tids = sorted([h.task_id for h in history])
    print(f"History entries: {len(tids)}")
    print(f"Task IDs: {tids[:10]}{'...' if len(tids)>10 else ''}")
    print(f"Unique: {len(set(tids))}, repeats within user: {len(tids)-len(set(tids))}")
    
    # Day 2 - clean and retry
    existing = DailyTaskSet.query.filter_by(user_id=uid).all()
    for s in existing:
        DailyTaskItem.query.filter_by(daily_set_id=s.id).delete()
        db.session.delete(s)
    db.session.commit()
    
    t0 = time.perf_counter()
    r2 = pick_daily_set(uid, force_regenerate=True)
    elapsed2 = time.perf_counter() - t0
    n2 = r2.get('count', 0)
    print(f"\nDay 2 pick: {n2} tasks in {elapsed2:.4f}s")
    
    history2 = TaskAssignmentHistory.query.filter_by(user_id=uid).all()
    tids2 = sorted([h.task_id for h in history2])
    print(f"History entries: {len(tids2)}")
    print(f"Repeats: {len(tids2)-len(set(tids2))} (expected: 0)")
    
    # Check that day 2 tasks differ from day 1
    day1_set = set(tids)
    day2_new = [t for t in tids2 if t not in day1_set]
    print(f"New tasks on day 2: {len(day2_new)} (out of {n2})")
    
    # Cell deficit report
    print("\n=== CELL DEFICIT REPORT (top 15) ===")
    report = cell_deficit_report()
    print(f"Total cells: {len(report)}")
    for i, r in enumerate(report[:15], 1):
        print(f"{i:2d}. G{r['grade']} {r['section']:15s} L{r['level']} pool={r['pool_total']:4d}")
    
    # Cleanup
    cs2 = CuratorState.query.filter_by(user_id=uid).first()
    if cs2:
        DailyTaskItem.query.filter(DailyTaskItem.daily_set_id.in_(
            db.session.query(DailyTaskSet.id).filter_by(user_id=uid)
        )).delete(synchronize_session=False)
        DailyTaskSet.query.filter_by(user_id=uid).delete()
        TaskAssignmentHistory.query.filter_by(user_id=uid).delete()
        db.session.delete(cs2)
        db.session.delete(user)
        db.session.commit()
    
    print("\n=== VERIFICATION COMPLETE ===")
