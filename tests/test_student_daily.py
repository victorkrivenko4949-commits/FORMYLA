import json
from datetime import date, timedelta

import pytest
from flask import g

from daily_tasks.models import DailyTaskItem, DailyTaskSet
from daily_tasks.services import today_in_user_tz
from method_week.models import MethodWeekAnswer, MethodWeekSet
from models import ParentChildLink, T10Group, T10GroupMember, db


def _login(client, user):
    g.pop('_login_user', None)
    with client.session_transaction() as session:
        session['_user_id'] = str(user.id)


@pytest.fixture(params=['teacher', 'parent'])
def linked_client(request, app, client, student_users, teacher_user, parent_user):
    from app import parent_only_account
    app.before_request(parent_only_account)
    student, unrelated = student_users[:2]
    if request.param == 'teacher':
        viewer = teacher_user
        group = T10Group(name='Группа', teacher_id=viewer.id, invite_code='AB7DEF')
        db.session.add(group)
        db.session.flush()
        link = T10GroupMember(group_id=group.id, user_id=student.id, status='accepted')
        db.session.add(link)
    else:
        viewer = parent_user
        link = ParentChildLink.query.filter_by(parent_id=viewer.id, child_id=student.id).first()
        if not link:
            link = ParentChildLink(parent_id=viewer.id, child_id=student.id)
            db.session.add(link)
        link.status = 'accepted'
    db.session.commit()
    _login(client, viewer)
    return client, student, unrelated, link


def test_saved_daily_tasks_are_read_only_and_sorted(linked_client):
    client, student, _, _ = linked_client
    daily = DailyTaskSet(user_id=student.id, target_date=today_in_user_tz(), status='ready')
    db.session.add(daily)
    db.session.flush()
    db.session.add_all([
        DailyTaskItem(daily_set_id=daily.id, position=2, task_text='Второе условие'),
        DailyTaskItem(daily_set_id=daily.id, position=1, task_text=r'Найдите $x^2$',
                      figure_svg_path='f2_10226_8.svg', slot_kind='review',
                      difficulty_level=2, user_answer='<b>4</b>', is_correct=False,
                      correct_answer='9', solution='Разбор решения', ai_feedback='НЕ ВЫВОДИТЬ'),
    ])
    db.session.commit()

    url = f'/student/{student.id}/daily'
    response = client.get(url)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert body.index('Найдите $x^2$') < body.index('Второе условие')
    assert '/static/daily_figures/f2_10226_8.svg' in body
    assert 'Неверно' in body and 'Не решал' in body and '&lt;b&gt;4&lt;/b&gt;' in body
    assert '<summary>Ответ и решение</summary>' in body
    assert 'НЕ ВЫВОДИТЬ' not in body and 'name="answer"' not in body
    assert client.post(url).status_code in (302, 405)
    assert DailyTaskSet.query.count() == 1


def test_student_daily_permissions_and_empty_state(linked_client):
    client, student, unrelated, link = linked_client
    url = f'/student/{student.id}/daily'
    assert 'Сегодня задачи ещё не выданы' in client.get(url).get_data(as_text=True)
    assert client.get(f'/student/{unrelated.id}/daily').status_code == 403
    link.status = 'pending'
    db.session.commit()
    assert client.get(url).status_code == 403
    link.status = 'accepted'
    student.share_progress = False
    db.session.commit()
    assert client.get(url).status_code == 403
    assert client.get(f'/student/{student.id}').status_code == 403


def test_method_day_uses_students_week_set_and_answers(linked_client, monkeypatch):
    client, student, _, _ = linked_client
    monkeypatch.setattr('curator.session_plan._pilot', lambda uid: uid == student.id)
    monkeypatch.setattr('curator.session_plan._lessons', lambda uid: [
        dict(assigned_date=date.today(), lesson_type='method', method_code='A1'),
    ])
    today = today_in_user_tz()
    week = MethodWeekSet(
        user_id=student.id, week_start=today - timedelta(days=today.weekday()),
        method_code='G1', method_name='Метод из набора', status='ready',
        lesson_md='### Введение\nРазбор метода $a^2$. <script>plain text</script>',
        tasks_json=json.dumps([dict(statement=f'Условие метода {i}') for i in range(1, 4)]),
    )
    db.session.add(week)
    db.session.flush()
    db.session.add(MethodWeekAnswer(
        set_id=week.id, user_id=student.id, position=2, user_answer='42', is_correct=True,
    ))
    db.session.commit()

    response = client.get(f'/student/{student.id}/daily')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Метод из набора' in body and 'Разбор метода $a^2$' in body
    assert '&lt;script&gt;plain text&lt;/script&gt;' in body
    assert body.count('Условие метода') == 3
    assert 'Ответ ученика:' in body and '42</span>' in body
    assert body.count('>Не решал</p>') == 2 and '>Верно</p>' in body
    assert 'id="mw-root"' not in body
    assert MethodWeekSet.query.count() == 1
