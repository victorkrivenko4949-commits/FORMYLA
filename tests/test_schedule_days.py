# -*- coding: utf-8 -*-
"""PILOT_SCHEDULE_DAYS_V1 — выбор дней занятий после покупки пилотного тарифа.

Проверяем:
  * хранение и валидацию (ровно 6 / ровно 3 дня, без дублей, 0..6);
  * days_for_plan: устаревший выбор под другой тариф → None;
  * страницу /schedule: без тарифа и с уже выбранными днями — редирект;
  * API /schedule/save: валидация количества;
  * гейт force_schedule_selection: без выбора — редирект на /schedule,
    после выбора — пропускает;
  * pilot_session_today: расписание по ВЫБРАННЫМ дням.
"""
from datetime import datetime, timedelta

import pytest


# ── helpers ─────────────────────────────────────────────────────────────

def _make_user(uid, nickname=None):
    from models import User
    u = User(id=uid, email=f'sched{uid}@test.invalid',
             nickname=nickname or f'sched{uid}',
             is_guest=False, role='student')
    from models import db
    db.session.add(u)
    return u


def _make_sub(uid, plan, started_days_ago=0):
    from models import Subscription, db
    s = Subscription(
        user_id=uid, plan=plan, status='active',
        started_at=datetime.utcnow() - timedelta(days=started_days_ago),
        expires_at=datetime.utcnow() + timedelta(days=30),
        is_beta_access=False, is_trial=False)
    db.session.add(s)
    return s


# ── 1. Хранение и валидация ───────────────────────────────────────────

def test_save_and_get_roundtrip(app):
    from services import schedule_days as sd

    assert sd.save_user_days(101, [0, 2, 4], 'premium_calm') is True
    assert sd.get_user_days(101) == [0, 2, 4]

    assert sd.save_user_days(102, [6, 1, 3, 0, 5, 2], 'premium_intense') is True
    assert sd.get_user_days(102) == [0, 1, 2, 3, 5, 6]  # сортировка


def test_validation_wrong_count(app):
    from services import schedule_days as sd

    # «Спокойный» — ровно 3
    assert sd.save_user_days(103, [0, 1], 'premium_calm') is False
    assert sd.save_user_days(103, [0, 1, 2, 3], 'premium_calm') is False
    # «Работяга» — ровно 6
    assert sd.save_user_days(103, [0, 1, 2, 3, 4], 'premium_intense') is False
    assert sd.save_user_days(103, [0, 1, 2, 3, 4, 5, 6], 'premium_intense') is False
    assert sd.get_user_days(103) is None  # ничего не сохранилось


def test_validation_bad_input(app):
    from services import schedule_days as sd

    assert sd.save_user_days(104, [0, 0, 1], 'premium_calm') is False   # дубль
    assert sd.save_user_days(104, [0, 7, 2], 'premium_calm') is False  # вне 0..6
    assert sd.save_user_days(104, 'Пн,Ср,Пт', 'premium_calm') is False  # не список
    assert sd.save_user_days(104, [], 'premium_calm') is False         # пусто
    # Не-пилотный тариф — сохранять дни нельзя
    assert sd.save_user_days(104, [0, 2, 4], 'premium_monthly') is False


def test_days_for_plan_stale_choice(app):
    from services import schedule_days as sd

    sd.save_user_days(105, [0, 2, 4], 'premium_calm')
    # Был «Спокойный» (3 дня), стал «Работяга» — нужно выбрать заново
    assert sd.days_for_plan(105, 'premium_intense') is None
    assert sd.days_for_plan(105, 'premium_calm') == [0, 2, 4]
    # Не-пилотный тариф — всегда None
    assert sd.days_for_plan(105, 'premium_monthly') is None


# ── 2. Страница /schedule и API ───────────────────────────────────────

def test_schedule_page_requires_pilot_plan(app, test_user):
    from routes.schedule_days import schedule_days_bp
    try:
        app.register_blueprint(schedule_days_bp)
    except Exception:
        pass  # уже зарегистрирован

    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['_user_id'] = str(test_user.id)
        # Нет пилотного тарифа — на /schedule делать нечего
        rv = c.get('/schedule')
        assert rv.status_code == 302
        assert '/daily_tasks' in rv.headers['Location']


def test_schedule_page_flow(app, test_user):
    from models import db
    from routes.schedule_days import schedule_days_bp
    try:
        app.register_blueprint(schedule_days_bp)
    except Exception:
        pass

    _make_sub(test_user.id, 'premium_intense')
    db.session.commit()

    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['_user_id'] = str(test_user.id)

        # Пилотный тариф есть, дни не выбраны — страница выбора
        rv = c.get('/schedule')
        assert rv.status_code == 200
        body = rv.get_data(as_text=True)
        assert 'Выберите дни занятий' in body
        assert '6' in body

        # POST: мало дней — отказ
        rv = c.post('/schedule/save',
                    json={'days': [0, 1, 2]})
        assert rv.status_code == 400

        # POST: ровно 6 — успех
        rv = c.post('/schedule/save',
                    json={'days': [0, 1, 3, 4, 5, 6]})
        assert rv.status_code == 200
        import json as _json
        assert _json.loads(rv.get_data(as_text=True))['ok'] is True

        # Дни выбраны — /schedule больше не показывает выбор
        rv = c.get('/schedule')
        assert rv.status_code == 302
        assert '/daily_tasks' in rv.headers['Location']


# ── 3. Гейт: без выбора не выпускаем ──────────────────────────────────

def test_gate_blocks_until_selection(app, test_user):
    import app as real_app_module
    from models import db
    from flask_login import login_user, logout_user

    _make_sub(test_user.id, 'premium_calm', started_days_ago=8)
    db.session.commit()

    with app.test_request_context('/daily_tasks'):
        login_user(test_user)
        rv = real_app_module.force_schedule_selection()
        assert rv is not None
        assert '/schedule' in rv.location

        # Выбираем дни — гейт открыт
        from services import schedule_days as sd
        sd.save_user_days(test_user.id, [1, 3, 5], 'premium_calm')
        rv = real_app_module.force_schedule_selection()
        assert rv is None
        logout_user()


def test_gate_ignores_non_pilot(app, test_user):
    import app as real_app_module
    from models import db
    from flask_login import login_user, logout_user

    # premium_monthly — не пилотный тариф, гейт не про него
    _make_sub(test_user.id, 'premium_monthly', started_days_ago=8)
    db.session.commit()

    with app.test_request_context('/daily_tasks'):
        login_user(test_user)
        rv = real_app_module.force_schedule_selection()
        assert rv is None
        logout_user()


def test_gate_skips_teacher_parent_and_lavrik(app):
    import app as real_app_module
    from models import db
    from flask_login import login_user, logout_user

    for uid, role, nick in ((210, 'teacher', 't210'),
                            (211, 'parent', 'p211'),
                            (212, 'student', 'lavrik')):
        _make_user(uid, nickname=nick)
        db.session.commit()
        from models import User
        db.session.query(User).filter_by(id=uid).update({'role': role})
        _make_sub(uid, 'premium_intense', started_days_ago=8)
        db.session.commit()

        with app.test_request_context('/daily_tasks'):
            from models import User
            u = db.session.get(User, uid)
            login_user(u)
            rv = real_app_module.force_schedule_selection()
            assert rv is None, f'{role}/{nick} не должен попадать под гейт'
            logout_user()


def test_gate_allows_own_paths(app, test_user):
    import app as real_app_module
    from models import db
    from flask_login import login_user, logout_user

    _make_sub(test_user.id, 'premium_intense', started_days_ago=8)
    db.session.commit()

    with app.test_request_context('/payments/premium/return?order_id=1'):
        login_user(test_user)
        rv = real_app_module.force_schedule_selection()
        assert rv is None, 'платёжный контур должен быть доступен'
        logout_user()


# ── 4. pilot_session_today по выбранным дням ───────────────────────────

def test_pilot_session_uses_chosen_days(app):
    from datetime import date
    from services import schedule_days as sd
    from services.pilot import pilot_session_today

    today_wd = date.today().weekday()

    # «Работяга» выбрал 6 дней, исключив сегодняшний (если возможно)
    all_days = [d for d in range(7) if d != today_wd][:6]
    if len(all_days) == 6:
        _make_user(220)
        _make_sub(220, 'premium_intense', started_days_ago=8)  # 2-я неделя
        from models import db
        db.session.commit()
        sd.save_user_days(220, all_days, 'premium_intense')

        s = pilot_session_today(220)
        assert s['enabled'] is True
        assert s['plan'] == 'premium_intense'
        assert s['total'] == 6
        # Сегодня НЕ в выбранных днях — отдых
        assert s['session_type'] == 'rest'
        assert s['session_index'] is None

    # «Спокойный» выбрал 3 дня, включая сегодняшний
    calm_days = [today_wd] + [d for d in range(7) if d != today_wd][:2]
    _make_user(221)
    _make_sub(221, 'premium_calm', started_days_ago=8)
    from models import db
    db.session.commit()
    sd.save_user_days(221, calm_days, 'premium_calm')

    s = pilot_session_today(221)
    assert s['enabled'] is True
    assert s['total'] == 3
    # Позиция считается по ОТСОРТИРОВАННЫМ дням (сервис сортирует)
    expected_pos = sorted(calm_days).index(today_wd) + 1
    assert s['session_index'] == expected_pos
    assert s['session_type'] in ('tasks', 'method')


def test_pilot_session_week1_diagnostic_only_chosen_days(app):
    from datetime import date
    from services import schedule_days as sd
    from services.pilot import pilot_session_today

    today_wd = date.today().weekday()
    calm_days = [d for d in range(7) if d != today_wd][:3]

    _make_user(222)
    _make_sub(222, 'premium_calm', started_days_ago=0)  # первая неделя
    from models import db
    db.session.commit()
    sd.save_user_days(222, calm_days, 'premium_calm')

    s = pilot_session_today(222)
    assert s['enabled'] is True
    assert s['week'] == 1
    # Сегодняшний день не выбран — даже в диагностическую неделю отдых
    assert s['session_type'] == 'rest'
    assert s['session_index'] is None


def test_pilot_session_calm_method_positions(app):
    """Метод — 2-й выбранный день нечётных недель; пробника в ротации нет (#176)."""
    from datetime import date
    from services import schedule_days as sd
    from services.pilot import pilot_session_today

    today_wd = date.today().weekday()
    # Дни: today в списке выбранных
    others = [d for d in range(7) if d != today_wd][:2]
    days = others + [today_wd]

    _make_user(223)
    _make_sub(223, 'premium_calm', started_days_ago=8)
    from models import db
    db.session.commit()
    sd.save_user_days(223, days, 'premium_calm')

    s = pilot_session_today(223)
    expected_pos = sorted(days).index(today_wd) + 1
    assert s['session_index'] == expected_pos
    # Тип занятия зависит от позиции в отсортированном списке и чётности недели;
    # пробник из ротации убран (#176) — только задачи, метод и отдых
    if expected_pos == 2:
        assert s['session_type'] == ('method' if s['week'] % 2 == 1 else 'tasks')
    else:
        assert s['session_type'] == 'tasks'
    assert s['session_type'] != 'mock'
