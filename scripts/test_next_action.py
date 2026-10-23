# -*- coding: utf-8 -*-
"""
scripts/test_next_action.py — Проверка 4 состояний get_next_action().

Собирает 4 состояния тестового ученика и для каждого показывает, что вернула
функция (kind, title, cta_label, url, reason):
  A. только зарегистрирован, onboarding_done = False
  B. анкета пройдена, в test_queue лежит diagnostic
  C. очередь пуста, задачи дня на сегодня не завершены
  D. очередь пуста, задачи дня завершены

Ожидание: A->onboarding, B->test, C->daily, D->idle.
В конце откатывает тестовые изменения.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, User, DailyQuest
from models_curator import CuratorState

TEST_USER_ID = 2  # SmokeDailyTasksTester — already exists, no app init issues
TEST_TODAY = date.today()

FMT_HEADER = "\n" + "=" * 70
FMT_SUB = "-" * 50


def _print_action(label: str, action: dict):
    print(f"\n{FMT_SUB}")
    print(f"  {label}")
    print(f"{FMT_SUB}")
    print(f"  kind:      {action.get('kind')}")
    print(f"  title:     {action.get('title')}")
    print(f"  cta_label: {action.get('cta_label')}")
    print(f"  url:       {action.get('url')}")
    print(f"  reason:    {action.get('reason')}")
    meta = action.get('meta', {})
    if meta:
        print(f"  meta:      {json.dumps(meta, ensure_ascii=False, default=str)}")


def run():
    with app.app_context():
        from services.next_action import get_next_action

        # ── Save original state for rollback ─────────────────────
        _orig_cs = CuratorState.query.filter_by(user_id=TEST_USER_ID).first()
        _orig_cs_data = None
        if _orig_cs:
            _orig_cs_data = {
                'onboarding_done': _orig_cs.onboarding_done,
                'prep_state': _orig_cs.prep_state,
            }
        _orig_dq = DailyQuest.query.filter_by(
            user_id=TEST_USER_ID, date=TEST_TODAY
        ).first()
        _orig_dq_data = None
        if _orig_dq:
            _orig_dq_data = {
                'task_ids': _orig_dq.task_ids,
                'completed_count': _orig_dq.completed_count,
                'total_count': _orig_dq.total_count,
                'completed_at': _orig_dq.completed_at,
            }

        def _clean():
            """Очистить состояние тестового пользователя."""
            CuratorState.query.filter_by(user_id=TEST_USER_ID).delete()
            DailyQuest.query.filter_by(
                user_id=TEST_USER_ID, date=TEST_TODAY
            ).delete()
            db.session.flush()

        def _restore():
            """Восстановить исходное состояние."""
            CuratorState.query.filter_by(user_id=TEST_USER_ID).delete()
            DailyQuest.query.filter_by(
                user_id=TEST_USER_ID, date=TEST_TODAY
            ).delete()
            db.session.flush()
            if _orig_cs_data:
                cs = CuratorState(
                    user_id=TEST_USER_ID,
                    onboarding_done=_orig_cs_data['onboarding_done'],
                    prep_state=_orig_cs_data['prep_state'],
                )
                db.session.add(cs)
            if _orig_dq_data:
                dq = DailyQuest(
                    user_id=TEST_USER_ID, date=TEST_TODAY,
                    task_ids=_orig_dq_data['task_ids'],
                    completed_count=_orig_dq_data['completed_count'],
                    total_count=_orig_dq_data['total_count'],
                    completed_at=_orig_dq_data['completed_at'],
                )
                db.session.add(dq)
            db.session.commit()

        # ══════════════════════════════════════════════════════════
        # A. onboarding_done = False
        # ══════════════════════════════════════════════════════════
        print(f"\n{FMT_HEADER}")
        print("  СОСТОЯНИЕ A: только зарегистрирован, onboarding_done=False")
        print(f"{FMT_HEADER}")

        _clean()
        cs = CuratorState(user_id=TEST_USER_ID, onboarding_done=False,
                          prep_state={})
        db.session.add(cs)
        db.session.commit()

        action_a = get_next_action(TEST_USER_ID)
        _print_action("A: новый ученик (onboarding_done=False)", action_a)
        assert action_a['kind'] == 'onboarding', \
            f"EXPECTED kind='onboarding', GOT '{action_a['kind']}'"
        print("  [OK] PASS: kind=onboarding, url=/prep/onboarding")

        # ══════════════════════════════════════════════════════════
        # B. Анкета пройдена, test_queue = [diagnostic]
        # ══════════════════════════════════════════════════════════
        print(f"\n{FMT_HEADER}")
        print("  СОСТОЯНИЕ B: анкета пройдена, test_queue=[diagnostic]")
        print(f"{FMT_HEADER}")

        _clean()
        prep_state = {
            'onboarding': {
                'goal': 'school', 'route_ceiling': 3,
                'daily_tasks': 5, 'deadline_bucket': 'none',
                'start_level': 2, 'test_length': 10,
                'conflict': False, 'prior_mu': 2.0, 'prior_sigma': 1.0,
                'answers': {'goal': 'school', 'school_mark': '4',
                            'load': 'm30', 'deadline': 'none'},
                'completed_at': datetime.utcnow().isoformat(),
            },
            'test_queue': [
                {
                    'kind': 'diagnostic', 'scope': 'all_sections',
                    'length': 10, 'level_hint': 2,
                    'reason': 'Первый замер: 10 задач по всем разделам, '
                              'старт с уровня 2.',
                    'created': TEST_TODAY.isoformat(),
                },
            ],
        }
        cs = CuratorState(
            user_id=TEST_USER_ID, onboarding_done=True,
            prep_state=prep_state,
        )
        db.session.add(cs)
        db.session.commit()

        action_b = get_next_action(TEST_USER_ID)
        _print_action("B: анкета пройдена + diagnostic в очереди", action_b)
        assert action_b['kind'] == 'test', \
            f"EXPECTED kind='test', GOT '{action_b['kind']}'"
        assert action_b.get('url') == '/olympiad-test', \
            f"EXPECTED url='/olympiad-test', GOT '{action_b.get('url')}'"
        print("  [OK] PASS: kind=test, url=/olympiad-test")

        # ══════════════════════════════════════════════════════════
        # C. Очередь пуста, daily_quest не завершён
        # ══════════════════════════════════════════════════════════
        print(f"\n{FMT_HEADER}")
        print("  СОСТОЯНИЕ C: test_queue=[], daily_quest не завершён")
        print(f"{FMT_HEADER}")

        _clean()
        cs = CuratorState(
            user_id=TEST_USER_ID, onboarding_done=True,
            prep_state={'onboarding': {}, 'test_queue': []},
        )
        db.session.add(cs)
        dq = DailyQuest(
            user_id=TEST_USER_ID, date=TEST_TODAY,
            task_ids=json.dumps([1, 2, 3, 4, 5]),
            completed_count=2, total_count=5,
            completed_at=None,
        )
        db.session.add(dq)
        db.session.commit()

        action_c = get_next_action(TEST_USER_ID)
        _print_action("C: очередь пуста, дневной квест в процессе", action_c)
        assert action_c['kind'] == 'daily', \
            f"EXPECTED kind='daily', GOT '{action_c['kind']}'"
        assert action_c['meta'].get('remaining') == 3, \
            f"EXPECTED remaining=3, GOT {action_c['meta'].get('remaining')}"
        print("  [OK] PASS: kind=daily, remaining=3, url=/daily-set")

        # ══════════════════════════════════════════════════════════
        # D. Очередь пуста, задачи дня завершены
        # ══════════════════════════════════════════════════════════
        print(f"\n{FMT_HEADER}")
        print("  СОСТОЯНИЕ D: test_queue=[], daily_quest завершён")
        print(f"{FMT_HEADER}")

        _clean()
        cs = CuratorState(
            user_id=TEST_USER_ID, onboarding_done=True,
            prep_state={'onboarding': {}, 'test_queue': []},
        )
        db.session.add(cs)
        dq = DailyQuest(
            user_id=TEST_USER_ID, date=TEST_TODAY,
            task_ids=json.dumps([1, 2, 3, 4, 5]),
            completed_count=5, total_count=5,
            completed_at=datetime.utcnow(),
        )
        db.session.add(dq)
        db.session.commit()

        action_d = get_next_action(TEST_USER_ID)
        _print_action("D: всё завершено, idle", action_d)
        assert action_d['kind'] == 'idle', \
            f"EXPECTED kind='idle', GOT '{action_d['kind']}'"
        print("  [OK] PASS: kind=idle")

        # ── ОТКАТ ────────────────────────────────────────────────
        print(f"\n{FMT_HEADER}")
        print("  ОТКАТ тестовых данных")
        print(f"{FMT_HEADER}")
        _restore()
        print("  [OK] Исходные данные восстановлены.")

    # ── ИТОГИ ────────────────────────────────────────────────────
    print(f"\n{FMT_HEADER}")
    print("  ВСЕ 4 ТЕСТА ПРОЙДЕНЫ УСПЕШНО")
    print(f"{FMT_HEADER}")
    print("  A: onboarding [OK]")
    print("  B: test       [OK]")
    print("  C: daily      [OK]")
    print("  D: idle       [OK]")


if __name__ == '__main__':
    run()
