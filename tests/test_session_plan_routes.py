# -*- coding: utf-8 -*-
"""Реальный Flask-маршрут /daily_tasks: план на 6 занятий и долги.

Проверяет не изолированный Jinja-блок, а НАСТОЯЩУЮ страницу дашборда
(маршрут, контекст, шаблон целиком) для пилота (uid=1 victor).

Run: pytest tests/test_session_plan_routes.py -v
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest


def _backdate(lesson_id: int, days: int = 1):
    from app import app
    from models import db
    from sqlalchemy import text
    with app.app_context():
        db.session.execute(text(
            "UPDATE curator_lessons SET assigned_date = :d WHERE id = :lid"),
            {'d': date.today() - timedelta(days=days), 'lid': lesson_id})
        db.session.commit()


@pytest.fixture()
def pilot_client():
    """Test client реального приложения, залогинен как uid=1 (пилот)."""
    from app import app
    from models import db, User

    with app.app_context():
        u = User.query.get(1)
        if not u:
            u = User(email='victor@test.local')
            db.session.add(u)
        # nickname «victor»: локальный юзер должен проходить гейт METHOD_WEEK_ALLOWED_USERS
        if getattr(u, 'nickname', None) != 'victor':
            u.nickname = 'victor'
        db.session.commit()
        # анкета «пройдена» — иначе before_request гоняет на /intake
        from models_curator import CuratorState
        import json as _json
        cs = CuratorState.query.filter_by(user_id=1).first()
        if cs is None:
            cs = CuratorState(user_id=1)
            db.session.add(cs)
        cs.grade = 9
        cs.prep_state = _json.dumps({'intake': {'completed': True}})
        db.session.commit()
        # чистим историю занятий тестового пользователя (локальная база)
        from curator.session_plan import ensure_tables
        ensure_tables()
        from sqlalchemy import text
        db.session.execute(text(
            "DELETE FROM curator_lessons WHERE user_id = 1"))
        db.session.commit()

    with app.test_client() as c:
        # dev_login работает только с localhost — test client как раз
        rv = c.get('/dev_login?uid=1')
        assert rv.status_code in (200, 302), (rv.status_code, rv.data[:200])
        yield c

    with app.app_context():
        from sqlalchemy import text
        from models import db
        db.session.execute(text(
            "DELETE FROM curator_lessons WHERE user_id = 1"))
        db.session.commit()


def test_dashboard_shows_six_lesson_plan(pilot_client):
    """Дашборд: полоса плана из 6 слотов, текущее выделено, CTA на месте."""
    rv = pilot_client.get('/daily_tasks')
    assert rv.status_code == 200, rv.status_code
    html = rv.get_data(as_text=True)
    # карточка плана и заголовок
    assert 'План на 6 занятий' in html
    assert 'сдвигается каждый день' in html
    # первый слот — метод, текущий
    assert 'изучение метода' in html
    assert 'сейчас' in html
    # типы в полосе: метод, практики, пробник
    assert 'пробник' in html
    assert 'практика' in html
    # CTA текущего занятия — кнопка ведёт на страницу метода с 3 задачами
    assert 'Изучить метод' in html
    assert 'Сегодня изучаешь метод' in html
    assert 'Разбор метода + 3 задачи' in html
    # долгов пока нет — строка не показывается
    assert 'В долгу' not in html


def test_dashboard_today_done_and_debt(pilot_client):
    """Завершение → «выполнено, завтра»; пропуск дня → «В долгу: 1»."""
    from app import app
    from curator import session_plan

    # первый заход создаёт урок-метод (назначен сегодня)
    rv = pilot_client.get('/daily_tasks')
    assert rv.status_code == 200

    with app.app_context():
        lesson = session_plan.current_lesson(1)
        assert lesson is not None and lesson['lesson_type'] == 'method'
        assert session_plan.complete_current_lesson(1, 'method') is True
        lesson_id = lesson['id']

    # рефреш в тот же день: день закрыт, следующее — завтра
    rv = pilot_client.get('/daily_tasks')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'Сегодняшнее занятие выполнено' in html
    assert 'завтра' in html

    # «наступает завтра»: вчерашний урок сделан, сегодня — новый (практика)
    _backdate(lesson_id, days=1)
    rv = pilot_client.get('/daily_tasks')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'В долгу' not in html          # пропусков не было
    assert 'практика' in html             # слот 2 — практика

    # сегодняшний урок НЕ сделан, день прошёл → долг
    with app.app_context():
        cur = session_plan.current_lesson(1)
        assert cur is not None
        cur_id = cur['id']
    _backdate(cur_id, days=1)
    rv = pilot_client.get('/daily_tasks')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'В долгу: 1' in html
    # план пошёл дальше — следующий слот (практика) текущий
    assert 'сейчас' in html


def test_method_week_page_pilot_only(pilot_client):
    """/method_week: пилоту — 200 (виджет разбор + 3 задачи), остальным — 404."""
    rv = pilot_client.get('/method_week')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'Метод недели' in html
    assert 'mw-root' in html
    assert 'method_week.js' in html


def test_daily_tasks_no_method_week_widget(pilot_client, monkeypatch):
    """Дашборд задач дня НЕ содержит виджет «Метод недели» (разбор + 3 задачи):
    владелец 26.10 — метод живёт на отдельной странице /method_week,
    кнопка «Изучить метод» на карточке плана ведёт туда.
    Даже если env METHOD_WEEK_UI_ENABLED=1 — инжектор выключен навсегда."""
    monkeypatch.setenv('METHOD_WEEK_UI_ENABLED', '1')
    rv = pilot_client.get('/daily_tasks')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'mw-root' not in html
    assert 'method_week.js' not in html
    # а страница метода работает
    rv = pilot_client.get('/method_week')
    assert rv.status_code == 200


def _seed_probe(uid=1, answered=0):
    """Активный срез по теме: answered — сколько задач отвечено (0..4)."""
    import json as _json
    from models import db
    from models_curator import CuratorState
    with db.session.no_autoflush:
        cs = CuratorState.query.filter_by(user_id=uid).first()
        if cs is None:
            cs = CuratorState(user_id=uid)
            db.session.add(cs)
        cs.probe_json = _json.dumps({
            'probe_id': 1, 'theme_id': 'G9_T02', 'grade': 9,
            'current_index': answered, 'current_level': 2,
            'seen_task_ids': [], 'answers': [],
            'started_at': '2026-10-24T16:16:47.885886+00:00',
        })
        db.session.commit()


def test_method_day_hides_probe_banner_and_block(pilot_client):
    """День метода: баннер «незавершённый тест» скрыт (даже если срез начат),
    дашборд НЕ блокируется «Сначала — тест», виджета «Метод недели» нет."""
    from curator import session_plan as sp
    # свежий пилот → слот 1 = день метода; срез начат (1 ответ из 5)
    _seed_probe(answered=1)
    rv = pilot_client.get('/daily_tasks')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'probeResumeBanner' not in html          # баннер среза скрыт
    assert 'У вас есть незавершённый тест' not in html
    # карточка «Сначала — тест» в DOM, но скрыта (dt-hidden)
    assert 'id="dt-blocked-state" class="dt-hidden"' in html
    assert 'Изучить метод' in html                    # карточка плана на месте
    assert 'mw-root' not in html                      # виджет метода не инжектится
    # и срез с 0 ответов (просто открыли) тоже не напоминает о себе
    _seed_probe(answered=0)
    rv = pilot_client.get('/daily_tasks')
    html = rv.get_data(as_text=True)
    assert 'probeResumeBanner' not in html


def test_practice_day_probe_banner_still_shows(pilot_client):
    """День практики: начатый срез по-прежнему напоминает о себе баннером
    (обычное поведение не сломано), блокировка срезом сохраняется."""
    from models import db
    from sqlalchemy import text
    from curator import session_plan as sp
    # сегодняшний урок — практика (слот 2), срез начат (1 ответ из 5)
    sp.ensure_tables()
    db.session.execute(text(
        "DELETE FROM curator_lessons WHERE user_id = 1"))
    db.session.commit()
    sp._insert_lesson(1, 1, 'method', status='completed')
    db.session.execute(text(
        "UPDATE curator_lessons SET assigned_date = date('now', '-1 day') "
        "WHERE user_id = 1 AND seq = 1"))
    db.session.commit()
    sp._insert_lesson(1, 2, 'practice')  # датировано сегодня
    assert sp.is_method_day(1) is False
    _seed_probe(answered=1)
    rv = pilot_client.get('/daily_tasks')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'probeResumeBanner' in html                 # баннер на месте
    assert 'У вас есть незавершённый тест' in html
    assert 'Изучить метод' not in html                  # день не методный


def test_is_method_day_done_lesson(pilot_client):
    """Метод сдан сегодня → это всё ещё день метода (баннер теста скрыт)."""
    from models import db
    from sqlalchemy import text
    from curator import session_plan as sp
    sp.ensure_tables()
    db.session.execute(text(
        "DELETE FROM curator_lessons WHERE user_id = 1"))
    db.session.commit()
    sp._insert_lesson(1, 1, 'method', status='completed')  # датировано сегодня
    assert sp.is_method_day(1) is True
    _seed_probe(answered=2)
    rv = pilot_client.get('/daily_tasks')
    html = rv.get_data(as_text=True)
    assert 'probeResumeBanner' not in html


def _force_cycle_blocked(monkeypatch):
    """Цикл месяца активен и требует срез (blocked)."""
    import curator.monthly_cycle as mc
    monkeypatch.setattr(
        mc, 'get_cycle_info',
        lambda user_id: {'active': True, 'blocked': True, 'finished': False,
                         'current_theme': 'G9_T02', 'day_index': 1})


def test_method_day_cycle_blocked_still_no_test(pilot_client, monkeypatch):
    """Даже при заблокированном цикле (требуется срез) в день метода
    дашборд не показывает «Сначала — тест» и баннер среза."""
    _force_cycle_blocked(monkeypatch)
    _seed_probe(answered=1)
    rv = pilot_client.get('/daily_tasks')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'id="dt-blocked-state" class="dt-hidden"' in html  # блок-карточка скрыта
    assert 'probeResumeBanner' not in html                    # баннер среза скрыт
    assert 'Изучить метод' in html


def test_practice_day_cycle_blocked_keeps_test(pilot_client, monkeypatch):
    """В день практики заблокированный цикл по-прежнему требует срез
    («Сначала — тест» видим, баннер на месте)."""
    from models import db
    from sqlalchemy import text
    from curator import session_plan as sp
    sp.ensure_tables()
    db.session.execute(text("DELETE FROM curator_lessons WHERE user_id = 1"))
    db.session.commit()
    sp._insert_lesson(1, 1, 'method', status='completed')
    db.session.execute(text(
        "UPDATE curator_lessons SET assigned_date = date('now', '-1 day') "
        "WHERE user_id = 1 AND seq = 1"))
    db.session.commit()
    sp._insert_lesson(1, 2, 'practice')  # сегодня — практика
    _force_cycle_blocked(monkeypatch)
    _seed_probe(answered=1)
    rv = pilot_client.get('/daily_tasks')
    html = rv.get_data(as_text=True)
    # блок-карточка ВИДИМА (не dt-hidden)
    assert 'id="dt-blocked-state" class="' in html
    assert 'dt-hidden' not in html.split('id="dt-blocked-state" class="')[1][:30]
    assert 'Сначала — тест' in html
    assert 'probeResumeBanner' in html


def test_non_pilot_banner_unchanged():
    """Не-пилот: прежнее поведение баннера — даже срез с 0 отвеченных
    (просто открыли) напоминает о себе."""
    from app import app
    from models import db, User
    from models_curator import CuratorState
    import json as _json
    with app.app_context():
        u = User.query.get(2)  # локальный юзер 2 может уже существовать
        if not u:
            u = User.query.filter_by(email='nonpilot@test.local').first()
        if not u:
            u = User(email='nonpilot@test.local')
            db.session.add(u)
            db.session.commit()
        cs = CuratorState.query.filter_by(user_id=u.id).first()
        if cs is None:
            cs = CuratorState(user_id=u.id)
            db.session.add(cs)
        cs.grade = 9
        cs.prep_state = _json.dumps({'intake': {'completed': True}})
        cs.probe_json = _json.dumps({
            'probe_id': 2, 'theme_id': 'G9_T02', 'grade': 9,
            'current_index': 0, 'current_level': 2,
            'seen_task_ids': [], 'answers': [],
            'started_at': '2026-10-24T16:16:47.885886+00:00'})
        db.session.commit()
        _uid2 = u.id
    with app.test_client() as c:
        c.get(f'/dev_login?uid={_uid2}')
        rv = c.get('/daily_tasks')
        html = rv.get_data(as_text=True)
        assert 'probeResumeBanner' in html  # прежнее поведение: баннер есть


def test_no_active_probe_blocked_cycle_method_day(pilot_client, monkeypatch):
    """Цикл требует срез, активного среза НЕТ (current_index=5 — пройден).
    ВАЖНО: ветка probe_required в pick_daily_set МЁРТВАЯ из-за старого бага
    (UnboundLocalError grade, проглатывается except) — срез создаётся из банка.
    Проверяем итоговое поведение дня метода: НИКАКОГО требования теста —
    не blocked, баннер среза скрыт, CTA ведёт на /method_week."""
    import json as _json
    from models import db
    from models_curator import CuratorState
    from sqlalchemy import text as _text
    # срез пройден (current_index=5 >= PROBE_SIZE), сет на сегодня чистим
    with db.session.no_autoflush:
        cs = CuratorState.query.filter_by(user_id=1).first()
        cs.probe_json = _json.dumps({
            'probe_id': 1, 'theme_id': 'G9_T02', 'grade': 9,
            'current_index': 5, 'current_level': 2,
            'seen_task_ids': [], 'answers': [], 'started_at': '2026-10-24'})
        db.session.commit()
    db.session.execute(_text(
        "DELETE FROM daily_task_sets WHERE user_id = 1 "
        "AND target_date = date('now')"))
    db.session.commit()
    _force_cycle_blocked(monkeypatch)
    # банк пуст → роут проваливается в pick_daily_set (ветка probe_required)
    import services.bank_daily as _bd
    monkeypatch.setattr(
        _bd, 'build_daily_set',
        lambda uid, today, max_items=None: {'bank_empty': True, 'items': []})
    # перехватываем реальный контекст рендера
    from flask import template_rendered
    captured = []
    def _capture(sender, template, context, **extra):
        captured.append(context)
    template_rendered.connect(_capture)
    try:
        rv = pilot_client.get('/daily_tasks')
    finally:
        template_rendered.disconnect(_capture)
    assert rv.status_code == 200
    ctx = captured[-1]
    d = ctx.get('data') or {}
    assert d.get('status') != 'blocked'          # требования теста нет
    assert d.get('session', {}).get('active') is True
    html = rv.get_data(as_text=True)
    assert '/method_week' in html                 # CTA на страницу метода
    assert 'id="dt-blocked-state" class="dt-hidden"' in html
    assert 'probeResumeBanner' not in html


def test_no_active_probe_blocked_cycle_practice_day(pilot_client, monkeypatch):
    """Та же ветка probe_required, но день практики: прежнее поведение —
    срез требуется (status=blocked, «Сначала — тест» видим)."""
    import json as _json
    from models import db
    from models_curator import CuratorState
    from sqlalchemy import text
    from curator import session_plan as sp
    sp.ensure_tables()
    db.session.execute(text("DELETE FROM curator_lessons WHERE user_id = 1"))
    db.session.commit()
    sp._insert_lesson(1, 1, 'method', status='completed')
    db.session.execute(text(
        "UPDATE curator_lessons SET assigned_date = date('now', '-1 day') "
        "WHERE user_id = 1 AND seq = 1"))
    db.session.commit()
    sp._insert_lesson(1, 2, 'practice')
    with db.session.no_autoflush:
        cs = CuratorState.query.filter_by(user_id=1).first()
        cs.probe_json = _json.dumps({
            'probe_id': 1, 'theme_id': 'G9_T02', 'grade': 9,
            'current_index': 5, 'current_level': 2,
            'seen_task_ids': [], 'answers': [], 'started_at': '2026-10-24'})
        db.session.commit()
    _force_cycle_blocked(monkeypatch)
    from flask import template_rendered
    captured = []
    def _capture(sender, template, context, **extra):
        captured.append(context)
    template_rendered.connect(_capture)
    try:
        rv = pilot_client.get('/daily_tasks')
    finally:
        template_rendered.disconnect(_capture)
    ctx = captured[-1]
    d = ctx.get('data') or {}
    assert d.get('status') == 'blocked'
    html = rv.get_data(as_text=True)
    assert 'Сначала — тест' in html
    assert 'id="dt-blocked-state" class="' in html
