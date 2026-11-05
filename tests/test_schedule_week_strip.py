# -*- coding: utf-8 -*-
"""PILOT_SCHEDULE_DAYS_V1 — недельная полоса плана (7 дней) и выходные.

Проверяем (03.11.2026):
  * session_info: полоса из 7 ячеек — «Работяга» 6 занятий + 1 выходной,
    «Спокойный» 3 занятия + 4 выходных (по выбранным на /schedule дням);
  * сегодня выходной: занятие не создаётся, today_rest=True,
    next_lesson_day указывает ближайший день занятий;
  * пропущенные ВЫХОДНЫЕ не становятся долгами (в долг — только дни
    занятий).
"""
from datetime import date, datetime, timedelta

import pytest

import services.pilot as pilot_mod
from models import db, User
from curator import session_plan


@pytest.fixture
def pilot_user(app, monkeypatch):
    monkeypatch.setattr(pilot_mod, 'is_pilot_user', lambda u=None, **k: True)
    u = User(email='week@test.ru', nickname='week_pilot',
             is_guest=False, role='student')
    db.session.add(u)
    db.session.commit()
    return u


def _add_sub(uid, plan):
    from models import Subscription
    db.session.add(Subscription(
        user_id=uid, plan=plan, status='active',
        started_at=datetime.utcnow() - timedelta(days=14),
        expires_at=datetime.utcnow() + timedelta(days=30),
        is_beta_access=False, is_trial=False))
    db.session.commit()


def _choose_days(uid, plan, days):
    from services.schedule_days import save_user_days
    assert save_user_days(uid, days, plan) is True


def _backdate(uid, lesson_id, days):
    db.session.execute(db.text(
        "UPDATE curator_lessons SET assigned_date = :d WHERE id = :lid"),
        {'d': date.today() - timedelta(days=days), 'lid': lesson_id})
    db.session.commit()


# ── Полоса 7 дней ──────────────────────────────────────────────────────

def test_weekly_strip_calm_3_lessons_4_rest(pilot_user):
    """«Спокойный»: 7 ячеек — 3 занятия и 4 выходных."""
    uid = pilot_user.id
    _add_sub(uid, 'premium_calm')
    _choose_days(uid, 'premium_calm', [0, 2, 4])  # Пн/Ср/Пт

    s = session_plan.session_info(uid)
    assert s['active'] is True
    assert len(s['plan']) == 7
    lessons = [p for p in s['plan'] if p['lesson_type'] != 'rest']
    rests = [p for p in s['plan'] if p['lesson_type'] == 'rest']
    assert len(lessons) == 3
    assert len(rests) == 4
    assert s['lessons_per_week'] == 3
    assert s['rest_days_count'] == 4
    # у карточек занятий есть слот ротации 1..6, у выходных — нет
    for p in lessons:
        assert p['slot'] in (1, 2, 3, 4, 5, 6)
        assert p['day_label'] in ('Пн', 'Ср', 'Пт')
    for p in rests:
        assert p['slot'] is None
        assert p['lesson_label'] == 'выходной'
        assert p['day_label'] in ('Вт', 'Чт', 'Сб', 'Вс')


def test_weekly_strip_intense_6_lessons_1_rest(pilot_user):
    """«Работяга»: 7 ячеек — 6 занятий и 1 выходной."""
    uid = pilot_user.id
    _add_sub(uid, 'premium_intense')
    _choose_days(uid, 'premium_intense', [0, 1, 2, 3, 4, 5])  # Пн–Сб

    s = session_plan.session_info(uid)
    assert s['active'] is True
    assert len(s['plan']) == 7
    lessons = [p for p in s['plan'] if p['lesson_type'] != 'rest']
    rests = [p for p in s['plan'] if p['lesson_type'] == 'rest']
    assert len(lessons) == 6
    assert len(rests) == 1
    assert rests[0]['day_label'] == 'Вс'
    assert s['lessons_per_week'] == 6
    assert s['rest_days_count'] == 1


def test_no_choice_fallback_default_days(pilot_user):
    """Без выбора дней — дефолт тарифа: Пн/Ср/Пт, полоса из 7 дней."""
    uid = pilot_user.id
    _add_sub(uid, 'premium_calm')
    # дни НЕ выбираем (гейт /schedule ещё не пройден) — дефолт «Спокойного»

    s = session_plan.session_info(uid)
    assert s['active'] is True
    # полоса-неделя по дефолту тарифа
    assert len(s['plan']) == 7
    assert s['lessons_per_week'] == 3
    assert s['rest_days_count'] == 4
    lessons = [p for p in s['plan'] if p['lesson_type'] != 'rest']
    assert all(p['day_label'] in ('Пн', 'Ср', 'Пт') for p in lessons)


# ── Выходной сегодня ────────────────────────────────────────────────────

def test_today_rest_no_lesson(pilot_user):
    """Сегодня выходной: занятие не создаётся, баннер — «выходной»."""
    uid = pilot_user.id
    _add_sub(uid, 'premium_calm')
    # Пн/Ср/Пт; если сегодня не один из них — выходной
    _choose_days(uid, 'premium_calm', [0, 2, 4])

    today_wd = date.today().weekday()
    if today_wd in (0, 2, 4):
        pytest.skip('сегодня день занятий — выходной не проверить')

    lesson = session_plan.current_lesson(uid)
    assert lesson is None, 'в выходной занятие создаваться не должно'

    s = session_plan.session_info(uid)
    assert s['active'] is True
    assert s['today_rest'] is True
    assert s['plan'][0]['lesson_type'] == 'rest'
    assert s['plan'][0]['is_today'] is True
    assert s['next_lesson_day'] in ('Пн', 'Ср', 'Пт')


def test_today_lesson_day(pilot_user):
    """Сегодня день занятий: текущее занятие создано, полоса начинается с него."""
    uid = pilot_user.id
    _add_sub(uid, 'premium_intense')
    _choose_days(uid, 'premium_intense', [0, 1, 2, 3, 4, 5])

    lesson = session_plan.current_lesson(uid)
    if date.today().weekday() == 6:  # Вс — выходной
        assert lesson is None
        return

    assert lesson is not None
    s = session_plan.session_info(uid)
    assert s['today_rest'] is False
    assert s['plan'][0]['lesson_type'] != 'rest'
    assert s['plan'][0]['state'] == 'current'


# ── Выходные не становятся долгами ──────────────────────────────────────

def test_rest_days_no_debts(pilot_user):
    """Пропуск 3 дней (вчера — день занятий, позавчера и ранее — выходные).

    Долги: само перенесённое занятие + 1 за вчерашний день занятий.
    За выходные (позавчера и 3 дня назад) долгов быть не должно.
    """
    uid = pilot_user.id
    _add_sub(uid, 'premium_calm')
    today_wd = date.today().weekday()
    # дни занятий: вчера, сегодня, завтра (позавчера и 3 дня назад — выходные)
    chosen = [(today_wd - 1) % 7, today_wd, (today_wd + 1) % 7]
    _choose_days(uid, 'premium_calm', chosen)

    # создаём занятие и «уходим» на 3 дня
    lesson = session_plan.current_lesson(uid)
    assert lesson is not None
    _backdate(uid, lesson['id'], days=3)

    s = session_plan.session_info(uid)
    # долг за перенос + долг за вчерашний день занятий = 2;
    # за выходные (позавчера и 3 дня назад) долгов нет
    assert s['debts_count'] == 2, (
        f'ожидались 2 долга, получено {s["debts_count"]}: '
        f'{[d["assigned_date"] for d in s["debts"]]}')
    debt_dates = {d['assigned_date'][:10] for d in s['debts']}
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    backdated = (date.today() - timedelta(days=3)).isoformat()
    assert debt_dates == {yesterday, backdated}
    # дни долгов — только дни занятий (кроме искусственно перенесённого)
    yesterday_wd = (today_wd - 1) % 7
    assert yesterday_wd in chosen


# ── Неделя 1 (диагностика) в полосе плана ─────────────────────────────

def test_week_one_strip_shows_method_after_diagnostics(pilot_user):
    """Неделя 1: дни диагностики — без номера слота, а первый день занятий
    ПОСЛЕ неё — слот 1, изучение метода (баг 05.11.2026: все карточки
    показывались практикой, т.к. тип считался по сегодняшней дате)."""
    from models import Subscription
    uid = pilot_user.id
    db.session.add(Subscription(
        user_id=uid, plan='premium_intense', status='active',
        started_at=datetime.utcnow() - timedelta(days=3),
        expires_at=datetime.utcnow() + timedelta(days=30),
        is_beta_access=False, is_trial=False))
    db.session.commit()
    _choose_days(uid, 'premium_intense', [0, 1, 2, 3, 4, 5])
    w1e = (datetime.utcnow() - timedelta(days=3) + timedelta(days=7)).date()

    s = session_plan.session_info(uid)
    assert s['active'] is True
    assert s['week_one'] is True
    assert s['diag_day_num'] == 4
    lessons = []
    for i, p in enumerate(s['plan']):
        if p['lesson_type'] == 'rest':
            continue
        day = date.today() + timedelta(days=i)
        if day < w1e:
            assert p['diag'] is True and p['slot'] is None
            assert p['lesson_type'] == 'practice'
        else:
            lessons.append(p)
    assert lessons, 'в полосе должны быть дни после диагностики'
    assert lessons[0]['slot'] == 1
    assert lessons[0]['lesson_type'] == 'method'
    assert [p['slot'] for p in lessons] == list(range(1, len(lessons) + 1))
