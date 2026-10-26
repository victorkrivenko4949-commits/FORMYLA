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


def _next_day(uid, lesson_id, days=1):
    """Симулируем следующий день: сдвигаем дату урока назад."""
    _backdate(uid, lesson_id, days=days)


def test_rotation_split_1_of_6(pilot_user):
    """Блок из шести: метод, 4 практики, пробник — и повторяется.

    Одно занятие в день: после завершения сдвигаем дату урока на день
    назад (симуляция следующего дня) и продолжаем.
    """
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
        # …и «наступает следующий день»
        _next_day(uid, lesson['id'])


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
    _next_day(uid, lesson['id'])  # одно занятие в день — «наступает завтра»

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


def test_current_practice_theme(pilot_user):
    """Тема берётся только с текущего занятия-практики."""
    uid = pilot_user.id
    # занятие 1 — метод: темы нет
    lesson = session_plan.current_lesson(uid)
    assert lesson['lesson_type'] == 'method'
    assert session_plan.current_practice_theme(uid) is None
    assert session_plan.complete_current_lesson(uid, 'method')
    _next_day(uid, lesson['id'])  # одно занятие в день — «наступает завтра»

    # занятие 2 — практика с темой
    lesson = session_plan.current_lesson(uid)
    assert lesson['lesson_type'] == 'practice'
    db.session.execute(db.text(
        "UPDATE curator_lessons SET theme = 'Делимость' WHERE id = :lid"),
        {'lid': lesson['id']})
    db.session.commit()
    assert session_plan.current_practice_theme(uid) == 'Делимость'

    # завершённая практика не отдаёт тему (нет назначенного занятия)
    db.session.add(DailyTaskSet(user_id=uid, target_date=date.today(),
                                status='ready'))
    db.session.commit()
    s = DailyTaskSet.query.filter_by(user_id=uid).order_by(
        DailyTaskSet.id.desc()).first()
    db.session.add(DailyTaskItem(
        daily_set_id=s.id, position=1, task_text='Задача', user_answer='1'))
    db.session.commit()
    assert session_plan.maybe_complete_practice(uid, s.id) is True
    assert session_plan.current_practice_theme(uid) is None


# ── План на 6 занятий + пропуски в долг (владелец, 26.10) ──────────────────

def _backdate(uid, lesson_id, days):
    """Переносим дату назначения занятия на N дней назад."""
    db.session.execute(db.text(
        "UPDATE curator_lessons SET assigned_date = :d WHERE id = :lid"),
        {'d': date.today() - timedelta(days=days), 'lid': lesson_id})
    db.session.commit()


def test_plan_six_entries_and_current_first(pilot_user):
    """План — ровно 6 слотов: текущее первое, остальные upcoming."""
    uid = pilot_user.id
    info = session_plan.session_info(uid)
    assert info['active'] is True
    assert len(info['plan']) == 6
    assert info['plan'][0]['state'] == 'current'
    assert info['plan'][0]['lesson_type'] == info['lesson_type']
    assert all(p['state'] == 'upcoming' for p in info['plan'][1:])
    # порядок типов: метод, 4 практики, пробник
    assert [p['lesson_type'] for p in info['plan']] == [
        'method', 'practice', 'practice', 'practice', 'practice', 'probnik']
    assert info['debts_count'] == 0


def test_stale_lesson_goes_to_debt(pilot_user):
    """Пропущенный день: занятие уходит в долг, план двигается дальше."""
    uid = pilot_user.id
    lesson = session_plan.current_lesson(uid)  # слот 1 — метод
    assert lesson['lesson_type'] == 'method'
    _backdate(uid, lesson['id'], days=1)

    info = session_plan.session_info(uid)
    # старое занятие — skipped (долг)
    assert info['debts_count'] == 1
    assert info['debts'][0]['lesson_type'] == 'method'
    # план пошёл дальше: слот 2 — практика, а не снова метод
    assert info['position_in_block'] == 2
    assert info['lesson_type'] == 'practice'
    # план как обычно из 6 слотов, начиная с текущего
    assert info['plan'][0]['slot'] == 2
    assert len(info['plan']) == 6


def test_multi_day_absence_creates_debt_per_day(pilot_user):
    """3 дня отсутствия = 3 занятия в долг, план сдвинулся на 3 слота."""
    uid = pilot_user.id
    lesson = session_plan.current_lesson(uid)  # слот 1
    _backdate(uid, lesson['id'], days=3)

    info = session_plan.session_info(uid)
    assert info['debts_count'] == 3, (
        f'ожидалось 3 долга, получено {info["debts_count"]}')
    # слот 4 — практика (1 метод + 2 практики пропущены)
    assert info['position_in_block'] == 4
    assert info['lesson_type'] == 'practice'
    # все долги — не назначенные и не завершённые
    for d in info['debts']:
        row = [l for l in _all_lessons(uid) if l['seq'] == d['seq']][0]
        assert row['status'] == 'skipped'


def test_skip_does_not_stall_cycle(pilot_user):
    """Пропуск не тормозит ротацию: после долга следующий слот — по счёту."""
    uid = pilot_user.id
    lesson = session_plan.current_lesson(uid)  # слот 1 — метод
    _backdate(uid, lesson['id'], days=1)
    session_plan.session_info(uid)            # метод ушёл в долг

    # текущее — слот 2 (практика): завершаем (одно занятие в день)
    cur = session_plan.current_lesson(uid)
    assert cur['lesson_type'] == 'practice'
    assert session_plan.complete_current_lesson(uid, 'practice') is True
    # рефреш дашборда в тот же день — НЕ создаёт новое занятие
    assert session_plan.current_lesson(uid) is None
    assert session_plan.session_info(uid)['today_done'] is True
    # «наступает завтра» — следующий слот 3, а не «заново метод»
    _next_day(uid, cur['id'])
    nxt = session_plan.current_lesson(uid)
    assert nxt['lesson_type'] == 'practice'
    assert session_plan.session_info(uid)['position_in_block'] == 3
    assert session_plan.session_info(uid)['debts_count'] == 1  # долг за метод остался


def test_completed_then_absent_accrues_debt(pilot_user):
    """Завершил занятие и пропал на 3 дня — долги за пропущенные дни всё равно набегают."""
    uid = pilot_user.id
    lesson = session_plan.current_lesson(uid)          # слот 1 — метод
    assert session_plan.complete_current_lesson(uid, 'method') is True
    # после завершения назначенного нет; датировано занятие 3 дня назад
    _backdate(uid, lesson['id'], days=3)

    info = session_plan.session_info(uid)
    # пропущены дни 2 и 3 (день 1 — завершён) → 2 долга
    assert info['debts_count'] == 2, info['debts_count']
    # последний урок был слот 1 → сегодня слот 1+3=4 (практика)
    assert info['position_in_block'] == 4
    assert info['lesson_type'] == 'practice'


def test_sync_idempotent_no_duplicates(pilot_user):
    """Повторная синхронизация в тот же день не создаёт дублей долгов."""
    uid = pilot_user.id
    lesson = session_plan.current_lesson(uid)
    _backdate(uid, lesson['id'], days=2)

    session_plan._advance_stale(uid)
    session_plan._advance_stale(uid)          # повторный вызов — no-op
    session_plan.session_info(uid)            # и чтение плана тоже

    lessons = _all_lessons(uid)
    seqs = [l['seq'] for l in lessons]
    assert len(seqs) == len(set(seqs)), 'появились дубли seq'
    skipped = [l for l in lessons if l['status'] == 'skipped']
    assert len(skipped) == 2, f'ожидалось 2 долга, получено {len(skipped)}'


def test_non_pilot_gets_nothing(app, monkeypatch):
    """Не-пилот: session_info неактивен, занятия не создаются."""
    monkeypatch.setattr(pilot_mod, 'is_pilot_user', lambda u=None, **k: False)
    u = User(email='np@test.ru', nickname='np')
    db.session.add(u)
    db.session.commit()
    uid = u.id
    assert session_plan.session_info(uid) == {'active': False}
    assert session_plan.current_lesson(uid) is None
    session_plan._advance_stale(uid)
    session_plan._sync(uid)
    assert _all_lessons(uid) == []


def test_completion_hook_syncs_without_dashboard(pilot_user):
    """Завершение без захода на дашборд: долг начисляется, создаётся и
    закрывается именно СЕГОДНЯШНЕЕ занятие (слот по счёту)."""
    uid = pilot_user.id
    # слот 1 — метод: создаём и датруем 2 дня назад (не завершаем)
    lesson = session_plan.current_lesson(uid)
    assert lesson['lesson_type'] == 'method'
    _backdate(uid, lesson['id'], days=2)

    # сразу хук практики (без session_info): синхронизация внутри хука
    s = DailyTaskSet(user_id=uid, target_date=date.today(), status='ready')
    db.session.add(s)
    db.session.commit()
    for pos in (1, 2):
        db.session.add(DailyTaskItem(
            daily_set_id=s.id, position=pos, task_text=f'Задача {pos}',
            user_answer='42'))
    db.session.commit()

    assert session_plan.maybe_complete_practice(uid, s.id) is True
    # долги начислены: день назначения (метод) + один день между = 2
    info = session_plan.session_info(uid)
    # завершён сегодняшний урок: слот 3 (после пропуска двух) — практика;
    # после завершения ротация сразу назначает следующий (слот 4) —
    # прежнее поведение: успевай делать больше одного в день
    assert info['lesson_type'] == 'practice'
    assert info['position_in_block'] == 4
    assert info['debts_count'] == 2
    # повторный вызов по тому же сету — ничего не создаёт и не закрывает
    assert session_plan.maybe_complete_practice(uid, s.id) is False


def test_refresh_after_completion_no_extra_debt(pilot_user):
    """Рефреш дашборда после завершения НЕ создаёт лишний долг.

    Путь A (закрыл и ушёл) и путь B (закрыл и обновил страницу) должны
    давать одинаковый результат: следующий день — следующий слот, 0 долгов.
    """
    uid = pilot_user.id
    lesson = session_plan.current_lesson(uid)  # слот 1 — метод
    assert session_plan.complete_current_lesson(uid, 'method') is True

    # «рефреш дашборда» в тот же день: план показывается, но новое занятие
    # не назначается (today_done)
    info = session_plan.session_info(uid)
    assert info['today_done'] is True
    assigned = [l for l in _all_lessons(uid) if l['status'] == 'assigned']
    assert not assigned, 'рефреш назначил лишнее занятие'

    # следующий день: без долгов, следующий слот 2 — практика
    _next_day(uid, lesson['id'])
    info = session_plan.session_info(uid)
    assert info['debts_count'] == 0
    assert info['position_in_block'] == 2
    assert info['lesson_type'] == 'practice'


def test_old_or_foreign_set_cannot_complete(pilot_user, app):
    """Старый (вчерашний) сет или чужой сет не закрывают текущую практику."""
    uid = pilot_user.id
    lesson = session_plan.current_lesson(uid)  # метод
    _next_day(uid, lesson['id'], days=1)
    info = session_plan.session_info(uid)  # теперь практика (слот 2)
    assert info['lesson_type'] == 'practice'

    # вчерашний сет ученика — не закрывает сегодняшнюю практику
    old_set = DailyTaskSet(user_id=uid, target_date=date.today() - timedelta(days=1),
                           status='ready')
    db.session.add(old_set)
    db.session.commit()
    for pos in (1, 2):
        db.session.add(DailyTaskItem(daily_set_id=old_set.id, position=pos,
                                     task_text=f'З {pos}', user_answer='1'))
    db.session.commit()
    assert session_plan.maybe_complete_practice(uid, old_set.id) is False

    # чужой сет — тоже нет
    other = User(email='other@test.ru', nickname='other')
    db.session.add(other)
    db.session.commit()
    foreign = DailyTaskSet(user_id=other.id, target_date=date.today(), status='ready')
    db.session.add(foreign)
    db.session.commit()
    for pos in (1, 2):
        db.session.add(DailyTaskItem(daily_set_id=foreign.id, position=pos,
                                     task_text=f'З {pos}', user_answer='1'))
    db.session.commit()
    assert session_plan.maybe_complete_practice(uid, foreign.id) is False

    # сегодняшняя практика осталась открытой
    cur = [l for l in _all_lessons(uid) if l['status'] == 'assigned']
    assert cur and cur[0]['lesson_type'] == 'practice'


def test_non_pilot_stale_lesson_untouched(pilot_user, app, monkeypatch):
    """Не-пилот с «просроченным» занятием: хуки не меняют его записи."""
    uid = pilot_user.id
    lesson = session_plan.current_lesson(uid)  # метод, назначен сегодня
    _backdate(uid, lesson['id'], days=2)       # просрочен на 2 дня

    monkeypatch.setattr(pilot_mod, 'is_pilot_user', lambda u=None, **k: False)
    session_plan._sync(uid)
    session_plan.maybe_complete_practice(uid, 999)
    db.session.rollback()  # monkeypatch мог оставить открытую транзакцию

    monkeypatch.setattr(pilot_mod, 'is_pilot_user', lambda u=None, **k: True)
    lessons = _all_lessons(uid)
    # ровно одно занятие, всё ещё назначено (не skipped, долгов нет)
    assert len(lessons) == 1
    assert lessons[0]['status'] == 'assigned'
    info = session_plan.session_info(uid)
    assert info['debts_count'] == 2  # теперь, как пилот, получает долги


def test_sync_failure_does_not_break_request(pilot_user, monkeypatch):
    """Сбой синхронизации не роняет запрос: ошибка проглатывается,
    транзакция откатывается, план всё равно отдаётся."""
    uid = pilot_user.id
    session_plan.current_lesson(uid)

    def boom(*a, **k):
        raise RuntimeError('sync failed')
    monkeypatch.setattr(session_plan, '_advance_stale', boom)

    info = session_plan.session_info(uid)  # не бросает
    assert info['active'] is True
    monkeypatch.undo()
    # сессия жива: дальнейшие запросы работают
    assert session_plan.session_info(uid)['active'] is True


def test_same_set_id_method_and_practice_both_count(pilot_user):
    """id метод-сетов и практик независимы: одинаковый id не блокирует другой тип.

    Регрессия ревью 26.10.2026: проверка повтора должна быть с lesson_type.
    """
    uid = pilot_user.id
    # день 1: метод — закрываем методом-сетом с id=1
    lesson = session_plan.current_lesson(uid)
    assert lesson['lesson_type'] == 'method'
    m = session_plan._pick_method(uid)
    mw = MethodWeekSet(user_id=uid, method_code=m['code'], method_name=m['name'],
                       week_start=date.today(),
                       tasks_json=json.dumps([{'position': 1}, {'position': 2}]))
    db.session.add(mw)
    db.session.commit()
    for pos in (1, 2):
        db.session.add(MethodWeekAnswer(set_id=mw.id, position=pos,
                                        user_id=uid, user_answer='1'))
    db.session.commit()
    assert mw.id == 1  # в чистой базе первый сет получает id=1
    assert session_plan.maybe_complete_method(uid) is True
    assert session_plan.complete_current_lesson(uid, 'method') is False

    # день 2: практика — сет дня ТОЖЕ с id=1 (другая таблица!)
    _next_day(uid, lesson['id'])
    cur = session_plan.current_lesson(uid)
    assert cur['lesson_type'] == 'practice'
    s = DailyTaskSet(user_id=uid, target_date=date.today(), status='ready')
    db.session.add(s)
    db.session.commit()
    assert s.id == 1
    for pos in (1, 2):
        db.session.add(DailyTaskItem(daily_set_id=s.id, position=pos,
                                     task_text=f'З {pos}', user_answer='1'))
    db.session.commit()
    # одинаковый id НЕ мешает: практика закрывается своим сетом
    assert session_plan.maybe_complete_practice(uid, s.id) is True
    # и повтор каждого сета отклоняется
    assert session_plan.maybe_complete_practice(uid, s.id) is False
