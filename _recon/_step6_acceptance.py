"""STEP 6: Acceptance testing — P2D2 load test."""
import sys, os, time, json, logging, hashlib

os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')
sys.path.insert(0, '.')
os.environ['FLASK_DEBUG'] = '0'

logging.basicConfig(level=logging.CRITICAL)
for name in list(logging.root.manager.loggerDict.keys()):
    logging.getLogger(name).setLevel(logging.CRITICAL)

from app import app

with app.app_context():
    from models import db, User, TaskAssignmentHistory
    from services.daily_task_rotation import pick_daily_set, cell_deficit_report
    from daily_tasks.models import DailyTaskSet, DailyTaskItem

    print("=" * 70)
    print("ACCEPTANCE TESTING — P2D2 LOAD TEST")
    print("=" * 70)

    LOAD_PREFIX = "load_"
    N_STUDENTS = 100
    TASKS_PER_DAY = 10
    N_DAYS = 30

    suffix = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]

    # ─── Cleanup via ORM ───
    print("\n--- Cleanup previous load_ users ---")
    existing = User.query.filter(User.email.like('load_%@test.local')).all()
    for u in existing:
        DailyTaskItem.query.filter(
            DailyTaskItem.daily_set_id.in_(
                db.session.query(DailyTaskSet.id).filter_by(user_id=u.id)
            )
        ).delete(synchronize_session=False)
        DailyTaskSet.query.filter_by(user_id=u.id).delete()
        TaskAssignmentHistory.query.filter_by(user_id=u.id).delete()
        db.session.delete(u)
    db.session.commit()
    print(f"  Cleaned up {len(existing)} users")

    # ─── Create 100 students ───
    from models_curator import CuratorState
    student_ids = []
    for i in range(1, N_STUDENTS + 1):
        email = f"{LOAD_PREFIX}{suffix}_{i}@test.local"
        nick = f"{LOAD_PREFIX}{suffix}_{i}"
        user = User(
            email=email,
            name=nick,
            nickname=nick,
            preferred_grade=9,
        )
        db.session.add(user)
        db.session.flush()

        try:
            cs = CuratorState(
                user_id=user.id,
                grade=9,
                prep_state={
                    'onboarding': {
                        'grade': 9,
                        'daily_tasks': TASKS_PER_DAY,
                        'route_ceiling': 5,
                        'target_level': 3,
                    }
                },
                level_mu=2.0,
                level_sigma=1.0,
                level_by_section=json.dumps({
                    'algebra': {'mu': 2.0, 'sigma': 1.0, 'n': 0},
                    'geometry': {'mu': 2.0, 'sigma': 1.0, 'n': 0},
                    'combinatorics': {'mu': 2.0, 'sigma': 1.0, 'n': 0},
                    'logic': {'mu': 2.0, 'sigma': 1.0, 'n': 0},
                    'number_theory': {'mu': 2.0, 'sigma': 1.0, 'n': 0},
                }),
                summary='P2D2_load',
            )
            db.session.add(cs)
        except Exception:
            pass  # table may not exist
        db.session.flush()
        student_ids.append(user.id)

    db.session.commit()
    print(f"  Created {N_STUDENTS} students (ids {student_ids[0]}..{student_ids[-1]})")

    # ─── Run 30 days ───
    print("\n--- Load test: 100 students x 30 days x 10 tasks ---")
    total_assignments = 0
    stuck_students = {}
    total_time_start = time.perf_counter()
    pick_times = []

    for day in range(1, N_DAYS + 1):
        day_assignments = 0
        for uid in student_ids:
            try:
                t0 = time.perf_counter()
                result = pick_daily_set(uid, force_regenerate=True)
                pick_times.append(time.perf_counter() - t0)
                n = result.get('count', 0)
                day_assignments += n
                total_assignments += n
                if n < TASKS_PER_DAY and uid not in stuck_students:
                    stuck_students[uid] = day
            except Exception:
                if uid not in stuck_students:
                    stuck_students[uid] = day
                db.session.rollback()

        if day % 10 == 0:
            print(f"  Day {day}: {day_assignments} tasks today, cumulative: {total_assignments}")

    total_time = time.perf_counter() - total_time_start
    avg_pick_time = sum(pick_times) / len(pick_times) if pick_times else 0

    print(f"\n  Total assignments: {total_assignments} (expected: {N_STUDENTS*N_DAYS*TASKS_PER_DAY})")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Avg pick time: {avg_pick_time:.4f}s")

    # ─── Repeats ───
    total_repeats = 0
    task_assignment_counts = {}

    for uid in student_ids:
        rows = TaskAssignmentHistory.query.filter_by(user_id=uid).all()
        task_ids = [r.task_id for r in rows]
        repeats = len(task_ids) - len(set(task_ids))
        total_repeats += repeats
        for tid in task_ids:
            task_assignment_counts[tid] = task_assignment_counts.get(tid, 0) + 1

    print(f"  Repeats within student: {total_repeats} (expected: 0)")

    if task_assignment_counts:
        avg_per_task = sum(task_assignment_counts.values()) / len(task_assignment_counts)
        print(f"  Distinct tasks: {len(task_assignment_counts)}")
        print(f"  Avg per task: {avg_per_task:.2f}")
        print(f"  Max single task: {max(task_assignment_counts.values())}")
        print(f"  Min single task: {min(task_assignment_counts.values())}")

    print(f"  Students short: {len(stuck_students)}/{N_STUDENTS}")
    if stuck_students:
        days = sorted(stuck_students.values())
        print(f"  Shortage days: {min(days)} (first) to {max(days)} (last)")

    # ─── Level/section distribution ───
    print("\n--- Distribution by level (1..5) ---")
    level_dist = {}
    section_dist = {}
    assigned_ids = list(task_assignment_counts.keys())

    if assigned_ids:
        from models import AdaptiveTask
        chunk = 900
        for start in range(0, len(assigned_ids), chunk):
            ids_chunk = assigned_ids[start:start + chunk]
            rows = db.session.query(AdaptiveTask.id, AdaptiveTask.difficulty_level).filter(
                AdaptiveTask.id.in_(ids_chunk)
            ).all()
            for t in rows:
                lvl = t.difficulty_level or 0
                level_dist[lvl] = level_dist.get(lvl, 0) + task_assignment_counts.get(t.id, 0)
        for lvl in sorted(level_dist):
            print(f"  Level {lvl}: {level_dist[lvl]}")

    print("\n--- Cell deficit (top 15) ---")
    try:
        report = cell_deficit_report()
        print(f"  Cells: {len(report)}")
        for i, r in enumerate(report[:15], 1):
            print(f"  {i:2d}. G{r.get('grade','?')} {r.get('section','?'):15s} L{r.get('level','?')} pool={r.get('pool_total',0):4d}")
    except Exception as e:
        print(f"  Error: {e}")

    # ─── Cleanup ───
    print("\n--- Cleanup load_ users ---")
    existing = User.query.filter(User.email.like('load_%@test.local')).all()
    for u in existing:
        DailyTaskItem.query.filter(
            DailyTaskItem.daily_set_id.in_(
                db.session.query(DailyTaskSet.id).filter_by(user_id=u.id)
            )
        ).delete(synchronize_session=False)
        DailyTaskSet.query.filter_by(user_id=u.id).delete()
        TaskAssignmentHistory.query.filter_by(user_id=u.id).delete()
        db.session.delete(u)
    db.session.commit()
    remaining = User.query.filter(User.email.like('load_%@test.local')).count()
    print(f"  Remaining: {remaining} (expected: 0)")

    print("\n=== DONE ===")
