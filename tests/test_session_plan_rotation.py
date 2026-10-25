# -*- coding: utf-8 -*-
"""
T-ROT: ротация занятий 1-из-6 (curator/session_plan.py).

Проверяем (ревью 26.10.2026):
  * разбивка блока: 1=метод, 2-5=практика, 6=пробник (и так по кругу);
  * прогресс двигается только завершением занятия;
  * ОДИН отвеченный сет дня закрывает РОВНО ОДНУ практику
    (повторный вызов хука не создаёт и не закрывает следующую);
  * метод-сет с чужим method_code не закрывает назначенное занятие-метод.
"""
import json
from datetime import date, timedelta

import pytest

import method_week.models  # noqa: F401 — таблицы метод-сетов в тестовой БД
import services.pilot as pilot_mod
from models import db, User
from daily_tasks.models import DailyTaskSet, DailyTaskItem
from method_week.models import MethodWeekSet, MethodWeekAnswer
from models_olympiad import OlympiadTask
from curator import session_plan


@pytest.fixture
def pilot_user(app, monkeypatch):
    """Пилотный пользователь: гейт is_pilot_user подменяем на True."""
    monkeypatch.setattr(pilot_mod, 'is_pilot_user', lambda u=None, **k: True)
    u = User(email='rot@test.ru', nickname='rot')
    db.session.add(u)
    db.session.commit()
    return u


def _all_lessons(uid):
    return session_plan._lessons(uid)


def test_rotation_split_1_of_6(pilot_user):
    """Блок из шести: метод, 4 практики, пробник — и повторяется."""
    uid = pilot_user.id
    expected = ['method', 'practice', 'practice', 'practice',
                'practice', 'probnik'] * 2  # два полных блока
    for i, want in enumerate(expected):
        lesson = session_plan.current_lesson(uid)
        assert lesson is not None, f'шаг {i}: занятие не создано'
        assert lesson['lesson_type'] == want, (
            f'шаг {i}: ожидался {want}, получен {lesson["lesson_type"]}')
        assert lesson['status'] == 'assigned'
        # завершаем текущее занятие его же типом
        assert session_plan.complete_current_lesson(uid, want) is True


def test_no_progress_without_completion(pilot_user):
    """Повторный вызов current_lesson не создаёт второе назначенное занятие."""
    uid = pilot_user.id
    first = session_plan.current_lesson(uid)
    assert first is not None
    again = session_plan.current_lesson(uid)
    assert again['id'] == first['id'], 'появилось лишнее назначенное занятие'


def test_one_daily_set_closes_exactly_one_practice(pilot_user):
    """Один отвеченный сет закрывает одну практику — и только одну.

    Регрессия 26.10.2026: раньше повторный вызов хука по тому же сету
    создавал следующую практику и сразу её закрывал.
    """
    uid = pilot_user.id
    # занятие 1 — метод: создаём и закрываем напрямую
    lesson = session_plan.current_lesson(uid)
    assert lesson['lesson_type'] == 'method'
    assert session_plan.complete_current_lesson(uid, 'method')

    # занятие 2 — практика
    lesson = session_plan.current_lesson(uid)
    assert lesson['lesson_type'] == 'practice'

    # сет дня с двумя отвеченными задачами
    s = DailyTaskSet(user_id=uid, target_date=date.today(), status='ready')
    db.session.add(s)
    db.session.commit()
    for pos in (1, 2):
        db.session.add(DailyTaskItem(
            daily_set_id=s.id, position=pos, task_text=f'Задача {pos}', user_answer='42'))
    db.session.commit()

    # первый вызов — закрывает практику
    assert session_plan.maybe_complete_practice(uid, s.id) is True
    # повторный вызов по тому же сету — НЕ создаёт и НЕ закрывает новую
    assert session_plan.maybe_complete_practice(uid, s.id) is False

    lessons = _all_lessons(uid)
    completed = [l for l in lessons if l['status'] == 'completed']
    assigned = [l for l in lessons if l['status'] == 'assigned']
    assert len(completed) == 2, 'закрылось больше двух занятий одним сетом'
    assert len(assigned) == 0, 'хук создал новое занятие'
    # у закрытой практики зафиксирован сет-источник
    practice = [l for l in completed if l['lesson_type'] == 'practice'][0]
    assert practice['completed_set_id'] == s.id


def test_method_code_mismatch_does_not_complete(pilot_user):
    """Метод-сет с чужим method_code не закрывает занятие-метод."""
    uid = pilot_user.id
    lesson = session_plan.current_lesson(uid)
    assert lesson['lesson_type'] == 'method'
    # назначаем занятию конкретный метод
    db.session.execute(db.text(
        "UPDATE curator_lessons SET method_code = 'assigned_method' "
        "WHERE id = :lid"), {'lid': lesson['id']})
    db.session.commit()

    # метод-сет ДРУГОГО метода, все задачи отвечены
    other = MethodWeekSet(user_id=uid, method_code='other_method',
                          method_name='Другой',
                          week_start=date.today() - timedelta(days=7),
                          tasks_json=json.dumps(
                              [{'position': 1}, {'position': 2}]))
    db.session.add(other)
    db.session.commit()
    for pos in (1, 2):
        db.session.add(MethodWeekAnswer(
            set_id=other.id, position=pos, user_id=uid, user_answer='1'))
    db.session.commit()

    assert session_plan.maybe_complete_method(uid) is False
    assert session_plan._current_assigned(uid)['status'] == 'assigned'

    # а сет назначенного метода — закрывает
    own = MethodWeekSet(user_id=uid, method_code='assigned_method',
                       method_name='Назначенный',
                       week_start=date.today(),
                       tasks_json=json.dumps(
                           [{'position': 1}, {'position': 2}]))
    db.session.add(own)
    db.session.commit()
    for pos in (1, 2):
        db.session.add(MethodWeekAnswer(
            set_id=own.id, position=pos, user_id=uid, user_answer='1'))
    db.session.commit()
    assert session_plan.maybe_complete_method(uid) is True


def test_pick_probnik_skips_empty(pilot_user):
    """Пробник без задач не выбирается."""
    from sqlalchemy import text
    uid = pilot_user.id
    # олимпиада не важна: создаём два пробника, у первого задач нет
    db.session.execute(text(
        "INSERT INTO olympiad_probniks (code, title, competition, grade, type, number, is_published, sort_order, created_at) "
        "VALUES ('empty_p', 'Пустой', 'ВсОШ', 9, 'topic', 1, TRUE, 1, CURRENT_TIMESTAMP), "
        "('full_p', 'Полный', 'ВсОШ', 9, 'topic', 2, TRUE, 2, CURRENT_TIMESTAMP)"))
    full = db.session.execute(text(
        "SELECT id FROM olympiad_probniks WHERE code = 'full_p'")).fetchone()
    db.session.add(OlympiadTask(
        probnik_id=full[0], number='1.1', condition_md='условие',
        idea_md='идея', solution_md='решение', method_primary='M1'))
    db.session.commit()

    picked = session_plan._pick_probnik(uid, 'vsosh', set())
    assert picked is not None
    assert picked['code'] == 'full_p', 'выбран пробник без задач'
