# -*- coding: utf-8 -*-
"""routes/schedule_days.py — PILOT_SCHEDULE_DAYS_V1 (03.11.2026).

Страница выбора дней занятий после покупки пилотного тарифа.

  * GET  /schedule          — 7 дней недели, «Выберите дни занятий»;
                              нужно выбрать ровно 6 («Работяга») или
                              3 («Спокойный») дня;
  * POST /schedule/save     — сохранение выбора (JSON), после успеха
                              редирект на задачи дня.

Страницу нельзя обойти: пока выбор не сделан, before_request-гейт
force_schedule_selection в app.py возвращает ученика с любого пути
обратно на /schedule.

Без активного пилотного тарифа /schedule просто редиректит на
/daily_tasks — кнопка «Перейти к задачам дня» после оплаты ведёт
сюда и не ломается для выбравших дни ранее.
"""
import logging

from flask import (Blueprint, jsonify, redirect, render_template,
                   request)
from flask_login import current_user, login_required

from models import db
from services.schedule_days import (
    WEEKDAY_LABELS,
    WEEKDAY_SHORT,
    days_for_plan,
    get_user_days,
    required_days_count,
    save_user_days,
)

logger = logging.getLogger('formyla.schedule_days')

schedule_days_bp = Blueprint('schedule_days', __name__)


def _active_pilot_plan(user_id: int):
    """Активный пилотный тариф пользователя или None.

    Один SQL-запрос к subscriptions — как get_user_plan, но без
    загрузки лимитов: гейт и страница должны быть лёгкими.
    """
    try:
        from datetime import datetime
        from sqlalchemy import text
        row = db.session.execute(text(
            "SELECT plan FROM subscriptions "
            "WHERE user_id = :uid AND status = 'active' "
            "  AND (expires_at IS NULL OR expires_at > :now) "
            "  AND plan IN ('premium_intense', 'premium_calm') "
            "ORDER BY id DESC LIMIT 1"),
            {'uid': int(user_id),
             'now': datetime.utcnow().isoformat()}).fetchone()
        return row[0] if row else None
    except Exception as e:  # noqa: BLE001
        logger.warning('[schedule_days] plan lookup failed: %r', e)
        return None


@schedule_days_bp.route('/schedule', methods=['GET'])
@login_required
def schedule_page():
    plan = _active_pilot_plan(current_user.id)
    need = required_days_count(plan)
    if need is None:
        # Нет активного пилотного тарифа — выбирать нечего
        return redirect('/daily_tasks')

    chosen = days_for_plan(current_user.id, plan)
    if chosen:
        # Дни уже выбраны под этот тариф — на страницу выбора не возвращаем
        return redirect('/daily_tasks')

    plan_titles = {
        'premium_intense': 'Работяга',
        'premium_calm': 'Спокойный',
    }
    return render_template(
        'schedule_days.html',
        plan=plan,
        plan_title=plan_titles.get(plan, plan),
        need=need,
        weekdays=[{'i': i, 'label': WEEKDAY_LABELS[i],
                   'short': WEEKDAY_SHORT[i]} for i in range(7)],
    )


@schedule_days_bp.route('/schedule/save', methods=['POST'])
@login_required
def schedule_save():
    plan = _active_pilot_plan(current_user.id)
    if required_days_count(plan) is None:
        return jsonify({'ok': False,
                        'error': 'Активный пилотный тариф не найден'}), 400

    payload = request.get_json(silent=True) or {}
    days = payload.get('days')
    if not isinstance(days, list):
        return jsonify({'ok': False,
                        'error': 'Выберите дни занятий'}), 400

    if save_user_days(current_user.id, days, plan):
        return jsonify({'ok': True, 'redirect': '/daily_tasks'})

    need = required_days_count(plan)
    return jsonify({'ok': False,
                    'error': f'Нужно выбрать ровно {need} '
                             f'{"дня" if need == 3 else "дней"}'}), 400
