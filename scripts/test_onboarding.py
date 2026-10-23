# -*- coding: utf-8 -*-
"""
scripts/test_onboarding.py — Прогон 5 сценариев через onboarding.py напрямую.
Показывает уровень каждого якоря и причину пропуска второго.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, AdaptiveTask
from models_curator import CuratorState

TEST_GRADE = 9

SCENARIOS = [
    {
        "label": "1: olympiad/region/True,True",
        "answers": [
            ("goal", "olympiad"), ("olymp_reach", "region"),
            ("load", "m60"), ("deadline", "mid"),
        ],
        "anchor_correct": [True, True],
    },
    {
        "label": "2: olympiad/region/False,False",
        "answers": [
            ("goal", "olympiad"), ("olymp_reach", "region"),
            ("load", "m60"), ("deadline", "mid"),
        ],
        "anchor_correct": [False, False],
    },
    {
        "label": "3: school/3/True,True",
        "answers": [
            ("goal", "school"), ("school_mark", "3"),
            ("load", "m15"), ("deadline", "none"),
        ],
        "anchor_correct": [True, True],
    },
    {
        "label": "4: exam/dunno/True,False",
        "answers": [
            ("goal", "exam"), ("exam_score", "dunno"),
            ("load", "m30"), ("deadline", "soon"),
        ],
        "anchor_correct": [True, False],
    },
    {
        "label": "5: fun/never/True,True",
        "answers": [
            ("goal", "fun"), ("prior_exp", "never"),
            ("load", "m90"), ("deadline", "none"),
        ],
        "anchor_correct": [True, True],
    },
]


def backup_state(uid):
    cs = CuratorState.query.filter_by(user_id=uid).first()
    if not cs:
        return None
    return {
        'onboarding_done': cs.onboarding_done,
        'prep_state': dict(cs.prep_state) if cs.prep_state else {},
        'goal_text': cs.goal_text,
        'level_mu': cs.level_mu,
        'level_sigma': cs.level_sigma,
        'level_by_section': cs.level_by_section,
        'level_updated_at': cs.level_updated_at,
    }


def restore_state(uid, bkp):
    if not bkp:
        return
    cs = CuratorState.query.filter_by(user_id=uid).first()
    if not cs:
        return
    cs.onboarding_done = bkp['onboarding_done']
    cs.prep_state = bkp['prep_state']
    cs.goal_text = bkp['goal_text']
    cs.level_mu = bkp['level_mu']
    cs.level_sigma = bkp['level_sigma']
    cs.level_by_section = bkp['level_by_section']
    cs.level_updated_at = bkp['level_updated_at']
    db.session.commit()


def reset_onboarding(uid):
    cs = CuratorState.query.filter_by(user_id=uid).first()
    if cs:
        cs.onboarding_done = False
        ps = dict(cs.prep_state) if cs.prep_state else {}
        ps.pop('onboarding', None)
        ps.pop('test_queue', None)
        cs.prep_state = ps
        cs.level_mu = None
        cs.level_sigma = None
        cs.level_by_section = None
        cs.level_updated_at = None
        db.session.commit()


def set_grade(uid, grade):
    from models import User
    u = db.session.get(User, uid)
    if u:
        u.preferred_grade = grade
        db.session.commit()


def run_one(uid, sc):
    from services.onboarding import start, answer, submit_anchor, finish
    from services.level_engine import get_state

    label = sc['label']
    answers = sc['answers']
    correct_flags = sc['anchor_correct']

    reset_onboarding(uid)
    set_grade(uid, TEST_GRADE)

    result = start(uid)
    if result.get('done') or result.get('error'):
        print(f"  [{label}] ERROR start: {result}")
        return None

    for qid, key in answers:
        result = answer(uid, qid, key)
        if result.get('error'):
            print(f"  [{label}] ERROR answer {qid}: {result['error']}")
            return None

    a1_id, a1_lvl, a1_ok = 'N/A', 'N/A', 'N/A'
    a2_id, a2_lvl, a2_ok = 'N/A', 'N/A', 'N/A'
    a2_skip = None

    if result.get('anchor'):
        anchor1 = result['anchor']
        a1_id = anchor1['task_id']
        a1_lvl = anchor1.get('level', '?')

        if correct_flags[0]:
            t = db.session.get(AdaptiveTask, a1_id)
            user_ans = t.correct_answer if t else "42"
        else:
            user_ans = "wrong_answer_xyz"

        result = submit_anchor(uid, a1_id, user_ans)
        a1_ok = str(result.get('correct', '?'))
        a2_skip = result.get('anchor2_skipped_reason')

        if result.get('anchor'):
            anchor2 = result['anchor']
            a2_id = anchor2['task_id']
            a2_lvl = anchor2.get('level', '?')

            if len(correct_flags) > 1 and correct_flags[1]:
                t = db.session.get(AdaptiveTask, a2_id)
                user_ans2 = t.correct_answer if t else "42"
            else:
                user_ans2 = "wrong_answer_xyz"

            result = submit_anchor(uid, a2_id, user_ans2)
            a2_ok = str(result.get('correct', '?'))
    else:
        a2_id = '—'
        a2_lvl = '—'
        a2_ok = '—'

    finish_data = finish(uid)
    r = finish_data.get('result', {})

    if not r:
        print(f"  [{label}] finish without result: {finish_data}")
        return None

    st = get_state(uid)
    mu_match = abs(float(st.get('mu', 0))
                   - float(r.get('prior_mu', 0))) < 0.01

    return {
        'goal': r.get('goal', '?'),
        'marker': answers[1][1] if len(answers) > 1 else '?',
        'a1_id': str(a1_id), 'a1_lvl': str(a1_lvl), 'a1_ok': a1_ok,
        'a2_id': str(a2_id), 'a2_lvl': str(a2_lvl), 'a2_ok': a2_ok,
        'a2_skip': a2_skip,
        'prior_mu': r.get('prior_mu', 0),
        'prior_sigma': r.get('prior_sigma', 0),
        'start_level': r.get('start_level', 0),
        'test_length': r.get('test_length', 0),
        'daily_tasks': r.get('daily_tasks', 0),
        'conflict': r.get('conflict', False),
        'mu_match': mu_match,
    }


def print_header():
    print()
    print(f"{'сценарий':<35} {'goal':<9} {'маркер':<8} "
          f"{'якорь1(id/ур/ok)':<27} {'якорь2(id/ур/ok)':<27} "
          f"{'mu':>5} {'ста':>6} {'длн':>4} {'з/д':>4} {'кнф':>4} {'mu'}  {'причина пропуска я2'}")
    print("-" * 200)


def print_row(label, r):
    a1 = f"{r['a1_id']}/L{r['a1_lvl']}/{r['a1_ok']}"
    a2 = f"{r['a2_id']}/L{r['a2_lvl']}/{r['a2_ok']}"
    mu_ok = 'OK' if r['mu_match'] else 'BAD'
    cf = 'T' if r['conflict'] else '-'
    skip = (r.get('a2_skip') or '')[:60]
    print(f"{label:<35} {r['goal']:<9} {r['marker']:<8} "
          f"{a1:<27} {a2:<27} "
          f"{r['prior_mu']:>5.2f} {r['prior_sigma']:>6.2f} {r['start_level']:>4} "
          f"{r['test_length']:>4} {cf:>4} {mu_ok}  {skip}")


def print_prep(uid):
    cs = CuratorState.query.filter_by(user_id=uid).first()
    if not cs:
        print("\nCuratorState missing")
        return
    ps = cs.prep_state or {}
    print("\n" + "=" * 70)
    print("prep_state['onboarding']:")
    print("=" * 70)
    print(json.dumps(ps.get('onboarding', {}), indent=2,
                     ensure_ascii=False, default=str))
    print("\n" + "=" * 70)
    print("prep_state['test_queue']:")
    print("=" * 70)
    print(json.dumps(ps.get('test_queue', []), indent=2,
                     ensure_ascii=False, default=str))


def main():
    app.config['TESTING'] = True

    with app.test_request_context():
        with app.app_context():
            uid = 1
            print(f"test_onboarding.py — user_id={uid}")

            bkp = backup_state(uid)
            print(f"   backup: {'OK' if bkp else 'none'}")

            rows = []
            ok = True

            for sc in SCENARIOS:
                row = run_one(uid, sc)
                if row:
                    rows.append((sc['label'], row))
                    if not row['mu_match']:
                        ok = False
                        print(f"  mu mismatch: prior_mu={row['prior_mu']}")
                else:
                    ok = False

            print("\n" + "=" * 200)
            print("RESULTS")
            print("=" * 200)
            print_header()
            for label, row in rows:
                print_row(label, row)
            print("-" * 200)

            if ok:
                print("All mu match!")
            else:
                print("Some mu mismatch")

            print_prep(uid)
            restore_state(uid, bkp)
            print(f"\nbackup restored")

            print(f"\n{'PASSED' if ok else 'FAILED'}")
            return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
