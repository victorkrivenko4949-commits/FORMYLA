# -*- coding: utf-8 -*-
"""
services/daily_debt.py — Двигатель долга задач дня.

Правила:
  1) Задача, не решённая до конца суток выдачи → debt_status='active'
  2) debt_until = target_date родительского сета + 7 дней
  3) При первом заходе ученика просроченный долг → 'burned'
  4) Никаких штрафов по уровню при сгорании
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List

from models import db
from daily_tasks.models import DailyTaskSet, DailyTaskItem

logger = logging.getLogger(__name__)

DEBT_TTL_DAYS = 7


def migrate_to_debt(user_id: int, before_date: date) -> int:
    """Перенести все нерешённые задачи пользователя в долг.

    Берёт все DailyTaskItem пользователя из сетов с target_date < before_date,
    где user_answer IS NULL и debt_status IS NULL.
    """
    from sqlalchemy import and_

    old_set_ids = (
        db.session.query(DailyTaskSet.id)
        .filter(
            DailyTaskSet.user_id == user_id,
            DailyTaskSet.target_date < before_date,
        )
        .subquery()
    )

    items = (
        DailyTaskItem.query
        .filter(
            DailyTaskItem.daily_set_id.in_(db.session.query(old_set_ids.c.id)),
            DailyTaskItem.user_answer.is_(None),
            DailyTaskItem.debt_status.is_(None),
        )
        .all()
    )

    count = 0
    for item in items:
        parent = DailyTaskSet.query.get(item.daily_set_id)
        if not parent:
            continue
        item.debt_status = 'active'
        item.debt_until = parent.target_date + timedelta(days=DEBT_TTL_DAYS)
        count += 1

    if count:
        db.session.commit()
        logger.info(
            "daily_debt: user=%d migrated %d items to debt", user_id, count,
        )

    return count


def burn_stale_debt(user_id: int = None) -> int:
    """Пометить просроченный долг как 'burned'.

    Args:
        user_id: если указан — только для этого ученика, иначе для всех.
    """
    today = date.today()

    q = DailyTaskItem.query.filter(
        DailyTaskItem.debt_status == 'active',
        DailyTaskItem.debt_until < today,
    )
    if user_id is not None:
        q = q.filter(
            DailyTaskItem.daily_set_id.in_(
                db.session.query(DailyTaskSet.id).filter(
                    DailyTaskSet.user_id == user_id,
                )
            )
        )

    items = q.all()
    for item in items:
        item.debt_status = 'burned'

    if items:
        db.session.commit()
        logger.info(
            "daily_debt: burned %d stale debt items (user=%s)",
            len(items), user_id or 'ALL',
        )

    return len(items)


def refresh_debt_for_user(user_id: int) -> Dict[str, int]:
    """Полный цикл обновления долга для ученика:
    1) Миграция нерешённого в долг
    2) Сжигание просроченного

    Безопасен при повторном вызове.
    """
    today = date.today()
    migrated = migrate_to_debt(user_id, today)
    burned = burn_stale_debt(user_id)
    return {'migrated': migrated, 'burned': burned}


def get_debt_items(user_id: int) -> List[Dict[str, Any]]:
    """Получить активные долговые задачи для ученика.

    Возвращает список dict, сгруппированных по дате выдачи (свежие сверху).
    """
    today = date.today()

    # JOIN daily_task_sets для получения target_date
    items = (
        DailyTaskItem.query
        .join(DailyTaskSet, DailyTaskItem.daily_set_id == DailyTaskSet.id)
        .filter(
            DailyTaskSet.user_id == user_id,
            DailyTaskItem.debt_status == 'active',
        )
        .order_by(DailyTaskSet.target_date.desc(), DailyTaskItem.position)
        .all()
    )

    result = []
    for item in items:
        parent = DailyTaskSet.query.get(item.daily_set_id)
        days_left = None
        if item.debt_until:
            days_left = (item.debt_until - today).days

        result.append({
            'id': item.id,
            'position': item.position,
            'subject': item.subject,
            'topic': item.topic,
            'difficulty_level': item.difficulty_level,
            'task_text': item.task_text,
            'correct_answer': item.correct_answer,
            'solution': item.solution,
            'hints': item.hints,
            'issued_date': parent.target_date.isoformat() if parent else None,
            'debt_until': item.debt_until.isoformat() if item.debt_until else None,
            'days_left': days_left,
            'daily_set_id': item.daily_set_id,
            'slot_kind': item.slot_kind,
        })

    return result


def get_debt_count(user_id: int) -> int:
    """Количество активных долговых задач."""
    return DailyTaskItem.query.join(
        DailyTaskSet, DailyTaskItem.daily_set_id == DailyTaskSet.id
    ).filter(
        DailyTaskSet.user_id == user_id,
        DailyTaskItem.debt_status == 'active',
    ).count()
