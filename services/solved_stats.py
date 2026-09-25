# -*- coding: utf-8 -*-
"""
services/solved_stats.py — единый источник правды «сколько задач решено».

SOLVED_STATS_V1 (25.09.2026): счётчик users.total_problems_solved дрейфовал
от реальности (часть путей решения не писала факты в БД, часть — не начисляла
счётчик). Из-за этого в админ-статистике (аккаунт Lavrik / 67лавриксемен67)
число «решено» не соответствовало рейтингу.

Решение: «решено» считается напрямую из фактических таблиц БД — тех же,
из которых начисляется рейтинг (experience_points):

  1. daily_task_items.is_correct   (задачи дня,    +5 XP за верный ответ)
  2. bank_issues.is_correct        (задачи банка,  +5 XP)
  3. insight practice tasks        (отработка неточностей, +5 XP)
  4. olympiad_task_attempts        (олимпиадные задачи,    +10 XP, статус 'solved')

Рейтинг также включает НЕ-задачные бонусы (анкета +20, друзья +10,
бонус за закрытую неточность +15 и т.п.), поэтому rating >= 5*решено —
это нормально; а вот «решено» теперь всегда точное.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def solved_counts_by_user() -> dict:
    """Вернуть словарь {user_id: количество реально решённых задач}.

    Считает по фактическим таблицам БД (см. модульный docstring).
    Работает и на SQLite, и на PostgreSQL (ORM-запросы).
    Любая ошибка в отдельном источнике не валит остальные.
    """
    counts: dict = {}

    def _add(rows):
        for user_id, cnt in rows:
            if user_id is None:
                continue
            try:
                cnt = int(cnt or 0)
            except (TypeError, ValueError):
                cnt = 0
            counts[user_id] = counts.get(user_id, 0) + cnt

    from models import db

    # 1. Задачи дня (daily_task_items -> daily_task_sets.user_id)
    try:
        from daily_tasks.models import DailyTaskItem, DailyTaskSet
        from sqlalchemy import func
        rows = (db.session.query(DailyTaskSet.user_id, func.count(DailyTaskItem.id))
                .join(DailyTaskItem, DailyTaskItem.daily_set_id == DailyTaskSet.id)
                .filter(DailyTaskItem.is_correct.is_(True))
                .group_by(DailyTaskSet.user_id)
                .all())
        _add(rows)
    except Exception as e:
        logger.warning('solved_counts_by_user: daily_task_items skipped: %r', e)

    # 2. Задачи банка (bank_issues)
    try:
        from models import BankIssue
        from sqlalchemy import func
        rows = (db.session.query(BankIssue.user_id, func.count(BankIssue.id))
                .filter(BankIssue.is_correct.is_(True))
                .group_by(BankIssue.user_id)
                .all())
        _add(rows)
    except Exception as e:
        logger.warning('solved_counts_by_user: bank_issues skipped: %r', e)

    # 3. Отработка неточностей (InsightPracticeTask -> Insight.user_id)
    try:
        from models_insights import Insight, InsightPracticeTask
        from sqlalchemy import func
        rows = (db.session.query(Insight.user_id, func.count(InsightPracticeTask.id))
                .join(InsightPracticeTask, InsightPracticeTask.insight_id == Insight.id)
                .filter(InsightPracticeTask.is_correct.is_(True))
                .group_by(Insight.user_id)
                .all())
        _add(rows)
    except Exception as e:
        logger.warning('solved_counts_by_user: insight practice tasks skipped: %r', e)

    # 4. Олимпиадные задачи (TaskAttempt status='solved'; уникальность
    #    (user_id, task_id) гарантируется констрейнтом uq_user_task)
    try:
        from models_olympiad import TaskAttempt
        from sqlalchemy import func
        rows = (db.session.query(TaskAttempt.user_id, func.count(TaskAttempt.id))
                .filter(TaskAttempt.status == 'solved')
                .group_by(TaskAttempt.user_id)
                .all())
        _add(rows)
    except Exception as e:
        logger.warning('solved_counts_by_user: olympiad task_attempts skipped: %r', e)

    # 5. Разделы-тренажёры (/section/...): факты пишет /api/save_test_result
    #    в TestResult (test_type='practice'). Считаем DISTINCT task_id, чтобы
    #    повторные решения одной задачи не задваивались. Если строк нет —
    #    источник просто ничего не добавляет.
    try:
        from models import TestResult
        from sqlalchemy import func
        rows = (db.session.query(TestResult.user_id, func.count(func.distinct(TestResult.task_id)))
                .filter(TestResult.is_correct.is_(True))
                .filter(TestResult.test_type == 'practice')
                .filter(TestResult.task_id.isnot(None))
                .group_by(TestResult.user_id)
                .all())
        _add(rows)
    except Exception as e:
        logger.warning('solved_counts_by_user: practice TestResult skipped: %r', e)

    return counts


def award_missing_olympiad_xp() -> set:
    """Доначислить +10 XP и +1 решённую за уже решённые олимпиадные задачи.

    Backfill для XP_AWARD_V1: до 25.09.2026 решённые олимпиадные задачи
    не получали ни рейтинга, ни счётчика. Запускать можно многократно —
    флаг xp_awarded исключает двойное начисление.

    Возвращает набор user_id, которым было доначислено.
    """
    from models import db, User
    from models_olympiad import TaskAttempt

    credited: set = set()
    try:
        attempts = (TaskAttempt.query
                    .filter(TaskAttempt.status == 'solved')
                    .filter(TaskAttempt.xp_awarded.is_(False) |
                            TaskAttempt.xp_awarded.is_(None))
                    .all())
        for at in attempts:
            u = db.session.get(User, at.user_id)
            if u is None:
                continue
            u.experience_points = (u.experience_points or 0) + 10
            u.total_problems_solved = (u.total_problems_solved or 0) + 1
            at.xp_awarded = True
            credited.add(at.user_id)
        if credited:
            db.session.commit()
            logger.info('[XP-OLYMPIAD-BACKFILL] доначислено пользователям: %s',
                        sorted(credited))
    except Exception as e:
        db.session.rollback()
        logger.warning('[XP-OLYMPIAD-BACKFILL] skipped: %r', e)
    return credited


def recount_all_users_solved() -> int:
    """Синхронизировать users.total_problems_solved с фактическими данными.

    Возвращает число пользователей, у которых счётчик был исправлен.
    Запускать можно многократно (идемпотентно).
    """
    from models import db, User

    fixed = 0
    try:
        counts = solved_counts_by_user()
        users = User.query.all()
        for u in users:
            fact = counts.get(u.id, 0)
            if (u.total_problems_solved or 0) != fact:
                u.total_problems_solved = fact
                fixed += 1
        if fixed:
            db.session.commit()
            logger.info('[SOLVED-RECONCILE] исправлен счётчик «решено» '
                       'у %d пользователей', fixed)
    except Exception as e:
        db.session.rollback()
        logger.warning('[SOLVED-RECONCILE] skipped: %r', e)
    return fixed
