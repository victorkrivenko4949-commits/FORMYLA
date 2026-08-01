"""STEP 1: Complete analysis of pick_daily_set + timing."""
import sys, os, time, logging

os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')
sys.path.insert(0, '.')
os.environ['FLASK_DEBUG'] = '0'

# Suppress app startup logs
logging.basicConfig(level=logging.ERROR)
for name in list(logging.root.manager.loggerDict.keys()):
    logging.getLogger(name).setLevel(logging.ERROR)

from app import app
with app.app_context():
    from services.daily_task_rotation import pick_daily_set
    from models import db, User, AdaptiveTestResult, TaskSolution, AdaptiveTask
    from models_curator import CuratorState

    print("=== DB STATS ===")
    print(f"  adaptive_tasks: {AdaptiveTask.query.count()}")
    print(f"  task_solutions: {TaskSolution.query.count()}")
    print(f"  adaptive_test_results: {AdaptiveTestResult.query.count()}")
    print(f"  users: {User.query.count()}")

    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    print(f"  daily_task_sets: {DailyTaskSet.query.count()}")
    print(f"  daily_task_items: {DailyTaskItem.query.count()}")

    # Check what CuratorState looks like
    cs_count = CuratorState.query.count()
    print(f"  curator_state rows: {cs_count}")
    
    # Show users with curator_state
    cs_list = CuratorState.query.limit(5).all()
    for cs in cs_list:
        print(f"    CS user_id={cs.user_id} has prep_state={bool(cs.prep_state)}")

    # Analyze _get_seen_task_ids behavior
    print("\n=== SEEN TASK IDS ANALYSIS ===")
    
    # Check adaptive_test_results for task_ids 
    test_users = [cs.user_id for cs in cs_list if cs.user_id]
    if test_users:
        uid = test_users[0]
        print(f"  Testing exclusion logic for user_id={uid}")
        
        # TaskSolution based exclusion
        from services.daily_task_rotation import _get_seen_task_ids
        seen = _get_seen_task_ids(uid)
        print(f"  seen_ids count via current logic: {len(seen)}")
        print(f"  sample seen_ids: {list(seen)[:10]}")
        
        # Direct check - task_solutions for this user
        sol_count = TaskSolution.query.filter_by(user_id=uid).count()
        print(f"  task_solutions for this user: {sol_count}")
        
        # adaptive_test_results for this user
        atr_count = AdaptiveTestResult.query.filter_by(user_id=uid).count()
        print(f"  adaptive_test_results for this user: {atr_count}")
        
        # Check if AdaptiveTestResult actually has task_ids attribute
        if atr_count > 0:
            atr = AdaptiveTestResult.query.filter_by(user_id=uid).first()
            print(f"  ATR attributes: {[a for a in dir(atr) if not a.startswith('_')]}")
            has_task_ids = hasattr(atr, 'task_ids')
            print(f"  hasattr task_ids: {has_task_ids}")
            has_answers_history = hasattr(atr, 'answers_history')
            print(f"  hasattr answers_history: {has_answers_history}")
    
    print("\n=== TIMING pick_daily_set (5 runs per user, 3 users) ===")
    
    # Find 3 users with curator_state
    all_cs = CuratorState.query.all()
    test_users = []
    for cs in all_cs:
        if cs.user_id and cs.prep_state:
            test_users.append(cs.user_id)
            if len(test_users) >= 3:
                break
    
    if not test_users:
        all_users = User.query.limit(3).all()
        test_users = [u.id for u in all_users]
    
    print(f"  Test users: {test_users}")
    
    all_times = []
    for uid in test_users:
        for run_i in range(5):
            t0 = time.perf_counter()
            try:
                result = pick_daily_set(uid, force_regenerate=True)
                elapsed = time.perf_counter() - t0
                all_times.append(elapsed)
                print(f"    user={uid} run={run_i+1:02d} time={elapsed:.4f}s tasks={result.get('count','?')}")
            except Exception as e:
                elapsed = time.perf_counter() - t0
                print(f"    user={uid} run={run_i+1:02d} ERROR: {e}")
    
    if all_times:
        avg = sum(all_times) / len(all_times)
        print(f"\n  Summary: avg={avg:.4f}s min={min(all_times):.4f}s max={max(all_times):.4f}s over {len(all_times)} runs")
    
    # Count DB queries approximate via flask_sqlalchemy debug
    print("\n=== DB QUERY ESTIMATE ===")
    # Let's trace one call
    import flask_sqlalchemy
    old_record = flask_sqlalchemy.get_debug_queries
    
    if hasattr(flask_sqlalchemy, 'get_debug_queries'):
        print("  SQLAlchemy debug available")
    
    # Manual count by instrumenting
    # For now, count the key queries the function makes:
    # 1. DailyTaskSet lookup
    # 2. CuratorState lookup
    # 3. TaskSolution lookup (all for user)
    # 4. AdaptiveTestResult lookup
    # 5. User lookup (+grade)
    # 6. level_engine.get_state (hits user_progress)
    # 7. _pick_tasks_for_section (1 query per section = 5 sections)
    # 8. fallback queries
    # 9. DailyTaskSet insert
    # 10. DailyTaskItem inserts (10 items = 10 inserts)
    # 11. commit
    
    print("  Estimated queries per pick: ~15-25 (varies by section hits)")
