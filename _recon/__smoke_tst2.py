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
    from models import db, User, AdaptiveTask
    from models_curator import CuratorState
    from services.daily_task_rotation import pick_daily_set, _get_allowed_difficulty, _get_onboarding
    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    from models import TaskAssignmentHistory
    
    # Check what tasks exist for grade 9
    print(f"Total adaptive_tasks: {AdaptiveTask.query.count()}")
    g9 = AdaptiveTask.query.filter_by(class_level=9).count()
    print(f"Grade 9 tasks: {g9}")
    
    # Check source distribution
    from sqlalchemy import func
    srcs = db.session.query(AdaptiveTask.source, func.count(AdaptiveTask.id)).group_by(AdaptiveTask.source).all()
    print(f"Source distribution: {srcs[:10]}")
    
    # Check correct_answer distribution
    with_ans = AdaptiveTask.query.filter(AdaptiveTask.correct_answer.isnot(None), AdaptiveTask.correct_answer!='').count()
    print(f"With correct_answer: {with_ans}")
    
    g9_valid = AdaptiveTask.query.filter(
        AdaptiveTask.class_level==9,
        AdaptiveTask.correct_answer.isnot(None),
        AdaptiveTask.correct_answer!='',
        AdaptiveTask.task_text.isnot(None),
        AdaptiveTask.task_text!='',
    ).count()
    print(f"Grade 9 valid tasks: {g9_valid}")
    
    # Check allowed_difficulty
    print(f"Allowed difficulty for level 2: {__import__('services.level_engine').allowed_difficulty(2, 'formyla_L1_L5_TOP5')}")
    
    # Create 1 test student
    email = "smoke_P2_1@test.local"
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email, name="smoke_1", nickname="smoke_1", preferred_grade=9)
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
            summary='smoke_P2')
        db.session.add(cs)
        db.session.flush()
    db.session.commit()
    
    # Clean before first pick
    existing = DailyTaskSet.query.filter_by(user_id=uid).all()
    for s in existing:
        DailyTaskItem.query.filter_by(daily_set_id=s.id).delete()
        db.session.delete(s)
    TaskAssignmentHistory.query.filter_by(user_id=uid).delete()
    db.session.commit()
    
    # Pick
    t0 = time.perf_counter()
    r = pick_daily_set(uid, force_regenerate=True)
    print(f"\nPick result: {r['count']} tasks, {time.perf_counter()-t0:.4f}s")
    
    # Check repeats
    rows = TaskAssignmentHistory.query.filter_by(user_id=uid).all()
    tids = [r.task_id for r in rows]
    print(f"History: {len(tids)} assignments, {len(set(tids))} unique")
    
    # Try day 2
    existing = DailyTaskSet.query.filter_by(user_id=uid).all()
    for s in existing:
        DailyTaskItem.query.filter_by(daily_set_id=s.id).delete()
        db.session.delete(s)
    db.session.commit()
    
    t0 = time.perf_counter()
    r2 = pick_daily_set(uid, force_regenerate=True)
    print(f"\nDay 2 pick: {r2['count']} tasks, {time.perf_counter()-t0:.4f}s")
    
    rows = TaskAssignmentHistory.query.filter_by(user_id=uid).all()
    tids = [r.task_id for r in rows]
    print(f"History after day 2: {len(tids)} assignments, {len(set(tids))} unique, repeats={len(tids)-len(set(tids))}")
    
    # Cleanup
    cs2 = CuratorState.query.filter_by(user_id=uid).first()
    if cs2:
        existing = DailyTaskSet.query.filter_by(user_id=uid).all()
        for s in existing:
            DailyTaskItem.query.filter_by(daily_set_id=s.id).delete()
            db.session.delete(s)
        TaskAssignmentHistory.query.filter_by(user_id=uid).delete()
        db.session.delete(cs2)
        db.session.delete(user)
        db.session.commit()
    
    print("Done")
