# -*- coding: utf-8 -*-
"""Task 4: Show build_profile differences for weak vs no-weak students."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app, db
from models import User
from models_curator import CuratorState
from daily_tasks.profile import build_profile

with app.app_context():
    grade = 9
    from datetime import datetime

    # Clean old
    for em in ['sim_weak@x.test', 'sim_none@x.test']:
        u = User.query.filter_by(email=em).first()
        if u:
            db.session.execute(db.text(f"DELETE FROM curator_state WHERE user_id={u.id}"))
            db.session.delete(u)
    db.session.commit()

    # Create A
    ua = User(email='sim_weak@x.test', name='Sim Weak', preferred_grade=grade)
    db.session.add(ua)
    db.session.commit()
    cs = CuratorState(user_id=ua.id, prep_state={
        'intake': {'completed': True, 'weak_sections': ['geometry', 'logic'], 'weak_priority': True,
                   'class_level': 9, 'daily_tasks': 10, 'goal': 'just_grow', 'experience': 'none',
                   'prior_mu': 2.0, 'prior_sigma': 2.0},
        'onboarding': {'completed_at': '2026-08-01T00:00:00'}
    }, onboarding_done=True, level_mu=2.0, level_sigma=2.0)
    db.session.add(cs); db.session.commit()

    # Create B
    ub = User(email='sim_none@x.test', name='Sim None', preferred_grade=grade)
    db.session.add(ub)
    db.session.commit()
    cs2 = CuratorState(user_id=ub.id, prep_state={
        'intake': {'completed': True, 'weak_sections': [], 'weak_priority': False,
                   'class_level': 9, 'daily_tasks': 10, 'goal': 'just_grow', 'experience': 'none',
                   'prior_mu': 2.0, 'prior_sigma': 2.0},
        'onboarding': {'completed_at': '2026-08-01T00:00:00'}
    }, onboarding_done=True, level_mu=2.0, level_sigma=2.0)
    db.session.add(cs2); db.session.commit()

    pa = build_profile(ua.id)
    pb = build_profile(ub.id)

    print("PROFILE A (weak=geometry,logic):")
    print(f"  topics_full count: {len(pa.get('topics_full',[]))}")
    print(f"  weak_topics count: {len(pa.get('weak_topics',[]))}")
    print(f"  calibration_topics count: {len(pa.get('calibration_topics',[]))}")
    for t in pa.get('weak_topics', []):
        print(f"    topic={t.get('topic','?')} subject={t.get('subject','?')} cal={t.get('calibration',False)} target={t.get('target_level','?')}")
    print()

    print("PROFILE B (no weak sections):")
    print(f"  topics_full count: {len(pb.get('topics_full',[]))}")
    print(f"  weak_topics count: {len(pb.get('weak_topics',[]))}")
    print(f"  calibration_topics count: {len(pb.get('calibration_topics',[]))}")
    for t in pb.get('weak_topics', []):
        print(f"    topic={t.get('topic','?')} subject={t.get('subject','?')} cal={t.get('calibration',False)} target={t.get('target_level','?')}")
    print()

    # DIFFERENCE: Both profiles are identical when no AdaptiveTestResult exists.
    # The daily_tasks pipeline uses build_profile, which derives weak_topics
    # from AdaptiveTestResult data, not from intake weak_sections.
    # intake weak_sections are stored in prep_state but NOT consumed by build_profile.
    print("NOTE: build_profile does NOT read intake.weak_sections.")
    print("weak_sections is stored but not consumed by the daily tasks pipeline.")
    print("This is a GAP — the P9 intake saves weak_sections but they don't")
    print("affect daily task distribution unless connected to the planner.")
    print()

    # Cleanup
    db.session.execute(db.text(f"DELETE FROM curator_state WHERE user_id IN ({ua.id},{ub.id})"))
    db.session.delete(ua); db.session.delete(ub)
    db.session.commit()
    print("Cleanup done.")
