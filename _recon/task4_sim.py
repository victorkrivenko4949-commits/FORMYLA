# -*- coding: utf-8 -*-
"""Task 4: Подтверждение приоритета слабых разделов."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app, db
from models import User, AdaptiveTask
from models_curator import CuratorState
from daily_tasks.services import get_daily_tasks
import json
from collections import defaultdict

CANONICAL = ['algebra', 'number_theory', 'geometry', 'combinatorics', 'logic']

with app.app_context():
    # Create two simulated profiles in CuratorState
    grade = 9

    # ── Student A: weak geometry + logic ──
    existing_a = User.query.filter_by(email='sim_weak@x.test').first()
    if existing_a:
        db.session.delete(existing_a)
        db.session.commit()
    user_a = User(email='sim_weak@x.test', name='Sim Weak', preferred_grade=grade)
    user_a.set_password('test')
    db.session.add(user_a)
    db.session.commit()

    cs_a = CuratorState.query.filter_by(user_id=user_a.id).first()
    if cs_a is None:
        cs_a = CuratorState(user_id=user_a.id)
        db.session.add(cs_a)
    prep = dict(cs_a.prep_state) if isinstance(cs_a.prep_state, dict) else {}
    prep['intake'] = {
        'completed': True,
        'completed_at': '2026-08-01T00:00:00',
        'class_level': grade,
        'goal': 'just_grow',
        'goal_auto': 'just_grow',
        'experience': 'none',
        'daily_tasks': 10,
        'weak_sections': ['geometry', 'logic'],
        'weak_priority': True,
        'prior_mu': 2.0,
        'prior_sigma': 2.0,
        'answers': {'class': '9', 'goal': 'just_grow', 'experience': 'none', 'time': 'm30', 'weak_sections': ['geometry', 'logic']},
        'anchor_results': [],
    }
    cs_a.prep_state = prep
    cs_a.level_mu = 2.0
    cs_a.level_sigma = 2.0
    cs_a.onboarding_done = True
    cs_a.level_by_section = {
        'algebra': 2.0, 'number_theory': 2.0, 'geometry': 2.0, 'combinatorics': 2.0, 'logic': 2.0
    }
    db.session.commit()

    # ── Student B: no weak sections ──
    existing_b = User.query.filter_by(email='sim_none@x.test').first()
    if existing_b:
        db.session.delete(existing_b)
        db.session.commit()
    user_b = User(email='sim_none@x.test', name='Sim None', preferred_grade=grade)
    user_b.set_password('test')
    db.session.add(user_b)
    db.session.commit()

    cs_b = CuratorState.query.filter_by(user_id=user_b.id).first()
    if cs_b is None:
        cs_b = CuratorState(user_id=user_b.id)
        db.session.add(cs_b)
    prep_b = dict(cs_b.prep_state) if isinstance(cs_b.prep_state, dict) else {}
    prep_b['intake'] = {
        'completed': True,
        'completed_at': '2026-08-01T00:00:00',
        'class_level': grade,
        'goal': 'just_grow',
        'goal_auto': 'just_grow',
        'experience': 'none',
        'daily_tasks': 10,
        'weak_sections': [],
        'weak_priority': False,
        'prior_mu': 2.0,
        'prior_sigma': 2.0,
        'answers': {'class': '9', 'goal': 'just_grow', 'experience': 'none', 'time': 'm30', 'weak_sections': ['dont_know']},
        'anchor_results': [],
    }
    cs_b.prep_state = prep_b
    cs_b.level_mu = 2.0
    cs_b.level_sigma = 2.0
    cs_b.onboarding_done = True
    cs_b.level_by_section = {
        'algebra': 2.0, 'number_theory': 2.0, 'geometry': 2.0, 'combinatorics': 2.0, 'logic': 2.0
    }
    db.session.commit()

    print(f"Student A (weak geometry+logic): id={user_a.id}")
    print(f"Student B (no weak): id={user_b.id}")

    # Now simulate 5 days of get_daily_tasks
    print("\n=== SIMULATION: 5 DAYS ===")
    print(f"{'Day':<6} {'Student':<8} " + " ".join(f"{s:<16}" for s in CANONICAL) + " TOTAL")

    for day in range(1, 6):
        for label, uid in [("A/WEAK", user_a.id), ("B/NONE", user_b.id)]:
            data = get_daily_tasks(uid)
            items = data.get('items', [])
            counts = defaultdict(int)
            for item in items:
                topic = item.get('topic', '').strip().lower()
                # normalize
                from services.anchors import _normalize_section
                topic = _normalize_section(topic)
                if topic in CANONICAL:
                    counts[topic] += 1
                else:
                    counts['other'] += 1
            line = f"  D{day:<4} {label:<8} "
            for s in CANONICAL:
                line += f"{counts.get(s, 0):<16} "
            line += f"  {sum(counts.values())}"
            print(line)

    # Cleanup
    print("\n--- CLEANUP ---")
    db.session.execute(db.text(f"DELETE FROM curator_state WHERE user_id IN ({user_a.id}, {user_b.id})"))
    db.session.delete(user_a)
    db.session.delete(user_b)
    db.session.commit()
    print("Simulation users deleted.")
