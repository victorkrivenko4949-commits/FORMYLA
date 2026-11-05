# -*- coding: utf-8 -*-
"""WISH_SURVEY_V1 (06.11.2026): опрос «Что ты хочешь от Формулы?» + скидка 30%.

Правила (владелец):
  * опрос показывается всем вошедшим пользователям (не гостям), один раз;
  * ответ длиннее 30 символов (пробелы схлопываются, нужны буквы) даёт
    скидку 30% на оплату Premium — на ОБА тарифа («Работяга» и «Спокойный»);
  * скидка одноразовая: действует на первую оплаченную покупку Premium,
    продление (автосписание) идёт по полной цене.

Как устроена надёжность скидки:
  * цену считает ТОЛЬКО сервер (price_for_plan), браузер её не передаёт;
  * одна и та же функция считает цену и для страницы, и для платежа ЮKassa;
  * страница оплаты присылает сумму, которую видел человек (expected_amount);
    если серверная сумма другая — платёж не создаётся (409, «обнови страницу»),
    поэтому человек никогда не заплатит не ту сумму, что видел;
  * заказ со скидкой записывается в wish_discount_orders в той же транзакции,
    что и сам заказ; скидка считается использованной, как только такой заказ
    оплачен (yookassa_payments.paid_at), — отдельного «списания» нет, ломаться
    нечему;
  * неоплаченные/отменённые заказы скидку не сжигают.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets

from flask import Blueprint, abort, current_app, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import inspect, text

from models import db

logger = logging.getLogger(__name__)

wish_survey_bp = Blueprint('wish_survey', __name__)

DISCOUNT_PERCENT = 30
MIN_CHARS_EXCLUSIVE = 30      # «более 30 символов» → нужно 31+
MIN_LETTERS = 10              # защита от «..............................»
MAX_CHARS = 2000
QUESTION = 'Что ты хочешь от Формулы?'

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS wish_survey_answers (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        answer_text TEXT NOT NULL,
        answer_len INTEGER NOT NULL,
        discount_granted INTEGER NOT NULL DEFAULT 0,
        answered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS wish_discount_orders (
        order_id VARCHAR(64) PRIMARY KEY,
        user_id INTEGER NOT NULL,
        plan VARCHAR(64) NOT NULL,
        base_rub INTEGER NOT NULL,
        amount_rub INTEGER NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    'CREATE INDEX IF NOT EXISTS ix_wish_discount_orders_user ON wish_discount_orders(user_id)',
)


# ─────────────────────────── чистая логика ───────────────────────────

def normalize_answer(raw) -> str:
    if not isinstance(raw, str):
        return ''
    return re.sub(r'\s+', ' ', raw).strip()[:MAX_CHARS]


def qualifies(answer: str) -> bool:
    """Ответ даёт скидку: больше 30 символов и хотя бы 10 букв."""
    answer = normalize_answer(answer)
    return (len(answer) > MIN_CHARS_EXCLUSIVE
            and sum(1 for ch in answer if ch.isalpha()) >= MIN_LETTERS)


def discounted_rub(base_rub: int) -> int:
    """Цена со скидкой в целых рублях (округление до рубля, половина — вверх).

    800 → 560, 500 → 350. Целочисленная арифметика — никаких float-хвостов.
    """
    base_rub = int(base_rub)
    return (base_rub * (100 - DISCOUNT_PERCENT) + 50) // 100


# ─────────────────────────── БД ───────────────────────────

def ensure_tables() -> None:
    engine = db.engine
    if current_app.extensions.get('wish_survey_schema_engine') is engine:
        return
    try:
        with engine.begin() as conn:
            for stmt in SCHEMA:
                conn.execute(text(stmt))
    except Exception:  # noqa: BLE001
        # На PostgreSQL два воркера, одновременно выполняющие
        # CREATE TABLE IF NOT EXISTS, могут поймать duplicate key в pg_type.
        # Если таблицы в итоге есть — всё в порядке, иначе пробрасываем.
        insp = inspect(engine)
        if not (insp.has_table('wish_survey_answers') and insp.has_table('wish_discount_orders')):
            raise
        try:
            with engine.begin() as conn:
                conn.execute(text(SCHEMA[2]))
        except Exception:  # noqa: BLE001 — индекс лишь ускоряет, не обязателен
            logger.warning('[wish_survey] index create skipped (race)')
    current_app.extensions['wish_survey_schema_engine'] = engine


def _answer_row(user_id):
    ensure_tables()
    return db.session.execute(text(
        'SELECT discount_granted FROM wish_survey_answers WHERE user_id = :uid'
    ), {'uid': user_id}).first()


def discount_used(user_id) -> bool:
    """Скидка израсходована — есть ОПЛАЧЕННЫЙ заказ со скидкой."""
    ensure_tables()
    if not inspect(db.engine).has_table('yookassa_payments'):
        return False
    return db.session.execute(text(
        'SELECT 1 FROM wish_discount_orders d '
        'JOIN yookassa_payments p ON p.order_id = d.order_id '
        'WHERE d.user_id = :uid AND p.paid_at IS NOT NULL LIMIT 1'
    ), {'uid': user_id}).first() is not None


def discount_available(user_id) -> bool:
    """Есть право на скидку прямо сейчас. Ошибка БД → без скидки (и лог)."""
    if not user_id:
        return False
    try:
        row = _answer_row(user_id)
        if row is None or not int(row[0] or 0):
            return False
        return not discount_used(user_id)
    except Exception:  # noqa: BLE001
        db.session.rollback()
        logger.exception('[wish_survey] discount check failed user=%s', user_id)
        return False


def price_for_plan(base_rub: int, user_id) -> dict:
    """Единая цена для страницы и для платежа."""
    base_rub = int(base_rub)
    if discount_available(user_id):
        return {'base': base_rub, 'amount': discounted_rub(base_rub),
                'discount_pct': DISCOUNT_PERCENT}
    return {'base': base_rub, 'amount': base_rub, 'discount_pct': 0}


def record_discount_order(order_id, user_id, plan, base_rub, amount_rub) -> None:
    """Пишет заказ со скидкой в текущую транзакцию (commit делает вызывающий)."""
    ensure_tables()
    db.session.execute(text(
        'INSERT INTO wish_discount_orders (order_id, user_id, plan, base_rub, amount_rub) '
        'VALUES (:oid, :uid, :plan, :base, :amount)'
    ), {'oid': order_id, 'uid': user_id, 'plan': plan,
        'base': int(base_rub), 'amount': int(amount_rub)})


def survey_state(user_id) -> dict:
    """Для шаблонов: answered / discount_available / discount_used."""
    try:
        row = _answer_row(user_id)
        granted = bool(row is not None and int(row[0] or 0))
        used = granted and discount_used(user_id)
        return {'answered': row is not None, 'granted': granted,
                'available': granted and not used, 'used': used}
    except Exception:  # noqa: BLE001
        db.session.rollback()
        logger.exception('[wish_survey] state failed user=%s', user_id)
        return {'answered': True, 'granted': False, 'available': False, 'used': False}


# ─────────────────────────── API ───────────────────────────

def _csrf_token(user_id) -> str:
    """Stateless HMAC-токен (как у опроса готовности — без гонок сессии)."""
    secret = current_app.config.get('SECRET_KEY') or ''
    if not secret:
        current_app.logger.error('wish survey: SECRET_KEY is not set')
        abort(500)
    if isinstance(secret, str):
        secret = secret.encode('utf-8')
    msg = 'wish_survey_csrf:{}'.format(user_id).encode('utf-8')
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _is_buyer_role() -> bool:
    return (getattr(current_user, 'role', 'student') or 'student') not in ('parent', 'teacher')


def _price_lines():
    from routes.premium_pay import PLAN_INFO
    return [{'title': info['short'], 'base': int(info['price_rub']),
             'amount': discounted_rub(info['price_rub'])}
            for info in PLAN_INFO.values()]


@wish_survey_bp.get('/api/wish-survey/pending')
@login_required
def pending():
    if getattr(current_user, 'is_guest', False):
        response = jsonify(pending=False)
    else:
        state = survey_state(current_user.id)
        response = jsonify(
            pending=not state['answered'],
            can_improve=not state['granted'],
            csrf=_csrf_token(current_user.id),
            offer=_is_buyer_role(),
            percent=DISCOUNT_PERCENT,
            min_chars=MIN_CHARS_EXCLUSIVE + 1,
            prices=_price_lines(),
        )
    response.headers['Cache-Control'] = 'no-store'
    return response


@wish_survey_bp.post('/api/wish-survey')
@login_required
def answer():
    if getattr(current_user, 'is_guest', False):
        abort(403)
    supplied = request.headers.get('X-Wish-CSRF', '')
    if not supplied or not secrets.compare_digest(_csrf_token(current_user.id), supplied):
        return jsonify(ok=False, error='Обнови страницу и попробуй ещё раз.'), 403
    data = request.get_json(silent=True)
    answer_text = normalize_answer(data.get('answer') if isinstance(data, dict) else None)
    if not answer_text:
        return jsonify(ok=False, error='Напиши хотя бы пару слов.'), 400
    granted = 1 if qualifies(answer_text) else 0
    try:
        ensure_tables()
        # Повторный ответ разрешён, пока скидка не выдана (дописал короткий
        # ответ). Выданную скидку и её ответ уже ничто не перезапишет.
        db.session.execute(text(
            'INSERT INTO wish_survey_answers (user_id, answer_text, answer_len, discount_granted) '
            'VALUES (:uid, :answer, :len, :granted) '
            'ON CONFLICT (user_id) DO UPDATE SET answer_text = excluded.answer_text, '
            'answer_len = excluded.answer_len, discount_granted = excluded.discount_granted, '
            'answered_at = CURRENT_TIMESTAMP '
            'WHERE wish_survey_answers.discount_granted = 0'
        ), {'uid': current_user.id, 'answer': answer_text,
            'len': len(answer_text), 'granted': granted})
        db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()
        current_app.logger.exception('Wish survey answer failed')
        return jsonify(ok=False, error='Не удалось сохранить ответ. Попробуй ещё раз.'), 503
    state = survey_state(current_user.id)
    return jsonify(ok=True, discount=state['available'], granted=state['granted'],
                   used=state['used'], percent=DISCOUNT_PERCENT,
                   offer=_is_buyer_role(), prices=_price_lines())


def load_admin_stats() -> dict:
    ensure_tables()
    total, granted = db.session.execute(text(
        'SELECT COUNT(*), COALESCE(SUM(discount_granted), 0) FROM wish_survey_answers'
    )).one()
    used = 0
    if inspect(db.engine).has_table('yookassa_payments'):
        used = db.session.execute(text(
            'SELECT COUNT(DISTINCT d.user_id) FROM wish_discount_orders d '
            'JOIN yookassa_payments p ON p.order_id = d.order_id WHERE p.paid_at IS NOT NULL'
        )).scalar() or 0
    rows = db.session.execute(text(
        'SELECT a.user_id, u.nickname, a.answer_text, a.discount_granted, a.answered_at '
        'FROM wish_survey_answers a JOIN users u ON u.id = a.user_id '
        'ORDER BY a.answered_at DESC, a.user_id DESC LIMIT 300'
    )).mappings().all()
    return {'total': int(total or 0), 'granted': int(granted or 0),
            'used': int(used), 'rows': rows, 'question': QUESTION,
            'percent': DISCOUNT_PERCENT}
