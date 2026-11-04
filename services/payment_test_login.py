"""Scoped payment-test login. The code authenticates one dedicated account only.
Disable code login with PAYMENT_TEST_LOGIN_DISABLED=1. Existing email login and
paid subscriptions remain available. Never add this user to PILOT_USER_IDS.
"""
import functools
import hashlib
import hmac
import os
import threading
import time
from datetime import datetime
from urllib.parse import urlsplit

CODE_HASH = "600000$2868a3e1f73c410ace4ace15d5aeea41$4e65e2d50f7f2eaf7a389e8f273410bca0dd9cf739c27bf428743b40c6f6b454"
RESERVED_EMAIL = "payment-test-84@example.invalid"
RESERVED_NICK = "payment_test_84"


def verify_code(value, encoded=None):
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        return False
    try:
        rounds, salt, expected = (encoded or CODE_HASH).split('$')
        rounds = int(rounds)
        if not 100000 <= rounds <= 1000000:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', value.encode(), salt.encode(), rounds).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def same_origin(source, target):
    try:
        a, b = urlsplit(source or ''), urlsplit(target or '')
        return a.scheme in ('http', 'https') and (a.scheme, a.netloc) == (b.scheme, b.netloc)
    except ValueError:
        return False


class AttemptLimiter:
    """Bounded, thread-safe, per-process limiter (deployment uses one worker)."""
    def __init__(self):
        self.entries = {}
        self.lock = threading.Lock()

    def allow(self, key, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            self.entries = {k: v for k, v in self.entries.items() if now - v[0] < 300}
            if key not in self.entries and len(self.entries) >= 1024:
                return False
            start, count = self.entries.get(key, (now, 0))
            if count >= 8:
                return False
            self.entries[key] = (start, count + 1)
            return True


def safe_user(user):
    blocked = {'kr1venkovictor@yandex.ru', 'victor.krivenko.4949@gmail.com'}
    for name in ('ADMIN_EMAILS', 'PAYWALL_WHITELIST'):
        blocked.update(v.strip().lower() for v in os.environ.get(name, '').split(',') if v.strip())
    return bool(user and user.id not in (1, 5, 7452)
                and not user.is_admin and not user.is_guest
                and user.role == 'student'
                and (user.email or '').lower() not in blocked
                and (user.nickname or '').lower() not in
                ('victor', 'victorkrivenko', 'lavrik', 'damian.pakhonin.13'))


def mapped_user_id():
    from flask import g, has_request_context
    if not has_request_context():
        return None
    if hasattr(g, '_payment_test_uid'):
        return g._payment_test_uid
    from models import db
    from sqlalchemy import text
    try:
        with db.engine.connect() as conn:
            value = conn.execute(text('SELECT user_id FROM payment_test_account WHERE id = 1')).scalar()
    except Exception:
        value = None
    g._payment_test_uid = value
    return value


def is_test_user(user):
    return bool(user and getattr(user, 'is_authenticated', False)
                and user.id == mapped_user_id() and safe_user(user))


def get_or_create_user():
    from flask import g
    from models import db, User
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from werkzeug.exceptions import Conflict
    with db.engine.begin() as conn:
        conn.execute(text('CREATE TABLE IF NOT EXISTS payment_test_account ('
                          'id INTEGER PRIMARY KEY CHECK (id = 1), '
                          'user_id INTEGER UNIQUE NOT NULL REFERENCES users(id))'))
    def existing():
        uid = db.session.execute(text('SELECT user_id FROM payment_test_account WHERE id = 1')).scalar()
        if uid is None:
            return None
        user = db.session.get(User, uid)
        if not safe_user(user):
            raise Conflict('Тестовый аккаунт недоступен. Существующие аккаунты не изменены.')
        g._payment_test_uid = uid
        return user
    user = existing()
    if user is not None:
        return user
    if User.query.filter_by(email=RESERVED_EMAIL).first() or User.query.filter_by(nickname=RESERVED_NICK).first():
        raise Conflict('Служебный адрес или ник занят. Чужой аккаунт не используется.')
    user = User(email=RESERVED_EMAIL, nickname=RESERVED_NICK, name='Тест оплаты',
                role='student', is_guest=False, current_plan='free',
                plan_expires_at=None, trial_started_at=None, trial_until=None,
                is_founder=False, founder_price_eligible=False)
    try:
        db.session.add(user)
        db.session.flush()
        if not safe_user(user):
            db.session.rollback()
            raise Conflict('Нельзя создать тестовый аккаунт с привилегированным ID.')
        db.session.execute(text('INSERT INTO payment_test_account (id, user_id) VALUES (1, :uid)'), {'uid': user.id})
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        user = existing()
        if user is None:
            raise Conflict('Конфликт создания тестового аккаунта. Попробуйте ещё раз.')
    g._payment_test_uid = user.id
    return user


def pilot_access(user):
    from flask import has_request_context, request
    if not has_request_context():
        return False
    from flask_login import current_user
    from services.pilot import PILOT_ENABLED
    uid = getattr(user, 'id', user)
    if not PILOT_ENABLED or uid != getattr(current_user, 'id', None) or not is_test_user(current_user):
        return False
    if request.path.rstrip('/') == '/subscribe' or request.path.startswith('/payments/premium/'):
        return True
    from services.access import resolve_access
    return resolve_access(current_user)[0] == 'paid'


def extend_pilot(predicate):
    @functools.wraps(predicate)
    def wrapped(user):
        return predicate(user) or pilot_access(user)
    wrapped._payment_test_extension = True
    return wrapped


def install(app):
    if app.extensions.get('payment_test_login_installed'):
        return
    app.extensions['payment_test_login_installed'] = True
    limiter = AttemptLimiter()
    from flask import abort, current_app, flash, redirect, render_template_string, request, session
    from flask_login import current_user, login_user, logout_user
    from services.security import get_csrf_token, validate_csrf
    from services import pilot
    # Install before route modules import pilot predicates. Auto-grants still
    # iterate the unchanged PILOT_USER_IDS; paid-content checks stay in force.
    for name in ('is_pilot_user', 'is_pilot_id'):
        original = getattr(pilot, name)
        if not getattr(original, '_payment_test_extension', False):
            setattr(pilot, name, extend_pilot(original))

    def valid_submission():
        token = request.form.get('csrf_token') or request.headers.get('X-CSRFToken') or request.headers.get('X-CSRF-Token')
        try:
            if validate_csrf(token):
                return True
        except (TypeError, ValueError):
            pass
        return same_origin(request.headers.get('Origin') or request.headers.get('Referer'), request.host_url)

    def email_page():
        if not is_test_user(current_user):
            abort(403)
        plan = request.values.get('plan', 'premium_intense')
        if plan not in ('premium_intense', 'premium_calm'):
            abort(400)
        error = ''
        if request.method == 'POST':
            if not valid_submission():
                abort(403)
            import re
            from models import db, User
            from sqlalchemy import func
            email = (request.form.get('email') or '').strip().lower()
            if len(email) > 120 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or email.endswith('.invalid'):
                error = 'Укажите действующий email для чека.'
            elif User.query.filter(func.lower(User.email) == email, User.id != current_user.id).first():
                error = 'Этот email уже занят. Существующий аккаунт не изменяется.'
            else:
                old_email = current_user.email
                current_user.email = email
                if not safe_user(current_user):
                    current_user.email = old_email
                    error = 'Для теста нужен обычный, не привилегированный email.'
                else:
                    from sqlalchemy.exc import IntegrityError
                    try:
                        db.session.commit()
                    except IntegrityError:
                        db.session.rollback()
                        error = 'Этот email уже занят. Укажите другой адрес.'
                    else:
                        return redirect('/payments/premium/checkout?plan=' + plan)
        return render_template_string("""<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Email для чека</title>
<body style="font:18px system-ui;max-width:520px;margin:60px auto;padding:20px">
<h1>Email для чека</h1><p>Тестовый аккаунт уже создан. Укажите свою почту перед покупкой.
Существующие аккаунты не объединяются. Вход по спецкоду сохранится.</p>
<p role="alert">{{ error }}</p><form method="post">
<input type="hidden" name="csrf_token" value="{{ token }}">
<input type="hidden" name="plan" value="{{ plan }}">
<label>Email <input type="email" name="email" required maxlength="120" autocomplete="email"></label>
<button type="submit">Перейти к оплате</button></form><p><a href="/subscribe">Назад к тарифам</a></p></body></html>""", error=error, plan=plan, token=get_csrf_token())

    app.add_url_rule('/payment-test/email', 'payment_test_email', email_page, methods=['GET', 'POST'])

    @app.before_request
    def payment_test_hook():
        if request.endpoint == 'login' and request.method == 'POST' and os.environ.get('PAYMENT_TEST_LOGIN_DISABLED') != '1':
            value = (request.form.get('email') or '').strip()
            if value and '@' not in value and len(value) <= 128:
                if not limiter.allow(request.remote_addr or 'unknown'):
                    abort(429, description='Слишком много попыток. Подождите пять минут.')
                if verify_code(value):
                    if not valid_submission():
                        abort(403)
                    user = get_or_create_user()
                    from models import db
                    user.last_login = datetime.utcnow()
                    db.session.commit()
                    logout_user()
                    session.clear()
                    session['_remember'] = 'clear'
                    login_user(user, remember=False, fresh=True)
                    get_csrf_token()
                    flash('Тест оплаты: Premium заранее не выдан. Код даёт вход только в этот аккаунт — не передавайте его другим.', 'info')
                    return redirect('/subscribe')
        if request.endpoint == 'payment_test_email':
            return email_page()
        if request.path.startswith('/payments/premium/') and is_test_user(current_user):
            if request.method == 'POST' and not valid_submission():
                abort(403)
            if request.path.endswith('/checkout') and current_user.email == RESERVED_EMAIL:
                plan = request.args.get('plan', 'premium_intense')
                if plan not in ('premium_intense', 'premium_calm'):
                    plan = 'premium_intense'
                return redirect('/payment-test/email?plan=' + plan)
            if request.path.endswith('/create'):
                if current_user.email == RESERVED_EMAIL:
                    return {'error': 'Сначала укажите email для чека.', 'redirect': '/payment-test/email'}, 409
                from routes.yookassa_pay import get_yookassa_config
                if not get_yookassa_config().get('configured'):
                    return {'error': 'ЮKassa не настроена. Тестовый аккаунт не получает Premium через демооплату.'}, 503
