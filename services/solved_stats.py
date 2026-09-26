# -*- coding: utf-8 -*-
"""
services/solved_stats.py — единый источник правды «сколько задач решено».

Счётчик users.total_problems_solved может дрейфовать от фактов в БД.
«Решено» означает верные задачи; «проверено» включает и неверные.
История повторных проверок некоторых задач не сохраняется, поэтому число
проверенных уникальных задач не следует называть числом всех проверок.

Решение: «решено» считается напрямую из фактических таблиц БД — тех же,
из которых начисляется рейтинг (experience_points):

  1. daily_task_items.is_correct   (задачи дня,    +5 XP за верный ответ)
  2. bank_issues.is_correct        (задачи банка,  +5 XP)
  3. insight practice tasks        (отработка неточностей, +5 XP)
  4. olympiad_task_attempts        (олимпиадные задачи,    +10 XP, статус 'solved')
  5. test_results_detail           (клиентские результаты тренажёра; XP нет)
  6. verified_problem_checks       (обычные задачи, +10 × сложность и бонус)

Рейтинг включает бонусы, но клиентские результаты тренажёра не дают XP.
Не выводить начисления или недоначисления только из соотношения XP и задач.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def task_counts_by_user(*, checked: bool = False, since=None) -> dict:
    """Count distinct recorded tasks by user, across the supported task sources.

    ``checked`` includes both correct and incorrect verdicts.  This is a
    count of recorded tasks, not of every resubmission: most source tables
    overwrite the previous answer.  ``since`` uses the stored UTC timestamps.
    """
    from models import db, BankIssue, TestResult, VerifiedProblemCheck
    from daily_tasks.models import DailyTaskItem, DailyTaskSet
    from models_insights import Insight, InsightPracticeTask
    from models_olympiad import TaskAttempt
    from sqlalchemy import func

    counts = {}

    def add(query):
        for user_id, count in query.all():
            if user_id is not None:
                counts[user_id] = counts.get(user_id, 0) + int(count or 0)

    daily = (db.session.query(DailyTaskSet.user_id, func.count(DailyTaskItem.id))
             .join(DailyTaskItem, DailyTaskItem.daily_set_id == DailyTaskSet.id)
             .filter(DailyTaskItem.is_correct.isnot(None) if checked
                     else DailyTaskItem.is_correct.is_(True)))
    if since is not None:
        daily = daily.filter(DailyTaskItem.answered_at >= since)
    add(daily.group_by(DailyTaskSet.user_id))

    bank = (db.session.query(BankIssue.user_id, func.count(BankIssue.id))
            .filter(BankIssue.is_correct.isnot(None) if checked
                    else BankIssue.is_correct.is_(True)))
    if since is not None:
        bank = bank.filter(BankIssue.answered_at >= since)
    add(bank.group_by(BankIssue.user_id))

    practice = (db.session.query(Insight.user_id, func.count(InsightPracticeTask.id))
                .join(InsightPracticeTask, InsightPracticeTask.insight_id == Insight.id)
                .filter(InsightPracticeTask.is_correct.isnot(None) if checked
                        else InsightPracticeTask.is_correct.is_(True)))
    if since is not None:
        # Incorrect practice answers do not store a checking timestamp.
        # Never substitute task creation time for the checking time.
        if not checked:
            practice = practice.filter(InsightPracticeTask.solved_at >= since)
        else:
            practice = None
    if practice is not None:
        add(practice.group_by(Insight.user_id))

    olympiad = (db.session.query(TaskAttempt.user_id, func.count(TaskAttempt.id))
                .filter(TaskAttempt.status.in_(('attempted', 'submitted', 'solved'))
                        if checked else TaskAttempt.status == 'solved'))
    if since is not None:
        olympiad = olympiad.filter(
            TaskAttempt.started_at >= since if checked
            else TaskAttempt.finished_at >= since)
    add(olympiad.group_by(TaskAttempt.user_id))

    # These records are synchronized from the client and do not represent
    # server-verified XP awards. They still count towards activity.
    results = (db.session.query(TestResult.user_id,
                                func.count(func.distinct(TestResult.task_id)))
               .filter(TestResult.test_type == 'practice')
               .filter(TestResult.task_id.isnot(None)))
    if not checked:
        results = results.filter(TestResult.is_correct.is_(True))
    if since is not None:
        results = results.filter(TestResult.created_at >= since)
    add(results.group_by(TestResult.user_id))

    regular = (db.session.query(VerifiedProblemCheck.user_id,
                                func.count(VerifiedProblemCheck.id))
               .filter(VerifiedProblemCheck.checked_at.isnot(None) if checked
                       else VerifiedProblemCheck.is_correct.is_(True)))
    if since is not None:
        regular = regular.filter(
            VerifiedProblemCheck.checked_at >= since if checked
            else VerifiedProblemCheck.solved_at >= since)
    add(regular.group_by(VerifiedProblemCheck.user_id))
    return counts


def solved_counts_by_user() -> dict:
    """Вернуть словарь {user_id: количество реально решённых задач}.

    Считает по фактическим таблицам БД (см. модульный docstring).
    Работает и на SQLite, и на PostgreSQL (ORM-запросы).
    Ошибка источника прерывает пересчёт: нельзя выдавать частичный итог
    за достоверный или перезаписывать им сохранённые счётчики.
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
        raise

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
        raise

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
        raise

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
        raise

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
        raise

    # Обычные задачи из /api/check_answer, одна строка на (user, problem).
    try:
        from models import VerifiedProblemCheck
        from sqlalchemy import func
        rows = (db.session.query(VerifiedProblemCheck.user_id,
                                 func.count(VerifiedProblemCheck.id))
                .filter(VerifiedProblemCheck.is_correct.is_(True))
                .group_by(VerifiedProblemCheck.user_id).all())
        _add(rows)
    except Exception as e:
        logger.warning('solved_counts_by_user: regular checks failed: %r', e)
        raise

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
