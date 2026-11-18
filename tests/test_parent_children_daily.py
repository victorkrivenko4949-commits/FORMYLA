# -*- coding: utf-8 -*-
"""
tests/test_parent_children_daily.py — PARENT_CHILDREN_DAILY_V1.

Кнопка «К задачам дня ребёнка» на дашборде задач дня + страница
/parent/children-daily, где задачи дня каждого подтверждённого ребёнка
показаны отдельным блоком.

Run: pytest tests/test_parent_children_daily.py -v
"""
from __future__ import annotations

from datetime import date, datetime

from models import db, User, ParentChildLink
from daily_tasks.models import DailyTaskSet, DailyTaskItem


def _login(client, user):
    # Flask-Login кеширует g._login_user на уровне контекста приложения,
    # а conftest держит один app-context на весь тест — сбрасываем кеш,
    # иначе следующий запрос «помнит» предыдущего пользователя.
    from flask import g
    try:
        g.pop('_login_user', None)
    except Exception:
        pass
    with client.session_transaction() as s:
        s['_user_id'] = str(user.id)


def _mk_user(email: str, nickname: str, role: str = 'student',
             share_progress: bool = True) -> User:
    user = User(
        email=email,
        nickname=nickname,
        role=role,
        share_progress=share_progress,
        is_guest=False,
    )
    db.session.add(user)
    db.session.commit()
    return user


def _link(parent: User, child: User, status: str = 'accepted') -> ParentChildLink:
    link = ParentChildLink(
        parent_id=parent.id, child_id=child.id, status=status,
        responded_at=datetime.utcnow() if status == 'accepted' else None,
    )
    db.session.add(link)
    db.session.commit()
    return link


def _mk_set(child: User, today: date, items_spec, status: str = 'ready') -> DailyTaskSet:
    """items_spec: список (position, text, answered, is_correct)."""
    ds = DailyTaskSet(
        user_id=child.id, target_date=today, status=status, class_level=9,
    )
    db.session.add(ds)
    db.session.commit()
    for pos, text, answered, correct in items_spec:
        it = DailyTaskItem(
            daily_set_id=ds.id,
            position=pos,
            task_text=text,
            user_answer='ответ' if answered else None,
            is_correct=correct if answered else None,
            answered_at=datetime.utcnow() if answered else None,
        )
        db.session.add(it)
    db.session.commit()
    return ds


# ── Доступ и пустые состояния ────────────────────────────────────────────


def test_student_role_gets_403(app):
    """Не-родитель (ученик) на страницу задач дня детей не попадает."""
    student = _mk_user('cd_student@example.invalid', 'cd_student')
    with app.test_client() as c:
        _login(c, student)
        rv = c.get('/parent/children-daily')
    assert rv.status_code == 403, (
        f'Student must get 403, got {rv.status_code}'
    )


def test_anonymous_redirected_to_login(app):
    with app.test_client() as c:
        rv = c.get('/parent/children-daily')
    # anonymous: 302 на /auth или 401 API-стилем — оба «не пустили»
    assert rv.status_code in (302, 401), (
        f'Anonymous must be blocked, got {rv.status_code}'
    )


def test_parent_without_children_redirected_to_dashboard(app):
    """Нет подтверждённых детей — редирект в кабинет родителя."""
    parent = _mk_user('cd_parent0@example.invalid', 'cd_parent0', role='parent')
    with app.test_client() as c:
        _login(c, parent)
        rv = c.get('/parent/children-daily', follow_redirects=False)
    assert rv.status_code == 302, (
        f'No children -> redirect, got {rv.status_code}'
    )
    assert '/parent' in rv.headers['Location']


def test_pending_link_does_not_count(app):
    """Неподтверждённая привязка — как будто детей нет (редирект)."""
    parent = _mk_user('cd_parentp@example.invalid', 'cd_parentp', role='parent')
    child = _mk_user('cd_childp@example.invalid', 'cd_childp')
    _link(parent, child, status='pending')
    with app.test_client() as c:
        _login(c, parent)
        rv = c.get('/parent/children-daily', follow_redirects=False)
    assert rv.status_code == 302, 'Pending link must not open children daily'


# ── Содержимое страницы ───────────────────────────────────────────────────


def test_single_child_daily_visible(app):
    """Один ребёнок: задачи дня, статусы и прогресс видны, ответы — нет."""
    parent = _mk_user('cd_parent1@example.invalid', 'cd_parent1', role='parent')
    child = _mk_user('cd_child1@example.invalid', 'cd_child1')
    _link(parent, child)
    today = date.today()
    _mk_set(child, today, [
        (1, 'Найдите сумму чисел от 1 до 10 [TEST].', True, True),
        (2, 'Сколько делителей у числа 36 [TEST]?', False, None),
    ])

    with app.test_client() as c:
        _login(c, parent)
        rv = c.get('/parent/children-daily')

    assert rv.status_code == 200, (
        f'Got {rv.status_code} body={rv.get_data(as_text=True)[:300]}'
    )
    html = rv.get_data(as_text=True)
    assert 'cd_child1' in html, 'child nickname must be shown'
    assert 'сумму чисел от 1 до 10' in html
    assert 'Сколько делителей' in html
    assert 'Решено верно' in html
    assert 'Ещё не решено' in html
    assert '1 из 2' in html


def test_two_children_separate_blocks(app):
    """Два ребёнка: страница показывает задачи дня каждого отдельно."""
    parent = _mk_user('cd_parent2@example.invalid', 'cd_parent2', role='parent')
    child_a = _mk_user('cd_child_a@example.invalid', 'cd_child_a')
    child_b = _mk_user('cd_child_b@example.invalid', 'cd_child_b')
    _link(parent, child_a)
    _link(parent, child_b)
    today = date.today()
    _mk_set(child_a, today, [
        (1, 'Задача Аленки про шахматы [TEST].', True, True),
    ])
    _mk_set(child_b, today, [
        (1, 'Задача Бори про треугольник [TEST].', False, None),
    ])

    with app.test_client() as c:
        _login(c, parent)
        rv = c.get('/parent/children-daily')

    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    # оба ребёнка и их задачи — на одной странице, отдельными блоками
    assert 'cd_child_a' in html and 'cd_child_b' in html
    assert 'про шахматы' in html and 'про треугольник' in html
    # у каждого свой прогресс
    assert '1 из 1' in html and '0 из 1' in html


def test_hidden_progress_child_not_shown(app):
    """Ребёнок закрыл прогресс — задачи дня не показываем."""
    parent = _mk_user('cd_parent3@example.invalid', 'cd_parent3', role='parent')
    child = _mk_user('cd_child3@example.invalid', 'cd_child3', share_progress=False)
    _link(parent, child)
    today = date.today()
    _mk_set(child, today, [(1, 'Секретная задача [TEST].', False, None)])

    with app.test_client() as c:
        _login(c, parent)
        rv = c.get('/parent/children-daily')

    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'закрыл доступ' in html
    assert 'Секретная задача' not in html


def test_no_set_shows_honest_note(app):
    """Набора на сегодня нет — честная плашка вместо пустой страницы."""
    parent = _mk_user('cd_parent4@example.invalid', 'cd_parent4', role='parent')
    child = _mk_user('cd_child4@example.invalid', 'cd_child4')
    _link(parent, child)

    with app.test_client() as c:
        _login(c, parent)
        rv = c.get('/parent/children-daily')

    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'ещё не сформированы' in html


def test_correct_answers_not_leaked(app):
    """Ответы/решения в страницу не попадают (только условия и статусы)."""
    parent = _mk_user('cd_parent5@example.invalid', 'cd_parent5', role='parent')
    child = _mk_user('cd_child5@example.invalid', 'cd_child5')
    _link(parent, child)
    today = date.today()
    ds = DailyTaskSet(user_id=child.id, target_date=today, status='ready')
    db.session.add(ds)
    db.session.commit()
    it = DailyTaskItem(
        daily_set_id=ds.id, position=1,
        task_text='Чему равно 2+2 [TEST]?',
        correct_answer='4', solution='Решение: 2+2=4.',
    )
    db.session.add(it)
    db.session.commit()

    with app.test_client() as c:
        _login(c, parent)
        rv = c.get('/parent/children-daily')

    html = rv.get_data(as_text=True)
    assert 'Решение: 2+2=4' not in html, 'Solution must not leak to parent'


# ── Кнопка на дашборде задач дня ─────────────────────────────────────────


def test_dashboard_shows_button_for_parent(app):
    """Родитель с подтверждённым ребёнком видит кнопку на /daily_tasks."""
    parent = _mk_user('cd_parent6@example.invalid', 'cd_parent6', role='parent')
    child = _mk_user('cd_child6@example.invalid', 'cd_child6')
    _link(parent, child)

    with app.test_client() as c:
        _login(c, parent)
        rv = c.get('/daily_tasks', follow_redirects=True)

    assert rv.status_code == 200, (
        f'Dashboard returned {rv.status_code} '
        f'body={rv.get_data(as_text=True)[:300]}'
    )
    html = rv.get_data(as_text=True)
    assert '/parent/children-daily' in html, 'button link must be rendered'
    assert 'К задачам дня ребёнка' in html


def test_dashboard_no_button_without_children(app):
    """Без привязанных детей кнопки нет (и ученику её не видно)."""
    student = _mk_user('cd_student7@example.invalid', 'cd_student7')

    with app.test_client() as c:
        _login(c, student)
        rv = c.get('/daily_tasks', follow_redirects=True)

    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert '/parent/children-daily' not in html
