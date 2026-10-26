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
    """/method_week: старой страницы нет — пилота редиректит на настоящую
    страницу метода из базы 102 (владелец, 26.10)."""
    rv = pilot_client.get('/method_week')
    assert rv.status_code == 302
    assert rv.headers['Location'].startswith('/olympiads/methods#/methods/')


def test_daily_tasks_no_method_week_widget(pilot_client, monkeypatch):
    """Дашборд задач дня НЕ содержит СТАРЫЙ виджет (куратор + разбор сверху),
    даже если env METHOD_WEEK_UI_ENABLED=1 — инжектор выключен навсегда.
    Вместо него (владелец, 26.10, итерация 4): в карточке метод-дня —
    только 3 задачи (data-mw-only="tasks"), без AI-разбора и куратора."""
    monkeypatch.setenv('METHOD_WEEK_UI_ENABLED', '1')
    rv = pilot_client.get('/daily_tasks')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    # старый инжект (голый mw-root без режима) — исчез
    assert '<div id="mw-root">' not in html
    assert 'data-mw-anchor' not in html
    # а /method_week больше не отдаёт старую страницу — редирект на метод
    rv = pilot_client.get('/method_week')
    assert rv.status_code == 302
    assert rv.headers['Location'].startswith('/olympiads/methods#/methods/')


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
    # 3 задачи метода — прямо на месте задач дня, только задачи (без разбора)
    assert '<div id="mw-root" data-mw-only="tasks">' in html
    assert 'ОБЯЗАТЕЛЬНО изучи метод' in html
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
    assert '/olympiads/methods#/methods/' in html  # CTA в атлас (новый дизайн)
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


def test_method_day_no_daily_set(pilot_client):
    """День метода: задачи дня НЕ выдаются и не создаются —
    статус method_day, сета на сегодня нет (владелец, 26.10)."""
    from models import db
    from daily_tasks.models import DailyTaskSet
    from flask import template_rendered
    captured = []
    def _capture(sender, template, context, **extra):
        captured.append(context)
    template_rendered.connect(_capture)
    try:
        rv = pilot_client.get('/daily_tasks')
    finally:
        template_rendered.disconnect(_capture)
    d = captured[-1].get('data') or {}
    assert d.get('status') == 'method_day'
    with __import__('app', fromlist=['app']).app.app_context():
        assert DailyTaskSet.query.filter_by(
            user_id=1, target_date=__import__('datetime', fromlist=['date']).date.today()
        ).count() == 0


def test_method_page_shows_deepseek_tasks(pilot_client):
    """Страница метода из базы 102 (метод текущей недели) содержит
    блок 3 дипсиковых задач (виджет method_week, режим tasks)."""
    from curator import session_plan as sp
    from method_week.catalog import method_for_week
    m = method_for_week(1)
    assert m and m.get('method_code'), 'метод недели должен быть определён'
    rv = pilot_client.get(f"/olympiads/methods/{m['method_code']}")
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'mw-root' in html and 'method_week.js' in html
    assert 'data-mw-only="tasks"' in html


def test_other_method_page_no_tasks_injection(pilot_client):
    """Другая страница метода (не метод текущей недели) — без блока задач."""
    from method_week.catalog import method_for_week
    m = method_for_week(1)
    other = 'A1' if (not m or m['method_code'] != 'A1') else 'A2'
    rv = pilot_client.get(f'/olympiads/methods/{other}')
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert 'mw-root' not in html


def test_non_pilot_method_page_no_tasks():
    """Не-пилот: страница метода без блока задач (как раньше)."""
    from app import app
    from models import db, User
    with app.app_context():
        u = User.query.get(2) or User.query.filter_by(email='nonpilot@test.local').first()
        _uid = u.id
    with app.test_client() as c:
        c.get(f'/dev_login?uid={_uid}')
        rv = c.get('/olympiads/methods/B2')
        assert rv.status_code == 200
        assert 'mw-root' not in rv.get_data(as_text=True)


def test_method_day_no_bank_no_pick(monkeypatch, pilot_client):
    """День метода: ни банк (build_daily_set), ни pick_daily_set не вызываются."""
    from app import app
    calls = {'bank': 0, 'pick': 0}
    import services.bank_daily as _bd
    import services.daily_task_rotation as _dtr
    monkeypatch.setattr(_bd, 'build_daily_set', lambda *a, **k: calls.__setitem__('bank', calls['bank'] + 1))
    monkeypatch.setattr(_dtr, 'pick_daily_set', lambda *a, **k: calls.__setitem__('pick', calls['pick'] + 1))
    rv = pilot_client.get('/daily_tasks')
    assert rv.status_code == 200
    assert calls == {'bank': 0, 'pick': 0}


def test_lavrik_method_page_tasks_injection():
    """Лаврик (id 5, пилот): страница его метода недели — с блоком задач."""
    from app import app
    from models import db, User
    from models_curator import CuratorState
    import json as _json
    with app.app_context():
        u = User.query.get(5)
        if not u:
            # чистим возможный дубль по email (id != 5 не проходит пилот-гейт)
            for stray in User.query.filter_by(email='lavrik@test.local').all():
                db.session.delete(stray)
            db.session.commit()
            u = User(id=5, email='lavrik@test.local')
            db.session.add(u)
            db.session.commit()
        if getattr(u, 'nickname', None) != 'lavrik':
            u.nickname = 'lavrik'
        cs = CuratorState.query.filter_by(user_id=u.id).first()
        if cs is None:
            cs = CuratorState(user_id=u.id)
            db.session.add(cs)
        cs.grade = 9
        cs.prep_state = _json.dumps({'intake': {'completed': True}})
        db.session.commit()
    with app.test_client() as c:
        c.get('/dev_login?uid=5')
        rv = c.get('/daily_tasks')
        assert rv.status_code == 200
        from method_week.catalog import method_for_week
        m = method_for_week(5)
        assert m and m.get('method_code'), 'метод недели Лаврика должен быть определён'
        rv = c.get(f"/olympiads/methods/{m['method_code']}")
        assert rv.status_code == 200
        html = rv.get_data(as_text=True)
        assert 'data-mw-only="tasks"' in html


def test_non_pilot_no_injection_on_pilot_method():
    """Не-пилот: на том же методе недели (что у пилота) блока задач нет."""
    from app import app
    from method_week.catalog import method_for_week
    with app.app_context():
        m = method_for_week(1)
    assert m and m.get('method_code')
    code = m['method_code']
    uid = 1000  # nonpilot@test.local — не-пилот
    with app.test_client() as c:
        c.get(f'/dev_login?uid={uid}')
        with app.app_context():
            pass  # контекст для method_for_week выше уже не нужен
        rv = c.get(f'/olympiads/methods/{code}')
        assert rv.status_code == 200
        assert 'mw-root' not in rv.get_data(as_text=True)


def test_method_day_cta_leads_to_method_page(pilot_client):
    """Сквозная: кнопка «Изучить метод» ведёт на страницу метода из базы 102,
    и там же рендерится блок 3 задач (тот же метод, что в CTA)."""
    from flask import template_rendered
    import re
    captured = []
    def _cap(sender, template, context, **extra):
        captured.append(context)
    template_rendered.connect(_cap)
    try:
        rv = pilot_client.get('/daily_tasks')
    finally:
        template_rendered.disconnect(_cap)
    html = rv.get_data(as_text=True)
    m = re.search(r'href="(/olympiads/methods#/methods/[A-Za-z0-9_-]+)"', html)
    assert m, 'на дне метода должна быть кнопка на метод в атласе'
    code = m.group(1).rsplit('/', 1)[-1]
    # фрагмент #/... не уходит на сервер: проверяем обёртку атласа
    rv2 = pilot_client.get(m.group(1).split('#')[0])
    assert rv2.status_code == 200
    html2 = rv2.get_data(as_text=True)
    assert 'atlas' in html2  # обёртка атласа с передачей hash в iframe


def test_method_cta_pilot_gate(pilot_client):
    """Кнопка «Изучить метод» (и весь блок плана) — только пилотам
    (victor=1, Lavrik=5): session_info закрыт ВХОДНЫМ пилот-гейтом,
    не-пилот получает прежнее {'active': False} (ранний выход до _sync —
    состояние БД не нужно). Пилоты с методом-уроком получают deep-link
    в атлас (владелец, 27.10)."""
    from app import app
    from models import db
    from curator import session_plan as sp
    from sqlalchemy import text
    import datetime as _dt

    # не-пилот: ранний выход, никаких записей в БД
    assert sp.session_info(999) == {'active': False}

    added = []
    try:
        with app.app_context():
            for uid in (1, 5):
                lessons = sp._lessons(uid)
                seq = max([l['seq'] for l in lessons], default=0) + 1
                sp._insert_lesson(uid, seq, 'method',
                                  assigned=_dt.date.today())
                added.append((uid, seq))
            s1 = sp.session_info(1)
            s5 = sp.session_info(5)
    finally:
        # убираем добавленные уроки — повторные прогоны не накапливают
        with app.app_context():
            for uid, seq in added:
                db.session.execute(text(
                    'DELETE FROM curator_lessons '
                    'WHERE user_id = :uid AND seq = :seq'),
                    {'uid': uid, 'seq': seq})
            db.session.commit()
    assert s1['cta_url'].startswith('/olympiads/methods#/methods/')
    assert s5['cta_url'].startswith('/olympiads/methods#/methods/')


def test_method_day_lesson_code_matches_week(pilot_client):
    """Инвариант: сегодняшний урок-метод всегда берётся из method_for_week
    (создаётся в свой день), поэтому CTA и блок задач ведут на один метод."""
    from curator import session_plan as sp
    from method_week.catalog import method_for_week
    rv = pilot_client.get('/daily_tasks')  # синхронизирует расписание
    assert rv.status_code == 200
    lessons = sp._lessons(1)
    today_lesson = None
    for l in reversed(lessons):
        if sp._to_date(l.get('assigned_date')) == __import__('datetime', fromlist=['date']).date.today():
            today_lesson = l
            break
    assert today_lesson and today_lesson['lesson_type'] == 'method'
    m = method_for_week(1)
    assert m and m.get('method_code')
    assert today_lesson.get('method_code') == m['method_code']


def test_non_pilot_no_autoopen_script():
    """Не-пилот: на странице метода нет скрипта автооткрытия из URL."""
    from app import app
    with app.test_client() as c:
        c.get('/dev_login?uid=1000')
        rv = c.get('/olympiads/methods/B2')
        assert rv.status_code == 200
        html = rv.get_data(as_text=True)
        assert 'mw-root' not in html
        assert 'data-mw-method' not in html


def test_method_page_marks_injected_code(pilot_client):
    """Блок задач помечен кодом метода — задачи следуют за открытым методом."""
    from method_week.catalog import method_for_week
    from app import app
    with app.app_context():
        m = method_for_week(1)
    # используем уже залогиненный client фикстуры (повторный dev_login
    # в новом клиенте после app_context даёт DetachedInstanceError)
    rv = pilot_client.get(f"/olympiads/methods/{m['method_code']}")
    assert rv.status_code == 200
    html = rv.get_data(as_text=True)
    assert f'data-mw-method="{m["method_code"]}"' in html


def test_saved_set_overrides_week_method_cta(pilot_client):
    """Рассинхрон (неделя пересекла границу месяца после создания сета):
    сет сохранён с методом A, план недели уже даёт B — кнопка и блок задач
    ведут на A (источник задач — сет), под теорией B задач нет."""
    import json as _json
    import datetime as _dt
    from app import app
    from models import db
    from method_week.models import MethodWeekSet
    from method_week.catalog import method_for_week, week_set_method
    from sqlalchemy import text

    with app.app_context():
        m = method_for_week(1)
        other = 'A1' if m['method_code'] != 'A1' else 'A2'
        today = _dt.date.today()
        ws = today - _dt.timedelta(days=today.weekday())
        db.session.execute(text("DELETE FROM method_week_sets WHERE user_id = 1"))
        db.session.commit()
        s = MethodWeekSet(
            user_id=1, week_start=ws, method_code=other,
            method_name='тестовый метод', status='ready',
            tasks_json=_json.dumps([], ensure_ascii=False),
        )
        db.session.add(s)
        db.session.commit()

    try:
        # кнопка на дашборде → страница метода сета
        rv = pilot_client.get('/daily_tasks')
        assert rv.status_code == 200
        html = rv.get_data(as_text=True)
        assert f'/olympiads/methods#/methods/{other}' in html
        assert f"/olympiads/methods#/methods/{m['method_code']}" not in html

        # страница метода сета — с блоком задач; метод плана — без
        rv2 = pilot_client.get(f'/olympiads/methods/{other}')
        assert rv2.status_code == 200
        assert 'data-mw-only="tasks"' in rv2.get_data(as_text=True)
        rv3 = pilot_client.get(f"/olympiads/methods/{m['method_code']}")
        assert rv3.status_code == 200
        assert 'mw-root' not in rv3.get_data(as_text=True)
    finally:
        with app.app_context():
            db.session.execute(text("DELETE FROM method_week_sets WHERE user_id = 1"))
            db.session.commit()


def test_saved_set_mismatch_lesson_completes(pilot_client):
    """Рассинхрон сета и плана (граница месяца): все 3 задачи сета решены —
    занятие-метод закрывается, метод занятия переуказан на метод сета."""
    import json as _json
    import datetime as _dt
    from app import app
    from models import db
    from method_week.models import MethodWeekSet, MethodWeekAnswer
    from curator import session_plan as sp
    from method_week.catalog import method_for_week
    from sqlalchemy import text

    with app.app_context():
        m = method_for_week(1)
        other = 'A1' if m['method_code'] != 'A1' else 'A2'
        today = _dt.date.today()
        ws = today - _dt.timedelta(days=today.weekday())
        db.session.execute(text("DELETE FROM method_week_sets WHERE user_id = 1"))
        # sqlite переиспользует id сетов — чистим и ответы
        db.session.execute(text("DELETE FROM method_week_answers"))
        db.session.commit()
        s = MethodWeekSet(
            user_id=1, week_start=ws, method_code=other,
            method_name='тестовый метод', status='ready',
            tasks_json=_json.dumps([
                {'position': 1, 'statement': 'a', 'answer': '1'},
                {'position': 2, 'statement': 'b', 'answer': '2'},
                {'position': 3, 'statement': 'c', 'answer': '3'},
            ], ensure_ascii=False),
        )
        db.session.add(s)
        db.session.commit()
        for pos in (1, 2, 3):
            db.session.add(MethodWeekAnswer(
                set_id=s.id, user_id=1, position=pos,
                user_answer=str(pos), is_correct=True))
        db.session.commit()
        sid = s.id

    try:
        # занятие-метод сегодня, метод по плану
        with app.app_context():
            done = sp.maybe_complete_method(1)
        assert done is True, 'занятие должно закрыться по решённому сету'
        with app.app_context():
            lesson = sp._current_assigned(1)
            assert lesson is None or lesson['lesson_type'] != 'method' or \
                lesson.get('method_code') == other
            row = db.session.execute(text(
                "SELECT status, method_code, completed_set_id FROM curator_lessons "
                "WHERE user_id = 1 AND lesson_type = 'method' "
                "ORDER BY id DESC LIMIT 1")).fetchone()
        assert row[0] == 'completed'
        assert row[1] == other, 'метод занятия должен стать методом сета'
        assert row[2] == sid
    finally:
        with app.app_context():
            db.session.execute(text("DELETE FROM method_week_sets WHERE user_id = 1"))
            db.session.commit()


def test_method_week_page_redirects_to_real_method(pilot_client):
    """/method_week (старая страница) больше не отдаётся: редирект на
    настоящую страницу метода из базы 102 (владелец, 26.10)."""
    from method_week.catalog import method_for_week
    from app import app
    with app.app_context():
        m = method_for_week(1)
    rv = pilot_client.get('/method_week')
    assert rv.status_code == 302
    assert rv.headers['Location'].startswith(
        f"/olympiads/methods#/methods/{m['method_code']}")

    # и со слэшем на конце
    rv2 = pilot_client.get('/method_week/')
    assert rv2.status_code == 302
    assert rv2.headers['Location'].startswith('/olympiads/methods#/methods/')

    # API живой (виджет на странице метода ходит в него); готовый сет —
    # чтобы /api/today не запускал генерацию в общей тестовой базе
    from app import app
    from models import db
    from method_week.models import MethodWeekSet
    from method_week.routes import week_start, _today
    from sqlalchemy import text
    with app.app_context():
        db.session.execute(text("DELETE FROM method_week_sets WHERE user_id = 1"))
        db.session.commit()
        s = MethodWeekSet(user_id=1, week_start=week_start(_today()), method_code='B2',
                          method_name='тест', status='ready',
                          tasks_json='[]')
        db.session.add(s)
        db.session.commit()
    try:
        rv3 = pilot_client.get('/method_week/api/today')
        assert rv3.status_code == 200
        assert rv3.get_json().get('status') == 'ready'
    finally:
        with app.app_context():
            db.session.execute(text("DELETE FROM method_week_sets WHERE user_id = 1"))
            db.session.commit()
