# -*- coding: utf-8 -*-
"""Срез убран (2026-09): задачи дня доступны сразу после анкеты,
уровень берётся из анкеты (prior_mu), план показывает динамический темп."""
import json
from datetime import date, datetime, timedelta

import pytest


@pytest.fixture
def intake_user(app):
    """Пользователь с определённым уровнем анкеты (mu)."""
    import models_curator
    from models import db, User

    def make(mu, grade=8):
        u = User(email=f"mu{mu}@t.test", name=f"mu{mu}", is_guest=False,
                 preferred_grade=grade)
        db.session.add(u)
        db.session.flush()
        cs = models_curator.CuratorState(
            user_id=u.id, grade=grade,
            prep_state={'intake': {'completed': True, 'prior_mu': mu,
                                   'daily_tasks': 5}},
        )
        db.session.add(cs)
        db.session.commit()
        return u
    return make


def test_level_from_intake(app, intake_user):
    """Задачи дня после анкеты идут на уровень из анкеты, а не по классу."""
    from daily_tasks.profile import build_profile

    with app.app_context():
        weak = intake_user(1.0)   # «удалось решить 1 задачу»
        strong = intake_user(4.0) # опытный

        p_weak = build_profile(weak.id)
        p_strong = build_profile(strong.id)

        # Калибровочные темы: уровень должен совпасть с mu анкеты.
        lv_weak = [t['target_level'] for t in p_weak['topics_full'] if t['calibration']]
        lv_strong = [t['target_level'] for t in p_strong['topics_full'] if t['calibration']]
        assert lv_weak and all(lv == 1 for lv in lv_weak), lv_weak
        assert lv_strong and all(lv == 4 for lv in lv_strong), lv_strong

        # И в общий класс-ожидаемый (его читает банк) - тоже mu.
        assert p_weak['class_expected_level'] == 1
        assert p_strong['class_expected_level'] == 4


def test_cycle_not_blocked(app, client, intake_user):
    """get_cycle_info больше не блокирует задачи дня."""
    from curator.monthly_cycle import get_cycle_info

    with app.app_context():
        u = intake_user(2.5)
        info = get_cycle_info(u.id)
        # Если цикл ещё не создан (intake без build_or_get_cycle) — не active.
        assert info.get('blocked') is False or not info.get('active')


def test_pace_honest_recalc(app, intake_user):
    """Пропущеные дни появляются в темпе: need_per_day растёт."""
    from models import db, OlympiadPrep, PrepDay, PrepPlan
    from routes.prep import plan_pace

    with app.app_context():
        oly = OlympiadPrep(slug='toly', name='TestOly', short_name='TestOly',
                           stages='[]', grades='[8]', is_active=True)
        db.session.add(oly)
        db.session.flush()
        u = intake_user(3.0)
        today = date.today()
        plan = PrepPlan(user_id=u.id, olympiad_id=oly.id,
                        target_stage='Школьный',
                        start_date=today - timedelta(days=4),
                        target_date=today + timedelta(days=6),
                        daily_task_count=5, status='active')
        db.session.add(plan)
        db.session.flush()

        days = []
        for i in range(11):  # 4 прошлых, сегодня, 6 будущих
            d = today - timedelta(days=4) + timedelta(days=i)
            st = 'completed' if i in (2, 3) else 'upcoming'  # вчера и позавчера
            ids = list(range(i * 100, i * 100 + 5))
            days.append(PrepDay(plan_id=plan.id, date=d,
                                problem_ids=json.dumps(ids),
                                completed_problem_ids=json.dumps(ids if st == 'completed' else []),
                                status=st))
            db.session.add(days[-1])
        db.session.commit()

        pace = plan_pace(plan, days)
        # Осталось: 2 дня по 5 из прошлых + сегодня 5 + 6 будущих по 5.
        # remaining = 9 дней по 5 = 45; days_left+1=7; ceil(45/7)=7 > 5 -> behind
        assert pace["remaining_problems"] == 45
        assert pace["need_per_day"] == 7
        assert pace['behind'] is True
        assert pace['streak'] == 2
        assert pace["minutes_per_day"] == 42


def test_pace_finished(app, intake_user):
    """Всё решено — темп уже не нужен."""
    from models import db, OlympiadPrep, PrepDay, PrepPlan
    from routes.prep import plan_pace

    with app.app_context():
        oly = OlympiadPrep(slug='toly2', name='T2', short_name='T2',
                           stages='[]', grades='[8]', is_active=True)
        db.session.add(oly)
        db.session.flush()
        u = intake_user(3.0)
        today = date.today()
        plan = PrepPlan(user_id=u.id, olympiad_id=oly.id,
                        target_stage='Финал', start_date=today - timedelta(days=1),
                        target_date=today + timedelta(days=5),
                        daily_task_count=5, status='active')
        db.session.add(plan)
        db.session.flush()
        db.session.add(PrepDay(plan_id=plan.id, date=today,
                               problem_ids=json.dumps([1, 2, 3, 4, 5]),
                               completed_problem_ids=json.dumps([1, 2, 3, 4, 5]),
                               status='completed'))
        db.session.commit()
        pace = plan_pace(plan)
        assert pace['remaining_problems'] == 0
        assert pace['on_track'] is True
