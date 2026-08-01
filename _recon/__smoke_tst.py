"""Quick smoke test before full acceptance."""
import sys, os, time, logging, json
os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')
sys.path.insert(0, '.')
os.environ['FLASK_DEBUG'] = '0'
logging.basicConfig(level=logging.CRITICAL)
for name in list(logging.root.manager.loggerDict.keys()):
    logging.getLogger(name).setLevel(logging.CRITICAL)

from app import app
with app.app_context():
    from models import db, User
    from models_curator import CuratorState
    from services.daily_task_rotation import pick_daily_set

    # Create 2 test students
    ids = []
    for i in range(1, 3):
        email = f"smoke_P2_{i}@test.local"
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(email=email, name=f"smoke_{i}", nickname=f"smoke_{i}", preferred_grade=9)
            db.session.add(user)
            db.session.flush()
        cs = CuratorState.query.filter_by(user_id=user.id).first()
        if not cs:
            cs = CuratorState(user_id=user.id, grade=9,
                prep_state={'onboarding': {'grade':9,'daily_tasks':10,'route_ceiling':5,'target_level':3}},
                level_mu=2.0, level_sigma=1.0,
                level_by_section=json.dumps({s:{'mu':2.0,'sigma':1.0,'n':0}
                    for s in ['algebra','geometry','combinatorics','logic','number_theory']}),
                summary='smoke_P2')
            db.session.add(cs)
            db.session.flush()
        ids.append(user.id)
    db.session.commit()
    print(f"Created: {ids}")

    # Run 3 days
    for day in range(1, 4):
        for uid in ids:
            t0 = time.perf_counter()
            r = pick_daily_set(uid, force_regenerate=True)
            print(f"Day {day} uid={uid}: {r['count']} tasks, {time.perf_counter()-t0:.4f}s")

    # Check repeats
    from models import TaskAssignmentHistory
    for uid in ids:
        rows = TaskAssignmentHistory.query.filter_by(user_id=uid).all()
        tids = [r.task_id for r in rows]
        print(f"uid={uid}: {len(tids)} assignments, {len(set(tids))} unique, repeats={len(tids)-len(set(tids))}")

    # Cleanup
    for cs in CuratorState.query.filter(CuratorState.summary=='smoke_P2').all():
        from daily_tasks.models import DailyTaskSet, DailyTaskItem
        DailyTaskItem.query.filter(DailyTaskItem.daily_set_id.in_(
            db.session.query(DailyTaskSet.id).filter_by(user_id=cs.user_id))).delete(synchronize_session=False)
        DailyTaskSet.query.filter_by(user_id=cs.user_id).delete()
        TaskAssignmentHistory.query.filter_by(user_id=cs.user_id).delete()
        CuratorState.query.filter_by(user_id=cs.user_id).delete()
        User.query.filter_by(id=cs.user_id).delete()
    db.session.commit()
    print("Smoke test complete - cleanup done")
