# -*- coding: utf-8 -*-
"""Проверка сценария пробного бесплатного дня (24ч Premium).

Вопрос владельца (01.11.2026): «Пробный бесплатный день — там получается
тест и 5 задач дня?»

Ожидаемое поведение из кода:
  * trial-пользователь проходит guard теста (can_take_theme_test);
  * в первый день цикла тема ещё не протестирована (cycle.blocked):
    норма дня = 5 задач (тест 5 + задачи дня 5 = 10);
  * после прохождения теста в тот же день — те же 5 задач дня;
  * в день без теста — полная норма 10.
"""
from datetime import datetime, timedelta

from models import db


def _nonpilot_user():
    """Пользователь с непилотным id (id=1 в тестах — это пилот victor)."""
    from models import User
    user = User(id=9010, email='trial_flow@test.invalid',
                nickname='trial_flow', is_guest=False)
    db.session.add(user)
    db.session.commit()
    return user


def _make_trial(user):
    user.plan_expires_at = datetime.utcnow() + timedelta(hours=24)
    user.current_plan = 'premium'
    db.session.commit()


def test_trial_user_can_take_test(app):
    from services.pilot import can_take_theme_test
    test_user = _nonpilot_user()
    _make_trial(test_user)
    assert can_take_theme_test(test_user), (
        'активный пробный день должен открывать тест'
    )


def test_trial_day_count_is_test_plus_five(app):
    from curator.monthly_cycle import build_or_get_cycle, get_cycle_info
    from services.daily_task_rotation import get_daily_task_count
    test_user = _nonpilot_user()
    _make_trial(test_user)

    build_or_get_cycle(test_user.id, 9)
    cycle = get_cycle_info(test_user.id)
    assert cycle.get('active'), 'цикл месяца должен быть активным'

    # День теста: тема ещё не протестирована -> blocked
    assert cycle.get('blocked') or not cycle.get('current_theme')
    count = get_daily_task_count(test_user.id)
    assert count == 5, (
        f'в день теста должно быть 5 задач дня (тест 5 + 5), получено {count}'
    )


def test_day_without_test_gives_full_norm(app):
    from curator.monthly_cycle import build_or_get_cycle, _get_monthly_cycle
    from models_curator import CuratorState
    from services.daily_task_rotation import get_daily_task_count
    test_user = _nonpilot_user()
    _make_trial(test_user)

    build_or_get_cycle(test_user.id, 9)
    cs = CuratorState.query.filter_by(user_id=test_user.id).first()
    mc = _get_monthly_cycle(cs)
    # Эмулируем «тест пройден вчера»: тема протестирована, но не сегодня.
    from curator.monthly_cycle import _save_monthly_cycle
    mc['done_themes'] = list(mc.get('themes') or [])[:1]
    mc['last_probe_date'] = (
        datetime.utcnow() - timedelta(days=1)
    ).strftime('%Y-%m-%d')
    _save_monthly_cycle(cs, mc)
    db.session.commit()

    count = get_daily_task_count(test_user.id)
    assert count == 10, (
        f'в день без теста должна быть полная норма 10, получено {count}'
    )


def test_trial_activation_endpoint(app, test_user):
    """POST /api/subscribe/trial — активация и повторная защита."""
    import app as _app_module
    from flask import session as _flask_session

    def _call():
        with app.test_request_context(
                '/api/subscribe/trial', method='POST',
                json={'plan': 'premium_intense'}):
            _flask_session['_user_id'] = str(test_user.id)
            return _app_module.api_subscribe_trial()

    # SQLite (тесты) не знает NOW() из Postgres-кода эндпоинта — добавляем.
    from models import db as _db

    _conn = _db.engine.raw_connection()
    try:
        _conn.create_function(
            'NOW', 0, lambda: datetime.utcnow().isoformat(sep=' '))
    except Exception:
        pass
    finally:
        _conn.close()

    r = _app_module.app.make_response(_call())
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body.get('ok') is True

    from services.pilot import can_take_theme_test
    from models import db
    db.session.refresh(test_user)
    assert test_user.plan_expires_at is not None
    assert can_take_theme_test(test_user), 'после активации тест должен быть доступен'

    # Повторная активация — 409 «уже использован»
    r2 = _app_module.app.make_response(_call())
    assert r2.status_code == 409, (
        f'повторный пробный день должен отклоняться, получено {r2.status_code}'
    )



def test_trial_expiry_cuts_off_premium(app):
    """После истечения пробного дня премиум-доступ отрубается."""
    from services.pilot import can_take_theme_test
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import text

    # Пробный день истёк час назад (activate_premium не принимает прошлое —
    # вставляем истёкшую is_trial-подписку напрямую, как и в конftest)
    from models import db
    test_user = _nonpilot_user()
    _past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
        '%Y-%m-%d %H:%M:%S')
    db.session.execute(text("""
        INSERT INTO subscriptions
            (user_id, plan, status, started_at, expires_at, is_beta_access,
             is_trial, created_at)
        VALUES (:u, 'premium_intense', 'active', :started, :expires, 1, 1, :created)
    """), {'u': test_user.id, 'started': _past, 'expires': _past,
           'created': _past})
    test_user.plan_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.session.commit()

    assert test_user.is_trial_active() is False, (
        'истёкший пробный день не должен считаться активным'
    )
    assert test_user.has_access() is False
    assert can_take_theme_test(test_user) is False, (
        'тест должен закрываться после истечения пробного дня'
    )


def test_trial_day_counts_as_paid_access(app):
    """В течение пробного дня resolve_access видит платный доступ."""
    from services.access import resolve_access
    from services.subscription import get_subscription_service
    from datetime import datetime, timedelta, timezone

    test_user = _nonpilot_user()
    get_subscription_service().activate_premium(
        user_id=test_user.id, plan='premium_intense', is_beta=True,
        is_trial=True,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=23),
    )
    from models import db
    db.session.commit()

    source, _ = resolve_access(test_user)
    assert source != 'free', (
        f'во время пробного дня доступ должен быть платным, получено {source!r}'
    )
    assert test_user.has_access() is True
