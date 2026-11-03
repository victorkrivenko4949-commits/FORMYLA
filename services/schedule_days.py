# -*- coding: utf-8 -*-
"""services/schedule_days.py — выбор дней занятий пилотного тарифа.

PILOT_SCHEDULE_DAYS_V1 (03.11.2026): после покупки пилотного тарифа
(premium_intense / premium_calm) ученик ОБЯЗАН выбрать дни занятий:
6 дней для «Работяги» и 3 дня для «Спокойного». Пока выбор не сделан,
before_request-гейт в app.py не выпускает его со страницы /schedule.

Хранение — отдельная таблица user_schedule_days (создаётся лениво,
CREATE TABLE IF NOT EXISTS, как в services/pilot.py). Дни недели —
числа 0..6 по Python (0=Пн … 6=Вс), сортированные, JSON-списком.

Никогда не бросает исключений наружу: все ошибки БД логируются и
гейт «падает открытой» (пользователь не запирается на странице).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger('formyla.schedule_days')

TABLE_NAME = 'user_schedule_days'

# Пилотные тарифы и сколько дней нужно выбрать
PILOT_SCHEDULE_REQUIRED = {
    'premium_intense': 6,   # «Работяга»
    'premium_calm': 3,      # «Спокойный»
}

WEEKDAY_LABELS = ['Понедельник', 'Вторник', 'Среда', 'Четверг',
                  'Пятница', 'Суббота', 'Воскресенье']
WEEKDAY_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']


def required_days_count(plan: str) -> Optional[int]:
    """Сколько дней нужно выбрать для тарифа. Не-пилотный → None."""
    return PILOT_SCHEDULE_REQUIRED.get(plan)


def _ensure_table() -> None:
    """Ленивое создание таблицы (идемпотентно, безопасно при гонке)."""
    try:
        from models import db
        from sqlalchemy import text
        db.session.execute(text(
            f"CREATE TABLE IF NOT EXISTS {TABLE_NAME} ("
            "  user_id INTEGER PRIMARY KEY,"
            "  days TEXT NOT NULL,"
            "  plan VARCHAR(40),"
            # CURRENT_TIMESTAMP работает и в Postgres, и в SQLite
            "  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"))
        db.session.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning('[schedule_days] ensure table failed: %r', e)
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass


def _valid_days(days) -> Optional[List[int]]:
    """Нормализация: список уникальных отсортированных чисел 0..6.

    Возвращает None, если вход не проходит валидацию (не числа,
    дубликаты, значения вне 0..6, пустой список).
    """
    if not isinstance(days, (list, tuple)):
        return None
    try:
        vals = [int(d) for d in days]
    except (TypeError, ValueError):
        return None
    if len(set(vals)) != len(vals):
        return None  # дубликаты
    if any(d < 0 or d > 6 for d in vals):
        return None
    if not vals:
        return None
    return sorted(vals)


def get_user_days(user_id: int) -> Optional[List[int]]:
    """Выбранные дни пользователя или None (выбора ещё не было)."""
    try:
        from models import db
        from sqlalchemy import text
        _ensure_table()
        row = db.session.execute(text(
            f"SELECT days FROM {TABLE_NAME} WHERE user_id = :uid LIMIT 1"),
            {'uid': int(user_id)}).fetchone()
        if not row or not row[0]:
            return None
        parsed = json.loads(row[0])
        return _valid_days(parsed)
    except Exception as e:  # noqa: BLE001
        logger.warning('[schedule_days] get failed: %r', e)
        return None


def save_user_days(user_id: int, days, plan: str = None) -> bool:
    """Сохранить выбор дней. Валидация: точное число дней под тариф.

    Тариф не из PILOT_SCHEDULE_REQUIRED → сохранение запрещено (False).
    Успех → True. Ошибки БД → False (пользователь увидит ошибку на
    странице и сможет повторить — гейт его не выпустит).
    """
    need = required_days_count(plan) if plan else None
    if need is None:
        return False  # выбор дней только для пилотных тарифов
    vals = _valid_days(days)
    if vals is None or len(vals) != need:
        return False
    try:
        from models import db
        from sqlalchemy import text
        _ensure_table()
        db.session.execute(text(
            f"INSERT INTO {TABLE_NAME} (user_id, days, plan, updated_at) "
            "VALUES (:uid, :days, :plan, CURRENT_TIMESTAMP) "
            f"ON CONFLICT (user_id) DO UPDATE SET "
            "  days = EXCLUDED.days, plan = EXCLUDED.plan, "
            "  updated_at = EXCLUDED.updated_at"),
            {'uid': int(user_id),
             'days': json.dumps(vals),
             'plan': str(plan)})
        db.session.commit()
        logger.info('[schedule_days] saved user=%s plan=%s days=%s',
                    user_id, plan, vals)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning('[schedule_days] save failed: %r', e)
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        return False


def days_for_plan(user_id: int, plan: str) -> Optional[List[int]]:
    """Выбранные дни, если их количество подходит под тариф.

    Если пользователь выбирал дни под другой тариф (например, был
    «Спокойный» — 3 дня, а стал «Работяга» — нужно 6), выбор считается
    устаревшим → None (гейт попросит выбрать заново).
    """
    need = required_days_count(plan)
    if need is None:
        return None
    days = get_user_days(user_id)
    if days is None or len(days) != need:
        return None
    return days
