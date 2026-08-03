# -*- coding: utf-8 -*-
"""
scripts/test_engine_wiring.py — End-to-end: level_engine wiring test
with scope="all_sections" multi-section distribution.

1. Setup: onboarding_done + test_queue with scope=all_sections
2. Состояние level_engine до теста
3. TEST_LENGTH задач распределены по ВСЕМ разделам через distribution_plan()
   + pick_all_sections_tasks(), 70% верно, 30% неверно
4. Таблица: #, section, diff_lvl, canonical, correct, mu глобальный
5. ИТОГ по разделам: для каждого раздела n, mu, sigma из by_section
6. skipped если есть
7. Проверка: минимум 3 разных раздела
8. Откат
"""
from __future__ import annotations

import json, os, sys, random
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, User, DailyQuest
from models_curator import CuratorState

TEST_USER_ID = 2
TEST_TODAY = date.today()
TEST_LENGTH = 10


def run():
    with app.app_context():
        from services.level_engine import get_state, set_prior, record_result
        from services.olympiad_adaptive import (
            _all_tasks, get_sections,
            distribution_plan, pick_all_sections_tasks,
        )

        # ── Save original ─────────────────────────────────────────────
        _orig_cs = CuratorState.query.filter_by(user_id=TEST_USER_ID).first()
        _orig_data = None
        if _orig_cs:
            _orig_data = (_orig_cs.onboarding_done, _orig_cs.prep_state,
                          _orig_cs.level_mu, _orig_cs.level_sigma,
                          _orig_cs.level_by_section, _orig_cs.level_updated_at)
        _orig_dq = DailyQuest.query.filter_by(user_id=TEST_USER_ID, date=TEST_TODAY).first()

        def restore():
            db.session.rollback()
            CuratorState.query.filter_by(user_id=TEST_USER_ID).delete()
            DailyQuest.query.filter_by(user_id=TEST_USER_ID, date=TEST_TODAY).delete()
            db.session.commit()
            if _orig_data:
                cs = CuratorState(user_id=TEST_USER_ID,
                                  onboarding_done=_orig_data[0],
                                  prep_state=_orig_data[1],
                                  level_mu=_orig_data[2],
                                  level_sigma=_orig_data[3],
                                  level_by_section=_orig_data[4],
                                  level_updated_at=_orig_data[5])
                db.session.add(cs)
            if _orig_dq:
                db.session.add(_orig_dq)
            db.session.commit()

        try:
            # ── Clean ─────────────────────────────────────────────────
            db.session.rollback()
            CuratorState.query.filter_by(user_id=TEST_USER_ID).delete()
            DailyQuest.query.filter_by(user_id=TEST_USER_ID, date=TEST_TODAY).delete()
            db.session.commit()

            user = db.session.get(User, TEST_USER_ID)
            grade_int = int(getattr(user, 'preferred_grade', 9) or 9)
            print("=" * 72)
            print(f"  TEST: engine wiring  user={TEST_USER_ID}  grade={grade_int}  length={TEST_LENGTH}")
            print(f"  scope=all_sections")
            print("=" * 72)

            # ── 1. SETUP ──────────────────────────────────────────────
            print("\n--- 1. SETUP: set_prior + test_queue (scope=all_sections) ---")
            level_hint = 2
            set_prior(TEST_USER_ID, 2.0, 1.0, source="test_setup")
            cs = CuratorState.query.filter_by(user_id=TEST_USER_ID).first()
            cs.onboarding_done = True
            cs.prep_state = {'onboarding': {'goal': 'school', 'start_level': 2, 'test_length': TEST_LENGTH},
                             'test_queue': [{'kind': 'diagnostic', 'scope': 'all_sections',
                                              'length': TEST_LENGTH, 'level_hint': level_hint,
                                              'reason': f'{TEST_LENGTH} задач по всем разделам.',
                                              'created': TEST_TODAY.isoformat()}]}
            db.session.commit()
            tq = cs.prep_state.get('test_queue', [])
            print(f"  test_queue: {len(tq)} item(s), scope={tq[0]['scope']}, length={tq[0]['length']}")

            # ── 2. BEFORE ─────────────────────────────────────────────
            print("\n--- 2. LEVEL_ENGINE BEFORE ---")
            s_before = get_state(TEST_USER_ID)
            print(f"  mu={s_before['mu']:.3f} sigma={s_before['sigma']:.3f} level={s_before['level']}")
            print(f"  by_section: {s_before['by_section']}")

            # ── 3. DISTRIBUTION PLAN ──────────────────────────────────
            print(f"\n--- 3. DISTRIBUTION PLAN (scope=all_sections) ---")
            by_sec = s_before.get('by_section') or {}
            plan = distribution_plan(grade_int, TEST_LENGTH, by_sec, level_hint)
            print(f"  Plan ({len(plan)} sections):")
            for p in plan:
                print(f"    {p['section']:<30s} count={p['count']} start_level={p['start_level']}")

            # ── 4. PICK TASKS ─────────────────────────────────────────
            print(f"\n--- 4. PICK TASKS (pick_all_sections_tasks) ---")
            result = pick_all_sections_tasks(grade_int, TEST_LENGTH, by_sec, level_hint)
            tasks = result['tasks']
            skipped = result.get('skipped', [])
            print(f"  Picked: {len(tasks)} tasks, skipped: {len(skipped)}")

            if skipped:
                print(f"\n  SKIPPED:")
                for sk in skipped:
                    print(f"    section={sk['section']} level={sk['level']} reason={sk['reason']}")

            # ── 5. SIMULATE TEST ──────────────────────────────────────
            print(f"\n--- 5. TEST ({len(tasks)} tasks, ~70% correct) ---")
            ct = max(0, int(len(tasks) * 0.7))
            print(f"  correct_threshold={ct}/{len(tasks)}")
            print(f"  {'#':>3} {'section':<30s} {'d_lvl':>6} {'c_lvl':>5} {'correct':>7} {'mu':>8}")
            print(f"  {'-'*3} {'-'*30} {'-'*6} {'-'*5} {'-'*7} {'-'*8}")

            sections_seen: set = set()
            for i, t in enumerate(tasks):
                sec_t = (t.get('section') or '?').strip()
                sections_seen.add(sec_t)
                dl = t.get('level', 1)
                cl = max(1, min(5, int(dl)))
                ok = i < ct
                record_result(TEST_USER_ID, sec_t, cl, correct=ok)
                mu = get_state(TEST_USER_ID)['mu']
                print(f"  {i+1:>3} {sec_t:<30s} {dl:>6} {cl:>5} {str(ok):>7} {mu:>8.3f}")

            # ── 6. RESULTS ────────────────────────────────────────────
            print("\n--- 6. RESULTS ---")
            s_after = get_state(TEST_USER_ID)
            print(f"  GLOBAL: mu={s_after['mu']:.3f} (was {s_before['mu']:.3f}, "
                  f"delta {s_after['mu']-s_before['mu']:+.3f}) "
                  f"sigma={s_after['sigma']:.3f} level={s_after['level']}")

            # ── 7. BY_SECTION SUMMARY ─────────────────────────────────
            print("\n--- 7. BY_SECTION AFTER ---")
            by_sec_after = s_after.get('by_section') or {}
            if by_sec_after:
                print(f"  {'section':<30s} {'n':>4} {'mu':>8} {'sigma':>8}")
                print(f"  {'-'*30} {'-'*4} {'-'*8} {'-'*8}")
                for sec_name, sec_data in sorted(by_sec_after.items()):
                    print(f"  {sec_name:<30s} {sec_data.get('n',0):>4} "
                          f"{sec_data.get('mu',0):>8.3f} {sec_data.get('sigma',0):>8.3f}")
            else:
                print("  (empty)")

            # ── 8. UPDATE PREP_STATE ──────────────────────────────────
            db.session.expire_all()
            cs = CuratorState.query.filter_by(user_id=TEST_USER_ID).first()
            if cs:
                ps = dict(cs.prep_state or {})
                tq_l = list(ps.get('test_queue', []))
                tq_l = tq_l[1:] if tq_l else []
                ps['test_queue'] = tq_l
                ps['last_test'] = {
                    'date': TEST_TODAY.isoformat(),
                    'tasks': len(tasks),
                    'correct': ct,
                    'wrong': len(tasks) - ct,
                    'mu_before': round(s_before['mu'], 3),
                    'mu_after': round(s_after['mu'], 3),
                    'level_before': s_before['level'],
                    'level_after': s_after['level'],
                    'sections': sorted(sections_seen),
                    'skipped': skipped,
                }
                cs.prep_state = ps
                db.session.commit()

            # ── 9. CHECKS ─────────────────────────────────────────────
            print("\n--- 9. CHECKS ---")
            errors = []

            # Check: at least 3 different sections
            unique_sec = len(sections_seen)
            if unique_sec >= 3:
                print(f"  [OK] {unique_sec} different sections involved: {sorted(sections_seen)}")
            else:
                msg = f"  [ERROR] Only {unique_sec} sections involved (need >= 3): {sorted(sections_seen)}"
                print(msg)
                errors.append(msg)

            # Check: mu changed
            if s_after['mu'] != s_before['mu']:
                print(f"  [OK] mu changed: {s_before['mu']:.3f} -> {s_after['mu']:.3f}")
            else:
                msg = "  [ERROR] mu unchanged"
                print(msg)
                errors.append(msg)

            # Check: test_queue emptied
            cs = CuratorState.query.filter_by(user_id=TEST_USER_ID).first()
            tq_f = (cs.prep_state or {}).get('test_queue', []) if cs else []
            if len(tq_f) == 0:
                print(f"  [OK] test_queue empty")
            else:
                msg = f"  [ERROR] test_queue not empty: {len(tq_f)} items"
                print(msg)
                errors.append(msg)

            # Check: by_section has entries for all seen sections
            for sec_name in sections_seen:
                if sec_name in by_sec_after:
                    sec = by_sec_after[sec_name]
                    print(f"  [OK] by_section['{sec_name}']: n={sec.get('n')} "
                          f"mu={sec.get('mu',0):.3f} sigma={sec.get('sigma',0):.3f}")
                else:
                    msg = f"  [ERROR] by_section missing '{sec_name}'"
                    print(msg)
                    errors.append(msg)

            # Check: skipped reported
            if skipped:
                print(f"  [!]️  SKIPPED: {len(skipped)} allocation(s)")
                for sk in skipped:
                    print(f"       {sk['section']}: level={sk['level']} — {sk['reason']}")

            # Check: tasks count
            if len(tasks) == TEST_LENGTH:
                print(f"  [OK] tasks={len(tasks)} == TEST_LENGTH={TEST_LENGTH}")
            else:
                msg = f"  [!]️ tasks={len(tasks)} != TEST_LENGTH={TEST_LENGTH} (skipped={len(skipped)})"
                print(msg)

            # Check: last_test populated
            cs = CuratorState.query.filter_by(user_id=TEST_USER_ID).first()
            lt = (cs.prep_state or {}).get('last_test', {}) if cs else {}
            if lt.get('tasks') == len(tasks):
                print(f"  [OK] last_test.tasks={lt.get('tasks')}")
            else:
                msg = f"  [ERROR] last_test.tasks={lt.get('tasks')} expected={len(tasks)}"
                print(msg)
                errors.append(msg)

            if errors:
                print(f"\n{'='*72}")
                print(f"  [ERROR] {len(errors)} CHECK(S) FAILED")
                print(f"{'='*72}")
            else:
                print(f"\n{'='*72}")
                print(f"  [OK] ALL CHECKS PASSED")
                print(f"{'='*72}")

        finally:
            print("\n--- ROLLBACK ---")
            restore()
            print("  [OK] Done.")


if __name__ == '__main__':
    run()
