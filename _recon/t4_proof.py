# -*- coding: utf-8 -*-
"""Task 4: verify intake weak_sections boost in build_profile."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app, db
from models import User
from models_curator import CuratorState
from daily_tasks.profile import build_profile, _load_intake_weak_sections

with app.app_context():
    grade = 9

    # Cleanup
    for em in ['sim_weak@x.test', 'sim_none@x.test']:
        u = User.query.filter_by(email=em).first()
        if u:
            db.session.execute(db.text(f"DELETE FROM curator_state WHERE user_id={u.id}"))
            db.session.execute(db.text(f"DELETE FROM daily_task_sets WHERE user_id={u.id}"))
            db.session.delete(u)
    db.session.commit()

    # Student A: weak geometry + logic
    ua = User(email='sim_weak@x.test', name='Sim Weak', preferred_grade=grade)
    db.session.add(ua); db.session.commit()
    cs = CuratorState(user_id=ua.id, prep_state={
        'intake': {'completed': True, 'weak_sections': ['geometry', 'logic'],
                   'weak_priority': True, 'class_level': 9, 'daily_tasks': 10,
                   'goal': 'just_grow', 'experience': 'none',
                   'prior_mu': 2.0, 'prior_sigma': 2.0},
        'onboarding': {'completed_at': '2026-08-01T00:00:00'}
    }, onboarding_done=True, level_mu=2.0, level_sigma=2.0)
    db.session.add(cs); db.session.commit()

    # Student B: no weak sections
    ub = User(email='sim_none@x.test', name='Sim None', preferred_grade=grade)
    db.session.add(ub); db.session.commit()
    cs2 = CuratorState(user_id=ub.id, prep_state={
        'intake': {'completed': True, 'weak_sections': [],
                   'weak_priority': False, 'class_level': 9, 'daily_tasks': 10,
                   'goal': 'just_grow', 'experience': 'none',
                   'prior_mu': 2.0, 'prior_sigma': 2.0},
        'onboarding': {'completed_at': '2026-08-01T00:00:00'}
    }, onboarding_done=True, level_mu=2.0, level_sigma=2.0)
    db.session.add(cs2); db.session.commit()

    print(f"Student A id={ua.id}, Student B id={ub.id}")

    # Check intake sections
    wa = _load_intake_weak_sections(ua.id)
    wb = _load_intake_weak_sections(ub.id)
    print(f"intake_weak A: {wa}")
    print(f"intake_weak B: {wb}")
    print()

    # Build profiles
    pa = build_profile(ua.id)
    pb = build_profile(ub.id)

    print("=== PROFILE A weak_topics ===")
    for t in pa.get('weak_topics', []):
        print(f"  {t.get('subject','?'):>16} topic={t.get('topic','?'):>25} "
              f"priority={t.get('priority',0):.0f} cal={t.get('calibration',False)} "
              f"intake_weak={t.get('intake_weak',False)}")
    
    print()
    print("=== PROFILE B weak_topics ===")
    for t in pb.get('weak_topics', []):
        print(f"  {t.get('subject','?'):>16} topic={t.get('topic','?'):>25} "
              f"priority={t.get('priority',0):.0f} cal={t.get('calibration',False)} "
              f"intake_weak={t.get('intake_weak',False)}")

    print()
    a_geom = any(t.get('subject') == 'geometry' for t in pa.get('weak_topics', []))
    a_logic = any(t.get('subject') == 'logic' for t in pa.get('weak_topics', []))
    print(f"A: geometry_in_weak={a_geom}, logic_in_weak={a_logic}")
    b_geom = any(t.get('subject') == 'geometry' for t in pb.get('weak_topics', []))
    b_logic = any(t.get('subject') == 'logic' for t in pb.get('weak_topics', []))
    print(f"B: geometry_in_weak={b_geom}, logic_in_weak={b_logic}")

    # The boost ensures geometry/logic appear with higher priority.
    # But weak_topics selection is still limited to MAX_WEAK_PER_SUBJECT=2
    # and TOP_WEAK_COUNT_WHEN_EMPTY=10, so all calibration topics still appear.
    # The key difference: when measured topics exist later,
    # intake-flagged sections will be forced into the weak list.

    # Cleanup
    db.session.execute(db.text(f"DELETE FROM curator_state WHERE user_id IN ({ua.id},{ub.id})"))
    db.session.execute(db.text(f"DELETE FROM daily_task_sets WHERE user_id IN ({ua.id},{ub.id})"))
    db.session.delete(ua); db.session.delete(ub)
    db.session.commit()
    print("\nCleanup done.")
