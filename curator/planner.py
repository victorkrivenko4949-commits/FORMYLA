# -*- coding: utf-8 -*-
"""
planner.py — Модуль построения персонального учебного плана (roadmap).

Алгоритм:
  1. На основе диагностики (StudentDiagnostic) определяем слабые и сильные темы.
  2. Приоритизируем слабые темы, но поддерживаем сильные.
  3. Разбиваем подготовку по неделям до даты целевой олимпиады.
  4. Используем обратное планирование (от дедлайна).
  5. Поддерживаем пересчёт плана при изменении прогресса.
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple

from models import db
from curator.models import StudentDiagnostic, LearningPlan, CuratorTaskAttempt, ProgressLog
from curator.config import (
    MIN_PLAN_DAYS, MAX_PLAN_DAYS, DEFAULT_DAILY_TASKS, DAYS_IN_WEEK,
    WEAK_TOPIC_WEIGHT, MEDIUM_TOPIC_WEIGHT, STRONG_TOPIC_WEIGHT,
    STRONG_THRESHOLD, WEAK_THRESHOLD,
    TOPIC_LABELS_RU,
)

logger = logging.getLogger(__name__)


# ─── Публичные функции ────────────────────────────────────────────────────────

def create_plan_from_diagnostic(
    user_id: int,
    diagnostic_id: int,
    target_olympiad: str = None,
    target_stage: str = None,
    target_date: date = None,
    daily_tasks_count: int = DEFAULT_DAILY_TASKS,
    title: str = None,
) -> Optional[LearningPlan]:
    """Создать учебный план на основе результатов диагностики.

    Args:
        user_id: ID пользователя.
        diagnostic_id: ID сессии диагностики.
        target_olympiad: Название целевой олимпиады.
        target_stage: Этап (школьный, муниципальный и т.д.).
        target_date: Дата олимпиады.
        daily_tasks_count: Количество задач в день.
        title: Название плана.

    Returns:
        LearningPlan — созданный план, или None при ошибке.
    """
    diagnostic = db.session.get(StudentDiagnostic, diagnostic_id)
    if not diagnostic or diagnostic.status != 'completed':
        logger.warning(f"[planner] Diagnostic #{diagnostic_id} not found or not completed")
        return None

    profile = diagnostic.profile
    if not profile:
        logger.warning(f"[planner] Diagnostic #{diagnostic_id} has no profile")
        return None

    today = date.today()

    # Если дата не указана, ставим дефолтную (через 3 месяца)
    if not target_date:
        target_date = today + timedelta(days=90)

    days_total = _calculate_days_total(today, target_date)
    if days_total < MIN_PLAN_DAYS:
        days_total = MIN_PLAN_DAYS
        target_date = today + timedelta(days=days_total)
    if days_total > MAX_PLAN_DAYS:
        days_total = MAX_PLAN_DAYS

    # Определяем приоритеты тем (от слабой к сильной)
    topic_priorities = _get_topic_priorities(profile)
    total_weeks = max(1, days_total // DAYS_IN_WEEK)

    # Строим roadmap по неделям
    roadmap = _build_roadmap(profile, topic_priorities, total_weeks)

    plan_title = title or f'Подготовка к {target_olympiad or "олимпиаде"}'

    plan = LearningPlan(
        user_id=user_id,
        title=plan_title,
        goal=_build_plan_goal(diagnostic, target_olympiad, target_stage),
        plan_type='diagnostic',
        baseline_profile=json.dumps(profile, ensure_ascii=False),
        start_date=today,
        target_date=target_date,
        target_olympiad=target_olympiad or '',
        target_stage=target_stage or '',
        status='active',
        roadmap_json=json.dumps(roadmap, ensure_ascii=False),
        current_profile=json.dumps(profile, ensure_ascii=False),
        total_weeks=total_weeks,
        current_week=1,
        topic_priorities=json.dumps(topic_priorities, ensure_ascii=False),
    )
    db.session.add(plan)
    db.session.flush()

    # Создаём первый ProgressLog
    _create_initial_progress_log(user_id, plan.id, profile)

    db.session.commit()
    logger.info(f"[planner] Plan #{plan.id} created for user={user_id}, "
                f"{total_weeks} weeks, target={target_date}")
    return plan


def get_plan(plan_id: int) -> Optional[dict]:
    """Получить детали плана.

    Args:
        plan_id: ID плана.

    Returns:
        dict с деталями плана или None.
    """
    plan = db.session.get(LearningPlan, plan_id)
    if not plan:
        return None

    roadmap = plan.roadmap or []
    current_profile = plan.current_profile_dict or {}

    return {
        'id': plan.id,
        'user_id': plan.user_id,
        'title': plan.title,
        'goal': plan.goal,
        'plan_type': plan.plan_type,
        'status': plan.status,
        'start_date': plan.start_date.isoformat() if plan.start_date else None,
        'target_date': plan.target_date.isoformat() if plan.target_date else None,
        'target_olympiad': plan.target_olympiad,
        'target_stage': plan.target_stage,
        'total_weeks': plan.total_weeks,
        'current_week': plan.current_week,
        'days_remaining': plan.days_until_target,
        'topic_priorities': plan.topic_priorities_list,
        'current_profile': current_profile,
        'roadmap': roadmap,
        'topics': [
            {
                'key': topic,
                'label': TOPIC_LABELS_RU.get(topic, topic),
                'pct': current_profile.get(topic, {}).get('pct', 0),
                'level': current_profile.get(topic, {}).get('level', 0),
            }
            for topic in ['algebra', 'geometry', 'combinatorics', 'number_theory', 'logic']
        ],
        'created_at': plan.created_at.isoformat() if plan.created_at else None,
        'updated_at': plan.updated_at.isoformat() if plan.updated_at else None,
    }


def recompute_plan(plan_id: int) -> Optional[LearningPlan]:
    """Пересчитать план на основе текущего прогресса.

    Обновляет roadmap для оставшихся недель с учётом нового профиля.

    Args:
        plan_id: ID плана.

    Returns:
        LearningPlan — обновлённый план, или None.
    """
    plan = db.session.get(LearningPlan, plan_id)
    if not plan or plan.status != 'active':
        return None

    # Получаем текущий профиль из последнего ProgressLog
    latest_log = (
        ProgressLog.query
        .filter_by(plan_id=plan_id, user_id=plan.user_id)
        .order_by(ProgressLog.log_date.desc())
        .first()
    )

    if latest_log and latest_log.profile_snapshot:
        current_profile = latest_log.profile_snapshot_dict
    else:
        current_profile = plan.current_profile_dict

    if not current_profile:
        return None

    # Обновляем приоритеты
    topic_priorities = _get_topic_priorities(current_profile)
    plan.topic_priorities_list = topic_priorities

    # Перестраиваем roadmap для оставшихся недель
    remaining_weeks = plan.total_weeks - (plan.current_week - 1)
    if remaining_weeks > 0:
        new_roadmap = _build_roadmap(
            current_profile,
            topic_priorities,
            remaining_weeks,
            start_week=plan.current_week,
        )
        # Сохраняем已完成ные недели
        old_roadmap = plan.roadmap or []
        completed_weeks = [w for w in old_roadmap if w.get('week', 0) < plan.current_week]
        plan.roadmap = completed_weeks + new_roadmap

    plan.current_profile_dict = current_profile
    plan.updated_at = datetime.utcnow()
    db.session.commit()

    logger.info(f"[planner] Plan #{plan_id} recomputed, "
                f"remaining weeks: {remaining_weeks}")
    return plan


def advance_week(plan_id: int) -> bool:
    """Перейти к следующей неделе плана.

    Args:
        plan_id: ID плана.

    Returns:
        True если успешно.
    """
    plan = db.session.get(LearningPlan, plan_id)
    if not plan or plan.status != 'active':
        return False

    if plan.current_week < plan.total_weeks:
        plan.current_week += 1
        plan.updated_at = datetime.utcnow()
        db.session.commit()
        logger.info(f"[planner] Plan #{plan_id} advanced to week {plan.current_week}")
        return True
    else:
        # План завершён
        plan.status = 'completed'
        plan.updated_at = datetime.utcnow()
        db.session.commit()
        logger.info(f"[planner] Plan #{plan_id} completed")
        return True


def pause_plan(plan_id: int) -> bool:
    """Поставить план на паузу."""
    plan = db.session.get(LearningPlan, plan_id)
    if not plan:
        return False
    plan.status = 'paused'
    plan.updated_at = datetime.utcnow()
    db.session.commit()
    return True


def resume_plan(plan_id: int) -> bool:
    """Возобновить план."""
    plan = db.session.get(LearningPlan, plan_id)
    if not plan:
        return False
    plan.status = 'active'
    plan.updated_at = datetime.utcnow()
    db.session.commit()
    return True


def get_tasks_for_week(plan_id: int, week: int = None) -> Optional[dict]:
    """Получить задачи для указанной (или текущей) недели плана.

    Args:
        plan_id: ID плана.
        week: Номер недели (1-based). Если None — текущая.

    Returns:
        dict с задачами недели или None.
    """
    plan = db.session.get(LearningPlan, plan_id)
    if not plan:
        return None

    if week is None:
        week = plan.current_week

    roadmap = plan.roadmap
    week_data = next((w for w in roadmap if w.get('week') == week), None)

    if not week_data:
        return None

    # Получаем задачи по темам из TaskBank
    tasks = _fetch_tasks_for_week(plan.user_id, week_data, plan.start_date, week)
    profile = plan.current_profile_dict or {}

    return {
        'plan_id': plan.id,
        'week': week,
        'total_weeks': plan.total_weeks,
        'topics': week_data.get('topics', []),
        'focus': week_data.get('focus', ''),
        'goal': week_data.get('goal', ''),
        'tasks_count': len(tasks),
        'tasks': tasks,
        'current_profile': [
            {
                'key': t,
                'label': TOPIC_LABELS_RU.get(t, t),
                'pct': profile.get(t, {}).get('pct', 0),
            }
            for t in week_data.get('topics', [])
        ],
    }


# ─── Внутренние функции ──────────────────────────────────────────────────────

def _calculate_days_total(start: date, end: date) -> int:
    """Количество дней между датами."""
    delta = end - start
    return max(MIN_PLAN_DAYS, delta.days)


def _get_topic_priorities(profile: dict) -> List[str]:
    """Определить приоритеты тем (от самой слабой к сильной)."""
    scored = []
    for topic, data in profile.items():
        pct = data.get('pct', 0) if isinstance(data, dict) else 0
        scored.append((topic, pct))

    # Сортируем по возрастанию процента (слабые → сильные)
    scored.sort(key=lambda x: x[1])
    return [s[0] for s in scored]


def _classify_topic(pct: float) -> str:
    """Классифицировать тему по уровню."""
    if pct >= STRONG_THRESHOLD:
        return 'strong'
    elif pct >= WEAK_THRESHOLD:
        return 'medium'
    return 'weak'


def _build_roadmap(
    profile: dict,
    priorities: List[str],
    total_weeks: int,
    start_week: int = 1,
) -> List[dict]:
    """Построить понедельный roadmap.

    Первые недели: фокус на слабых темах.
    Средние недели: баланс слабых и средних.
    Последние недели: повторение всех тем + сильные для поддержки.
    """
    roadmap = []
    classified = {t: _classify_topic(profile.get(t, {}).get('pct', 0)) for t in priorities}
    weak_topics = [t for t in priorities if classified.get(t) == 'weak']
    medium_topics = [t for t in priorities if classified.get(t) == 'medium']
    strong_topics = [t for t in priorities if classified.get(t) == 'strong']

    # Если нет слабых, все темы medium/strong
    if not weak_topics:
        weak_topics = priorities[:2] if len(priorities) >= 2 else priorities
        medium_topics = [t for t in priorities if t not in weak_topics]

    for week_num in range(total_weeks):
        week = start_week + week_num
        progress_ratio = week_num / max(total_weeks, 1)

        if progress_ratio < 0.3:
            # Фаза 1: фокус на слабых темах (первые 30% времени)
            focus = 'weakest'
            topics = weak_topics[:2]  # 1-2 слабые темы
            if len(weak_topics) > 2:
                # Циклически перебираем слабые темы
                idx = week_num % len(weak_topics)
                topics = [weak_topics[idx]]
                if idx + 1 < len(weak_topics):
                    topics.append(weak_topics[(idx + 1) % len(weak_topics)])
            elif not topics:
                topics = priorities[:2]
            goal = f'Укрепление слабых тем: {_format_topics(topics)}'
        elif progress_ratio < 0.7:
            # Фаза 2: баланс (30-70% времени)
            focus = 'balanced'
            # 1 слабая + 1 средняя + иногда 1 сильная
            topics = []
            if weak_topics:
                topics.append(weak_topics[week_num % len(weak_topics)])
            if medium_topics:
                topics.append(medium_topics[week_num % len(medium_topics)])
            if week_num % 2 == 0 and strong_topics:
                topics.append(strong_topics[week_num % len(strong_topics)])
            goal = f'Комплексная подготовка: {_format_topics(topics)}'
        else:
            # Фаза 3: повторение всех тем (последние 30%)
            focus = 'review'
            # Циклически по всем темам
            topics = []
            for i in range(2):
                idx = (week_num + i) % len(priorities)
                topics.append(priorities[idx])
            goal = f'Повторение и закрепление: {_format_topics(topics)}'

        roadmap.append({
            'week': week,
            'topics': list(set(topics)),
            'focus': focus,
            'goal': goal,
            'tasks_count': DEFAULT_DAILY_TASKS,
        })

    return roadmap


def _build_plan_goal(diagnostic: StudentDiagnostic, olympiad: str, stage: str) -> str:
    """Сформировать текстовую цель плана."""
    overall = diagnostic.overall_pct or 0
    profile = diagnostic.profile
    weak_topics = [
        TOPIC_LABELS_RU.get(t, t)
        for t, d in profile.items()
        if isinstance(d, dict) and d.get('pct', 0) < 40
    ]

    goal_parts = [f'Текущий уровень: {overall}%.']
    if weak_topics:
        goal_parts.append(f'Уделить внимание: {", ".join(weak_topics[:3])}.')
    if olympiad:
        goal_parts.append(f'Цель: подготовка к {olympiad}')
        if stage:
            goal_parts.append(f'({stage} этап).')
        else:
            goal_parts.append('.')
    else:
        goal_parts.append('Цель: повышение общего уровня олимпиадной подготовки.')

    return ' '.join(goal_parts)


def _format_topics(topics: List[str]) -> str:
    """Форматировать список тем для отображения."""
    labels = [TOPIC_LABELS_RU.get(t, t) for t in topics]
    return ', '.join(labels)


def _fetch_tasks_for_week(
    user_id: int,
    week_data: dict,
    plan_start: date,
    week: int,
) -> List[dict]:
    """Выбрать задачи для недели из банка TaskBank."""
    from curator.task_bank import TaskBank

    topics = week_data.get('topics', [])
    tasks_count = week_data.get('tasks_count', DEFAULT_DAILY_TASKS)

    if not topics:
        return []

    # Получаем уже решённые задачи пользователя
    solved_task_ids = set()
    attempts = CuratorTaskAttempt.query.filter_by(user_id=user_id).all()
    for a in attempts:
        if a.task_id:
            solved_task_ids.add(a.task_id)

    tasks = []
    topics_cycle = topics * (tasks_count // len(topics) + 1)

    for i, topic in enumerate(topics_cycle[:tasks_count]):
        # Определяем уровень сложности на основе недели
        difficulty = min(3 + week // 2, 10)  # TaskBank difficulty 1-10

        task = (
            TaskBank.query
            .filter_by(topic=topic, difficulty=difficulty)
            .filter(~TaskBank.id.in_(solved_task_ids) if solved_task_ids else True)
            .order_by(db.func.random())
            .first()
        )

        if not task:
            # Fallback: любой уровень
            task = (
                TaskBank.query
                .filter_by(topic=topic)
                .filter(~TaskBank.id.in_(solved_task_ids) if solved_task_ids else True)
                .order_by(db.func.random())
                .first()
            )

        if task:
            tasks.append({
                'task_id': task.id,
                'topic': topic,
                'topic_label': TOPIC_LABELS_RU.get(topic, topic),
                'difficulty': task.difficulty or difficulty,
                'question_text': task.statement,
                'correct_answer': task.answer,
                'solution': task.solution,
            })

    return tasks


def _create_initial_progress_log(user_id: int, plan_id: int, profile: dict):
    """Создать начальную запись прогресса."""
    log = ProgressLog(
        user_id=user_id,
        plan_id=plan_id,
        log_date=date.today(),
        log_type='weekly',
        profile_snapshot=json.dumps(profile, ensure_ascii=False),
        tasks_solved=0,
        tasks_total=0,
        accuracy_pct=0.0,
        minutes_spent=0.0,
        streak_days=0,
        max_streak=0,
        plan_week=1,
    )
    db.session.add(log)
