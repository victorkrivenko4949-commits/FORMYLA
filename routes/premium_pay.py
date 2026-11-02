# -*- coding: utf-8 -*-
"""
routes/premium_pay.py — PREMIUM_PAY_V1 (24.10.2026): оплата тарифов Premium.

Полный цикл покупки:
  * GET  /payments/premium/checkout?plan=premium_intense|premium_calm
         — страница оформления: что входит, цена, кнопка «Оплатить»
  * POST /payments/premium/create
         — создание платежа ЮKassa (item_code = тариф) и редирект на оплату
  * GET  /payments/premium/return?order_id=...
         — возврат с оплаты: проверка статуса + активация Premium

PREMIUM_GIFT_V1 (01.11.2026): покупка Premium РОДИТЕЛЕМ или УЧИТЕЛЕМ
для ребёнка. Параметр for_user=<id ребёнка>:
  * checkout/create — проверяем подтверждённую связь (родитель:
    ParentChildLink accepted; учитель: accepted-участник его группы);
  * в заказе хранится beneficiary_user_id — кто получает Premium;
  * после оплаты Premium активируется ИМЕННО ребёнку, а не платящему.
Автопродление для подарочных платежей не подключается.

Вебхук — общий с значком (routes/yookassa_pay.py): по item_code
активирует premium_intense/premium_calm (30 дней полного доступа).

Подключение реальной оплаты (один раз, без правок кода):
  указать Shop ID и Секретный ключ ЮKassa в профиле (карточка ЮKassa)
  или в переменных окружения YOOKASSA_SHOP_ID / YOOKASSA_SECRET_KEY.
  До этого работает демо-режим: «Оплатить» проводит платёж без списания
  (для теста полного цикла).

Доступен только пилотным аккаунтам (до запуска 3 ноября).
Отключить: PREMIUM_PAY_AUTOREG=0.
"""
import json
import logging
import os
import uuid
from datetime import datetime

import requests
from flask import (Blueprint, abort, current_app, jsonify, redirect,
                    render_template, request, url_for)
from flask_login import current_user, login_required
from sqlalchemy import text

from models import db

logger = logging.getLogger(__name__)

premium_pay_bp = Blueprint('premium_pay', __name__)

YOOKASSA_API_BASE = "https://api.yookassa.ru/v3"

PLAN_INFO = {
    'premium_intense': {
        'icon': '⚡',
        'short': 'Работяга',
        'title': 'Premium «Работяга»',
        'price_rub': 800,
        'tagline': 'Для готовых пахать',
        'features': [
            '6 занятий в неделю',
            '1 пробник в неделю — реальный вариант прошлых лет',
            '1 метод в неделю — 70% разбор + 3 задачи',
            '4 занятия — задачи дня',
            'ИИ-тьютор, куратор и генератор чертежей',
        ],
    },
    'premium_calm': {
        'icon': '🌿',
        'short': 'Спокойный',
        'title': 'Premium «Спокойный»',
        'price_rub': 500,
        'tagline': 'Без спешки',
        'features': [
            '3 занятия в неделю по 1.5 часа',
            '1 пробник в 2 недели',
            '1 метод в 2 недели',
            'Задачи дня и тесты — как у всех',
            'ИИ-тьютор, куратор и генератор чертежей',
        ],
    },
}


def _pilot_or_404():
    """Оплата Premium доступна только пилотным аккаунтам (до 3 ноября)."""
    from services.pilot import is_pilot_user
    if not (getattr(current_user, 'is_authenticated', False)
            and is_pilot_user(current_user.id)):
        abort(404)


def _is_parent_or_teacher() -> bool:
    """Роль из первого вопроса анкеты — родитель или учитель.

    PARENT_TEACHER_NO_BUY (02.11.2026, владелец): такие аккаунты не
    оформляют Premium-пилот в принципе — ни себе, ни подарочно для
    ребёнка. Покупка и пробный день выполняются в аккаунте ученика.
    """
    return (getattr(current_user, 'role', 'student') or 'student') in ('parent', 'teacher')


PARENT_TEACHER_BUY_MESSAGE = (
    'Оформите это в аккаунте ребёнка: Premium-пилот оформляется '
    'в аккаунте ученика, а не в аккаунте родителя или учителя.'
)


# ── PREMIUM_GIFT_V1: покупка Premium для ребёнка ──────────────────────────

def _gift_child(for_user_raw):
    """Ребёнок (User), для которого текущий пользователь может купить Premium.

    Разрешено только по ПОДТВЕРЖДЁННОЙ связи:
      * родитель — ParentChildLink(status='accepted');
      * учитель — ученик состоит в его группе (T10GroupMember accepted).
    Никнейм/progress не важны: платит взрослый, Premium получает ребёнок.
    Возвращает User или None.
    """
    if not getattr(current_user, 'is_authenticated', False):
        return None
    try:
        child_id = int(for_user_raw)
    except (TypeError, ValueError):
        return None
    if not child_id or child_id == current_user.id:
        return None

    from models import ParentChildLink, T10Group, T10GroupMember, User
    child = User.query.get(child_id)
    if child is None:
        return None
    child_role = getattr(child, 'role', 'student') or 'student'
    if child_role in ('teacher', 'parent'):
        return None

    # Родитель: подтверждённая связь с ребёнком
    link = ParentChildLink.query.filter_by(
        parent_id=current_user.id, child_id=child.id, status='accepted',
    ).first()
    if link is not None:
        return child

    # Учитель: ученик — accepted-участник одной из его групп
    member = T10GroupMember.query.join(T10Group).filter(
        T10GroupMember.user_id == child.id,
        T10Group.teacher_id == current_user.id,
        T10GroupMember.status == 'accepted',
    ).first()
    if member is not None:
        return child

    return None


def _pilot_or_gift_or_404(for_user_raw=None):
    """Доступ к оплате: пилотный аккаунт ИЛИ покупка для своего ребёнка.

    Возвращает ребёнка (User) для подарочной покупки или None для обычной.
    """
    from services.pilot import is_pilot_user
    if getattr(current_user, 'is_authenticated', False) and is_pilot_user(current_user.id):
        return _gift_child(for_user_raw) if for_user_raw else None
    child = _gift_child(for_user_raw)
    if child is None:
        abort(404)
    return child


def _beneficiary_of_order(order_id=None, payment_id=None) -> int | None:
    """Кому выдать Premium по этому заказу (beneficiary_user_id или None)."""
    try:
        row = db.session.execute(text(
            "SELECT beneficiary_user_id FROM yookassa_payments "
            "WHERE (order_id = :oid OR payment_id = :pid) LIMIT 1"
        ), {'oid': order_id or '', 'pid': payment_id or ''}).fetchone()
        return int(row[0]) if row and row[0] else None
    except Exception:  # noqa: BLE001
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


def _user_display_by_id(uid: int) -> str | None:
    """Отображаемое имя пользователя по id (для страниц оплаты)."""
    try:
        from models import User
        u = User.query.get(int(uid))
        if u is None:
            return None
        try:
            return u.display_name
        except Exception:
            from services.user_helpers import display_name_from_email
            return display_name_from_email(u.email)
    except Exception:  # noqa: BLE001
        return None


def _active_premium(user_id=None):
    """Активная premium-подписка пользователя (или None).

    Если Premium уже оплачен и не истёк — оплату повторно не предлагаем.
    Для подарочной покупки проверяем подписку РЕБЁНКА (for_user).
    FAIL-CLOSED: если проверку не удалось выполнить, оплата запрещена —
    лучше не дать купить лишний раз, чем списать деньги повторно.
    """
    try:
        from services.subscription import get_subscription_service
        plan = get_subscription_service().get_user_plan(user_id or current_user.id)
        if plan.get('is_premium'):
            return plan
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning('[premium_pay] plan lookup failed (payment blocked): %r', e)
        return {'is_premium': True, 'error': 'plan_lookup_failed'}


def _yk_config() -> dict:
    """Конфиг ЮKassa (общий с значком-алмазом)."""
    try:
        from routes.yookassa_pay import get_yookassa_config
        return get_yookassa_config()
    except Exception as e:  # noqa: BLE001
        logger.warning('[premium_pay] yookassa config failed: %r', e)
        return {'configured': False, 'shop_id': '', 'secret_key': '',
                'send_receipt': False, 'is_test': False}


def _recurring_enabled() -> bool:
    """Опция «Подписки (автоплатежи)» у магазина в ЮKassa.

    Пока менеджер ЮKassa не включил её магазину, ЛЮБОЙ платёж с
    save_payment_method=true отклоняется ошибкой
    'This store can't make recurring payments' — у каждого покупателя
    падала бы оплата. Поэтому по умолчанию платим разово (без
    save_payment_method), автопродление не подключается.

    Когда менеджер ЮKassa включит рекуррентные платежи магазину —
    поставить YOOKASSA_RECURRING_PAYMENTS=1 в .env и перезапустить
    сервис: вернётся save_payment_method, автопродление и копирайт
    «списания каждые 30 дней» на странице оплаты.
    """
    return os.environ.get('YOOKASSA_RECURRING_PAYMENTS', '0').strip().lower() \
        in ('1', 'true', 'yes', 'on')


def activate_premium_for_payment(user_id: int, plan: str,
                                 payment_id=None, order_id=None) -> dict:
    """Активировать Premium после оплаты (30 дней, настоящий платный статус).

    Идемпотентно НА УРОВНЕ ПЛАТЕЖА: атомарный захват по paid_at в
    yookassa_payments — повторный вебхук или повторное открытие старой
    ссылки возврата НЕ активирует и НЕ переписывает оплаченный срок
    более новой подписки. Возвращает {'ok': True, 'already_applied': True},
    если платёж уже был применён.
    """
    if plan not in PLAN_INFO:
        return {'ok': False, 'error': 'unknown plan'}
    price = PLAN_INFO[plan]['price_rub']

    # PREMIUM_GIFT_V1: подарочный заказ — Premium получает РЕБЁНОК,
    # а не платящий родитель/учитель (beneficiary_user_id в заказе).
    beneficiary_id = _beneficiary_of_order(order_id, payment_id)
    target_id = beneficiary_id or user_id

    # ОДНА транзакция: захват платежа → активация → единый commit.
    # Падение активации откатывает и захват (paid_at), не оставляя
    # «деньги получены, доступа нет» — повтор успешно докатит активацию.
    try:
        res = db.session.execute(text(
            "UPDATE yookassa_payments SET paid_at = :now"
            " WHERE (order_id = :oid OR payment_id = :pid) AND paid_at IS NULL"
        ), {'now': datetime.utcnow(),
            'oid': order_id or '', 'pid': payment_id or ''})
        if (res.rowcount or 0) == 0:
            # Строка есть, но paid_at уже стоит — платёж применён ранее.
            row = db.session.execute(text(
                "SELECT id FROM yookassa_payments WHERE order_id = :oid OR payment_id = :pid LIMIT 1"
            ), {'oid': order_id or '', 'pid': payment_id or ''}).fetchone()
            if row:
                db.session.commit()
                logger.info('[premium_pay] payment already applied, skip (user=%s)', user_id)
                return {'ok': True, 'already_applied': True}
            # Строки нет (легаси-платёж до фикса) — активируем без маркера.

        from services.subscription import get_subscription_service
        svc = get_subscription_service()
        result = svc.activate_premium(
            user_id=target_id,
            plan=plan,
            payment_id=f"yookassa:{payment_id}" if payment_id else f"order:{order_id}",
            is_beta=False,
            amount_rub=price,
        )
        # Единый commit: и захват paid_at, и подписка — атомарно
        db.session.commit()
        logger.info('[premium_pay] activated %s for user=%s (payer=%s, payment=%s)',
                    plan, target_id, user_id, payment_id)
        return {'ok': True, 'result': result, 'target_user_id': target_id}
    except Exception as e:  # noqa: BLE001
        # Откат ВСЕЙ транзакции, включая захват paid_at.
        db.session.rollback()
        logger.error('[premium_pay] activation failed user=%s: %r (rolled back, will retry)', target_id, e)
        return {'ok': False, 'error': str(e)}


# ── Страница оформления ────────────────────────────────────────────────────

@premium_pay_bp.route('/payments/premium/checkout', methods=['GET'])
@login_required
def checkout():
    # PARENT_TEACHER_NO_BUY (02.11.2026): родитель и учитель не покупают
    # Premium-пилот вообще — страница /subscribe сама покажет им
    # «Оформите это в аккаунте ребёнка».
    if _is_parent_or_teacher():
        return redirect('/subscribe')

    # PREMIUM_GIFT_V1: родитель/учитель может оформить Premium для ребёнка.
    child = _pilot_or_gift_or_404(request.args.get('for_user'))
    plan = request.args.get('plan', 'premium_intense')
    if plan not in PLAN_INFO:
        plan = 'premium_intense'
    info = PLAN_INFO[plan]
    cfg = _yk_config()

    beneficiary = None
    beneficiary_id = None
    if child is not None:
        beneficiary_id = child.id
        try:
            beneficiary = child.display_name
        except Exception:
            from services.user_helpers import display_name_from_email
            beneficiary = display_name_from_email(child.email)

    # Premium уже активен — новую оплату не создаём (защита от двойной оплаты).
    # Для подарка проверяем подписку РЕБЁНКА, а не платящего.
    active = _active_premium(beneficiary_id)
    if active:
        from services.auto_renew import get_auto_renewal
        auto_renew = get_auto_renewal(beneficiary_id or current_user.id)
        active_plan_key = active.get('plan')
        active_info = PLAN_INFO.get(active_plan_key)
        expires = active.get('expires_at')
        return render_template('payments/premium_checkout.html',
                               plan=plan, info=info, cfg=cfg,
                               already_premium=True,
                               premium_until=str(expires)[:16] if expires else None,
                               active_title=active_info['title'] if active_info else 'Premium',
                               active_icon=active_info['icon'] if active_info else '⭐',
                               auto_renew=auto_renew if not beneficiary_id else None,
                               recurring_enabled=_recurring_enabled(),
                               for_user=beneficiary_id,
                               beneficiary=beneficiary)

    from services.auto_renew import get_auto_renewal as _gar
    return render_template('payments/premium_checkout.html',
                           plan=plan, info=info, cfg=cfg,
                           auto_renew=_gar(current_user.id) if not beneficiary_id else None,
                           recurring_enabled=_recurring_enabled(),
                           for_user=beneficiary_id,
                           beneficiary=beneficiary)


# ── Создание платежа ───────────────────────────────────────────────────────

@premium_pay_bp.route('/payments/premium/create', methods=['POST'])
@login_required
def create_payment():
    # PARENT_TEACHER_NO_BUY (02.11.2026): родитель и учитель не могут
    # купить Premium-пилот — ни себе, ни для ребёнка. Оформление —
    # в аккаунте ученика.
    if _is_parent_or_teacher():
        return jsonify({'error': PARENT_TEACHER_BUY_MESSAGE}), 403

    data = request.get_json(silent=True) or {}
    plan = data.get('plan') or request.form.get('plan') or 'premium_intense'
    if plan not in PLAN_INFO:
        return jsonify({'error': 'Неизвестный тариф'}), 400

    # PREMIUM_GIFT_V1: for_user — ребёнок, для которого покупают Premium.
    for_user = data.get('for_user') or request.form.get('for_user')
    child = _pilot_or_gift_or_404(for_user)
    beneficiary_id = child.id if child is not None else None

    info = PLAN_INFO[plan]
    cfg = _yk_config()

    # Premium уже активен — новую оплату не создаём (защита от двойной оплаты).
    # Для подарка проверяем подписку РЕБЁНКА.
    if _active_premium(beneficiary_id):
        already_msg = ('У ученика уже активен Premium — повторная оплата не требуется.'
                       if beneficiary_id else
                       'У вас уже активен Premium — повторная оплата не требуется.')
        return jsonify({'error': already_msg, 'already_premium': True}), 409

    order_id = uuid.uuid4().hex
    nick_label = current_user.nickname or f"id={current_user.id}"
    gift_label = None
    if beneficiary_id:
        from models import User as _U
        _child = child or _U.query.get(beneficiary_id)
        if _child is not None:
            gift_label = getattr(_child, 'nickname', None) or f"id={beneficiary_id}"

    # FAIL-CLOSED FIX: сначала сохраняем заказ в БД, потом создаём платёж
    # в ЮKassa. Раньше строка писалась ПОСЛЕ создания платежа, и если INSERT
    # падал, пользователю всё равно показывали ссылку на оплату: он платил,
    # а после возврата сайт не находил заказ («Платёж не найден») и доступ
    # не выдавался. Теперь без записи в БД платёж вообще не создаётся.
    # FIX 01.11.2026 (прод-бага «Не удалось сохранить заказ»): таблицы
    # yookassa_payments создаёт routes/yookassa_pay._ensure_tables; на
    # PostgreSQL он ломался на ALTER users.has_diamond (колонка уже есть
    # от auto_migrate) — транзакция абортировалась, таблицы не создавались
    # либо оставались без beneficiary_user_id, и INSERT падал с 500 у
    # каждого покупателя. _ensure_tables переписан (каждая DDL в своей
    # транзакции), здесь дублируем вызов явно перед вставкой.
    from routes.yookassa_pay import _ensure_tables
    _ensure_tables()
    try:
        db.session.execute(text(
            "INSERT INTO yookassa_payments "
            "(order_id, payment_id, user_id, item_code, amount_rub, status, confirmation_url, created_at, beneficiary_user_id) "  # noqa: E501
            "VALUES (:oid, NULL, :uid, :item, :amount, 'pending', NULL, :now, :ben)"
        ), {
            'oid': order_id, 'uid': current_user.id, 'item': plan,
            'amount': float(info['price_rub']),
            'now': datetime.utcnow(),
            'ben': beneficiary_id,
        })
        db.session.commit()
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.exception('[premium_pay] order insert failed (payment NOT created): %r', e)
        return jsonify({'error': 'Не удалось сохранить заказ. Платёж не создавался — деньги не списаны. Попробуйте ещё раз.'}), 500

    # ── Демо-режим (ЮKassa не настроена): платёж без списания ──────────
    if not cfg.get('configured'):
        try:
            db.session.execute(text(
                "UPDATE yookassa_payments SET payment_id = :pid, status = 'succeeded' "
                "WHERE order_id = :oid"
            ), {'pid': f"demo_{order_id[:12]}", 'oid': order_id})
            db.session.commit()
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            logger.warning('[premium_pay] demo update failed: %r', e)
        return jsonify({'ok': True, 'demo': True, 'order_id': order_id,
                        'redirect': f"/payments/premium/return?order_id={order_id}&demo=1"})

    # ── Реальный платёж ЮKassa ──────────────────────────────────────────
    return_url = url_for('premium_pay.payment_return', order_id=order_id, _external=True)
    if beneficiary_id:
        # Подарочная покупка: платит взрослый, Premium получает ребёнок.
        # save_payment_method НЕ включаем — автопродление для подарков
        # не подключается (взрослый платит разово, без подписки).
        payload = {
            "amount": {"value": f"{info['price_rub']}.00", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": (
                f"{info['title']} на FORMYLA (30 дней) для ученика @{gift_label} — "
                f"оплачивает @{nick_label}"
            ),
            "metadata": {
                "order_id": order_id,
                "user_id": str(current_user.id),
                "item": plan,
                "for_user": str(beneficiary_id),
            },
        }
    else:
        payload = {
            "amount": {"value": f"{info['price_rub']}.00", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            # save_payment_method=True отклоняется ЮKassa с ошибкой
            # 'This store can't make recurring payments', пока у магазина
            # не включена опция рекуррентных платежей (см. _recurring_enabled).
            "save_payment_method": _recurring_enabled(),  # автопродление: ЮKassa сохранит способ оплаты
            "description": f"{info['title']} на FORMYLA (30 дней) — @{nick_label}",
            "metadata": {
                "order_id": order_id,
                "user_id": str(current_user.id),
                "item": plan,
            },
        }
    if cfg.get('send_receipt'):
        customer_email = current_user.email if (current_user.email and '@' in current_user.email) else ''
        if customer_email:
            payload["receipt"] = {
                "customer": {"email": customer_email},
                "items": [{
                    "description": f"{info['title']} (30 дней)",
                    "quantity": "1.00",
                    "amount": {"value": f"{info['price_rub']}.00", "currency": "RUB"},
                    "vat_code": 1,
                    "payment_mode": "full_payment",
                    "payment_subject": "service",
                }],
            }

    try:
        resp = requests.post(
            f"{YOOKASSA_API_BASE}/payments",
            auth=(cfg['shop_id'], cfg['secret_key']),
            headers={"Idempotence-Key": order_id, "Content-Type": "application/json"},
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            timeout=15,
        )
        yk = resp.json() if resp.content else {}
    except Exception as e:  # noqa: BLE001
        logger.exception('[premium_pay] yookassa request failed: %r', e)
        return jsonify({'error': 'Ошибка соединения с ЮKassa'}), 502

    if resp.status_code not in (200, 201):
        err = yk.get('description') or yk.get('code') or f'HTTP {resp.status_code}'
        logger.error('[premium_pay] yookassa rejected: %s', err)
        return jsonify({'error': f'ЮKassa отклонила платёж: {err}'}), 502

    confirmation_url = (yk.get('confirmation') or {}).get('confirmation_url')
    payment_id = yk.get('id')
    status = yk.get('status', 'pending')

    # Обновляем сохранённый заказ данными платежа (payment_id может прийти
    # и позже — вебхук допишет). Ошибка обновления не блокирует оплату.
    try:
        db.session.execute(text(
            "UPDATE yookassa_payments SET payment_id = COALESCE(:pid, payment_id), "
            "status = :st, confirmation_url = :curl WHERE order_id = :oid"
        ), {'pid': payment_id, 'st': status, 'curl': confirmation_url, 'oid': order_id})
        db.session.commit()
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logger.warning('[premium_pay] payment row update failed order=%s: %r', order_id, e)

    if not confirmation_url:
        return jsonify({'error': 'ЮKassa не вернула ссылку на оплату'}), 502
    return jsonify({'ok': True, 'redirect': confirmation_url})


def _top_premium_expires(user_id):
    """Дата окончания самой поздней активной premium-подписки (для страницы)."""
    try:
        from services.subscription import get_subscription_service
        plan = get_subscription_service().get_user_plan(user_id)
        return plan.get('expires_at') if plan.get('is_premium') else None
    except Exception:  # noqa: BLE001
        return None


# ── Автопродление: вкл/выкл ────────────────────────────────────────────────

@premium_pay_bp.route('/payments/premium/auto-renew', methods=['POST'])
@login_required
def toggle_auto_renew():
    """Включить/выключить автопродление Premium.

    Идемпотентно: тело запроса {'enabled': true|false} задаёт желаемое
    состояние — повтор того же запроса не «переключает» обратно.
    Без тела — переключение текущего состояния.
    Выключение не трогает оплаченный период — доступ сохраняется до конца.
    Включение возможно только при сохранённом способе оплаты (после первой
    оплаты тарифа).
    """
    _pilot_or_404()
    from services.auto_renew import get_auto_renewal, set_enabled
    ar = get_auto_renewal(current_user.id)
    if not ar:
        return jsonify({'error': 'Автопродление недоступно: способ оплаты ещё не сохранён (он сохранится при первой оплате тарифа).'}), 400

    data = request.get_json(silent=True) or {}
    if isinstance(data.get('enabled'), bool):
        new_state = data['enabled']
    else:
        new_state = not bool(ar.get('enabled'))
    if new_state and not ar.get('payment_method_id'):
        return jsonify({'error': 'Некуда списывать: сохраните способ оплаты при оплате тарифа.'}), 400
    if set_enabled(current_user.id, new_state):
        return jsonify({'ok': True, 'enabled': new_state,
                        'message': 'Автопродление включено — Premium будет продлеваться сам каждые 30 дней.' if new_state
                                   else 'Автопродление отключено — доступ сохранится до конца оплаченного периода.'})
    return jsonify({'error': 'Не удалось изменить настройку, попробуйте ещё раз'}), 500


# ── Возврат с оплаты ────────────────────────────────────────────────────────

@premium_pay_bp.route('/payments/premium/return', methods=['GET'])
@login_required
def payment_return():
    order_id = request.args.get('order_id') or ''
    demo = request.args.get('demo') == '1'
    if not order_id:
        return redirect('/subscribe')

    # Платёж в базе
    row = None
    try:
        row = db.session.execute(text(
            "SELECT user_id, item_code, status, payment_id, beneficiary_user_id"
            " FROM yookassa_payments WHERE order_id = :oid LIMIT 1"
        ), {'oid': order_id}).fetchone()
    except Exception as e:  # noqa: BLE001
        logger.warning('[premium_pay] return lookup failed: %r', e)

    if not row:
        return render_template('payments/premium_result.html',
                               status='not_found', info=None, plan=None), 404

    p_user_id, item_code, p_status, payment_id = row[0], row[1], row[2], row[3]
    p_beneficiary = row[4] if len(row) > 4 else None
    if p_user_id != current_user.id:
        abort(403)

    # Доступ: пилотный аккаунт ИЛИ подарочный заказ (Premium — ребёнку).
    from services.pilot import is_pilot_user
    if not (is_pilot_user(current_user.id) or p_beneficiary):
        abort(404)

    # PREMIUM_GIFT_V1: кому выдать Premium и как его показать на странице.
    beneficiary_id = int(p_beneficiary) if p_beneficiary else None
    target_id = beneficiary_id or current_user.id
    beneficiary_name = _user_display_by_id(beneficiary_id) if beneficiary_id else None

    plan = item_code if item_code in PLAN_INFO else None
    info = PLAN_INFO.get(plan) if plan else None

    # Демо-режим: активируем сразу
    if demo and p_status == 'succeeded':
        from services.auto_renew import get_auto_renewal, upsert_from_payment, handle_succeeded_payment
        # Единый финализатор: заказ автосписания продлевается контуром
        # продления (идемпотентно), первый платёж — обычной активацией
        # (activate_premium_for_payment тоже идемпотентен: атомарный захват
        # по paid_at не даст повторному вебхуку/возврату переписать срок).
        if plan and handle_succeeded_payment(order_id, payment_id, current_user.id, plan):
            result = {'ok': True}
        else:
            result = activate_premium_for_payment(current_user.id, plan, payment_id, order_id)
        expires = _top_premium_expires(target_id) or \
            ((result.get('result') or {}).get('expires_at') if result.get('ok') else None)
        if plan and not beneficiary_id:
            # Автопродление подключаем только для обычной (не подарочной)
            # покупки — подарки не создают подписку со списаниями.
            upsert_from_payment(current_user.id, payment_id, plan)
        return render_template('payments/premium_result.html',
                               status='succeeded', info=info, plan=plan, demo=True,
                               expires=str(expires)[:16] if expires else None,
                               auto_renew=get_auto_renewal(current_user.id) if not beneficiary_id else None,
                               recurring_enabled=_recurring_enabled(),
                               beneficiary=beneficiary_name)

    # Реальный платёж: перепроверяем статус в API ЮKassa
    cfg = _yk_config()
    if cfg.get('configured') and payment_id and not str(payment_id).startswith('demo_'):
        try:
            resp = requests.get(
                f"{YOOKASSA_API_BASE}/payments/{payment_id}",
                auth=(cfg['shop_id'], cfg['secret_key']),
                timeout=10,
            )
            if resp.status_code == 200:
                remote = resp.json() or {}
                p_status = remote.get('status') or p_status
        except Exception as e:  # noqa: BLE001
            logger.warning('[premium_pay] return verify failed: %r', e)

    if p_status == 'succeeded':
        # Единый финализатор (идемпотентность): заказ автосписания уже
        # продлевался контуром продления — не активируем повторно.
        # Первый платёж активируется с атомарным захватом по paid_at —
        # повторное открытие старой ссылки не перепишет оплаченный срок.
        from services.auto_renew import get_auto_renewal, upsert_from_payment, handle_succeeded_payment
        if plan and handle_succeeded_payment(order_id, payment_id, current_user.id, plan):
            expires = _top_premium_expires(target_id)
        else:
            result = activate_premium_for_payment(current_user.id, plan, payment_id, order_id)
            expires = _top_premium_expires(target_id) or \
                ((result.get('result') or {}).get('expires_at') if result.get('ok') else None)
        if plan and not beneficiary_id:
            # Автопродление подключаем только для обычной (не подарочной)
            # покупки — подарки не создают подписку со списаниями.
            upsert_from_payment(current_user.id, payment_id, plan)
        return render_template('payments/premium_result.html',
                               status='succeeded', info=info, plan=plan,
                               expires=str(expires)[:16] if expires else None,
                               auto_renew=get_auto_renewal(current_user.id) if not beneficiary_id else None,
                               recurring_enabled=_recurring_enabled(),
                               beneficiary=beneficiary_name)

    if p_status == 'canceled':
        return render_template('payments/premium_result.html',
                               status='canceled', info=info, plan=plan)

    return render_template('payments/premium_result.html',
                           status='pending', info=info, plan=plan)


def install_premium_pay(app, register=None) -> None:
    """Регистрация blueprint'а (вызывается из routes/__init__.py)."""
    if app.extensions.get('premium_pay_installed'):
        return
    app.extensions['premium_pay_installed'] = True
    if register is None:
        app.register_blueprint(premium_pay_bp)
    else:
        register(app, premium_pay_bp)
