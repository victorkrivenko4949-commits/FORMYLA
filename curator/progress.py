# -*- coding: utf-8 -*-
"""
progress.py — Модуль отслеживания прогресса и мотивации.

Функции:
  - Ежедневные/еженедельные срезы профиля (ProgressLog)
  - Расчёт серий (streaks) и максимальных серий
  - Выявление "застреваний" (3+ дня без прогресса)
  - AI-советы и мотивационные сообщения
  - Обновление профиля после каждой попытки решения задачи
"""

import json
import logging
import random
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Tuple

from models import db
from curator.models import CuratorTaskAttempt, ProgressLog, LearningPlan, StudentDiagnostic

logger = logging.getLogger(__name__)

# ─── Константы ────────────────────────────────────────────────────────────────

# Порог "застревания": дней без прогресса
STUCK_DAYS_THRESHOLD = 3

# Типы логов
LOG_TYPE_DAILY = 'daily'
LOG_TYPE_WEEKLY = 'weekly'
LOG_TYPE_SESSION = 'session'

# AI-модель для советов
ADVICE_MODEL = "deepseek/deepseek-chat"


# ─── Публичные функции ────────────────────────────────────────────────────────


def create_or_update_daily_log(
    user_id: int,
    plan_id: int = None,
    tasks_solved: int = 0,
    tasks_total: int = 0,
    minutes_spent: float = 0.0,
    log_type: str = LOG_TYPE_DAILY,
) -> ProgressLog:
    """Создать или обновить ежедневную запись прогресса.

    Если запись за сегодня уже существует — обновляет счётчики.
    Иначе создаёт новую.

    Args:
        user_id: ID пользователя.
        plan_id: ID плана.
        tasks_solved: Количество решённых задач.
        tasks_total: Общее количество задач.
        minutes_spent: Потраченное время (минуты).
        log_type: Тип лога (daily, weekly, session).

    Returns:
        ProgressLog — созданная/обновлённая запись.
    """
    today = date.today()

    # Ищем существующую запись за сегодня
    existing = (
        ProgressLog.query
        .filter_by(user_id=user_id, log_date=today, log_type=log_type)
        .first()
    )

    if existing:
        # Обновляем существующую
        existing.tasks_solved += tasks_solved
        existing.tasks_total += tasks_total
        if existing.tasks_total > 0:
            existing.accuracy_pct = round(
                (existing.tasks_solved / existing.tasks_total) * 100, 1
            )
        if minutes_spent:
            existing.minutes_spent = (existing.minutes_spent or 0) + minutes_spent

        # Обновляем профиль, если передан plan_id
        if plan_id:
            profile = _get_current_profile(user_id, plan_id)
            if profile:
                existing.profile_snapshot = json.dumps(profile, ensure_ascii=False)

        # Пересчитываем streak
        existing.streak_days = _recalc_streak(user_id)
        existing.max_streak = max(existing.max_streak or 0, existing.streak_days)

        # Проверка на stuck
        existing.is_stuck = _detect_stuck_internal(user_id, plan_id)

        db.session.commit()
        logger.debug(f"[progress] Updated daily log #{existing.id} for user={user_id}")
        return existing

    # Создаём новую запись
    streak_days = _recalc_streak(user_id)
    max_streak = _get_max_streak(user_id)
    profile = _get_current_profile(user_id, plan_id) if plan_id else {}

    # Определяем текущую неделю плана
    plan_week = None
    if plan_id:
        plan = db.session.get(LearningPlan, plan_id)
        if plan:
            plan_week = plan.current_week

    log_entry = ProgressLog(
        user_id=user_id,
        plan_id=plan_id,
        log_date=today,
        log_type=log_type,
        profile_snapshot=json.dumps(profile, ensure_ascii=False) if profile else None,
        tasks_solved=tasks_solved,
        tasks_total=tasks_total,
        accuracy_pct=round((tasks_solved / max(tasks_total, 1)) * 100, 1) if tasks_total > 0 else None,
        minutes_spent=minutes_spent or 0.0,
        streak_days=streak_days,
        max_streak=max(streak_days, max_streak),
        plan_week=plan_week,
        is_stuck=_detect_stuck_internal(user_id, plan_id),
    )
    db.session.add(log_entry)
    db.session.flush()
    db.session.commit()

    logger.info(f"[progress] Created daily log #{log_entry.id} for user={user_id}, "
                f"streak={streak_days}, solved={tasks_solved}/{tasks_total}")
    return log_entry


def get_streak(user_id: int) -> Dict:
    """Получить информацию о текущей серии (streak).

    Args:
        user_id: ID пользователя.

    Returns:
        dict: {current_streak, max_streak, last_active_date, is_active_today}
    """
    max_streak = _get_max_streak(user_id)

    # Находим последнюю запись прогресса
    last_log = (
        ProgressLog.query
        .filter_by(user_id=user_id)
        .order_by(ProgressLog.log_date.desc())
        .first()
    )

    today = date.today()
    current_streak = _recalc_streak(user_id)
    last_active = last_log.log_date if last_log else None
    is_active_today = last_active == today if last_active else False

    return {
        'current_streak': current_streak,
        'max_streak': max_streak,
        'last_active_date': last_active.isoformat() if last_active else None,
        'is_active_today': is_active_today,
    }


def detect_stuck(user_id: int, plan_id: int = None) -> Dict:
    """Проверить, "застрял" ли ученик.

    Застревание = 3+ дня без прогресса при активном плане.

    Args:
        user_id: ID пользователя.
        plan_id: ID плана (опционально).

    Returns:
        dict: {is_stuck, days_since_progress, stuck_since, advice}
    """
    is_stuck, days_since = _check_stuck(user_id, plan_id)

    # Последняя дата прогресса
    last_log = (
        ProgressLog.query
        .filter_by(user_id=user_id)
        .order_by(ProgressLog.log_date.desc())
        .first()
    )
    last_active = last_log.log_date if last_log else None

    # Генерируем совет если stuck
    advice = None
    if is_stuck:
        advice = _generate_stuck_advice(user_id, days_since)

    return {
        'is_stuck': is_stuck,
        'days_since_progress': days_since,
        'stuck_since': (date.today() - timedelta(days=days_since)).isoformat() if days_since > 0 else None,
        'last_active_date': last_active.isoformat() if last_active else None,
        'advice': advice,
    }


def update_profile_after_attempt(
    attempt: CuratorTaskAttempt,
    plan_id: int = None,
) -> Optional[ProgressLog]:
    """Обновить профиль прогресса после попытки решения задачи.

    Вызывается из review_solution() в tutor.py после каждой попытки.
    Обновляет дневной лог и инициирует проверку статуса.

    Args:
        attempt: Объект CuratorTaskAttempt.
        plan_id: ID плана (если задача из плана).

    Returns:
        ProgressLog — обновлённый дневной лог.
    """
    is_correct = 1 if attempt.is_correct else 0

    log_entry = create_or_update_daily_log(
        user_id=attempt.user_id,
        plan_id=plan_id or attempt.plan_id,
        tasks_solved=is_correct,
        tasks_total=1,
        minutes_spent=(attempt.time_spent_sec or 0) / 60.0,
        log_type=LOG_TYPE_DAILY,
    )

    # Если есть план, обновляем профиль в плане
    target_plan_id = plan_id or attempt.plan_id
    if target_plan_id:
        _sync_plan_profile(target_plan_id)

    return log_entry


def get_progress_summary(
    user_id: int,
    plan_id: int = None,
    days: int = 30,
) -> Dict:
    """Получить сводку прогресса за период.

    Args:
        user_id: ID пользователя.
        plan_id: ID плана (опционально).
        days: Количество дней для анализа.

    Returns:
        dict со сводкой прогресса.
    """
    since = date.today() - timedelta(days=days)

    query = ProgressLog.query.filter(
        ProgressLog.user_id == user_id,
        ProgressLog.log_date >= since,
    )
    if plan_id:
        query = query.filter(ProgressLog.plan_id == plan_id)

    logs = query.order_by(ProgressLog.log_date.asc()).all()

    if not logs:
        return {
            'total_days': 0,
            'total_tasks_solved': 0,
            'total_tasks_attempted': 0,
            'overall_accuracy': 0.0,
            'total_minutes_spent': 0.0,
            'streak': get_streak(user_id),
            'daily_breakdown': [],
        }

    total_solved = sum(l.tasks_solved for l in logs)
    total_attempted = sum(l.tasks_total for l in logs)
    total_minutes = sum(l.minutes_spent or 0 for l in logs)
    avg_accuracy = (
        round((total_solved / max(total_attempted, 1)) * 100, 1)
        if total_attempted > 0
        else 0.0
    )

    # Профиль на последний день
    latest_profile = logs[-1].profile_snapshot_dict if logs[-1].profile_snapshot else {}

    # Ежедневная разбивка
    daily_breakdown = [
        {
            'date': l.log_date.isoformat(),
            'solved': l.tasks_solved,
            'total': l.tasks_total,
            'accuracy': l.accuracy_pct,
            'minutes': l.minutes_spent,
            'streak': l.streak_days,
            'is_stuck': l.is_stuck,
        }
        for l in logs
    ]

    return {
        'total_days': len(logs),
        'total_tasks_solved': total_solved,
        'total_tasks_attempted': total_attempted,
        'overall_accuracy': avg_accuracy,
        'total_minutes_spent': round(total_minutes, 1),
        'current_profile': {
            topic: data.get('pct', 0)
            for topic, data in latest_profile.items()
            if isinstance(data, dict)
        },
        'streak': get_streak(user_id),
        'stuck_status': detect_stuck(user_id, plan_id),
        'daily_breakdown': daily_breakdown,
    }


def generate_ai_advice(user_id: int, plan_id: int = None) -> str:
    """Сгенерировать AI-совет на основе текущего прогресса.

    Args:
        user_id: ID пользователя.
        plan_id: ID плана.

    Returns:
        str — совет на русском языке.
    """
    summary = get_progress_summary(user_id, plan_id, days=7)

    # Если за последние 7 дней нет активности
    if summary['total_days'] == 0:
        return _get_motivation_restart_message(user_id)

    streak_info = get_streak(user_id)
    stuck_info = detect_stuck(user_id, plan_id)

    profile = summary.get('current_profile', {})
    profile_str = ', '.join(
        f'{topic}: {pct}%' for topic, pct in profile.items()
    ) if profile else 'нет данных'

    prompt = (
        f"Прогресс ученика за последние 7 дней:\n"
        f"  - Решено задач: {summary['total_tasks_solved']}/{summary['total_tasks_attempted']}\n"
        f"  - Точность: {summary['overall_accuracy']}%\n"
        f"  - Потрачено времени: {summary['total_minutes_spent']} мин\n"
        f"  - Текущая серия: {streak_info['current_streak']} дней\n"
        f"  - Максимальная серия: {streak_info['max_streak']} дней\n"
        f"  - Профиль: {profile_str}\n"
    )

    if stuck_info['is_stuck']:
        prompt += (
            f"  - Проблема: ученик застрял (нет прогресса {stuck_info['days_since_progress']} дней)\n"
        )

    try:
        from services.openrouter_client import openrouter

        response = openrouter.chat(
            model=ADVICE_MODEL,
            messages=[
                {'role': 'system', 'content': _ADVICE_SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.7,
            max_tokens=300,
        )
        advice = response.get('content', '').strip()
        if advice:
            # Сохраняем совет в последнем логе
            _save_advice_to_log(user_id, plan_id, advice)
            return advice
    except Exception as e:
        logger.error(f"[progress] AI advice failed: {e}")

    # Fallback советы
    fallback = _get_fallback_advice(summary, streak_info, stuck_info)
    _save_advice_to_log(user_id, plan_id, fallback)
    return fallback


def get_weekly_report(user_id: int, plan_id: int = None) -> Dict:
    """Сформировать еженедельный отчёт.

    Args:
        user_id: ID пользователя.
        plan_id: ID плана.

    Returns:
        dict с отчётом за неделю.
    """
    summary = get_progress_summary(user_id, plan_id, days=7)

    # Сравнение с предыдущей неделей
    prev_summary = get_progress_summary(user_id, plan_id, days=14)
    prev_solved = prev_summary['total_tasks_solved'] - summary['total_tasks_solved']
    prev_accuracy = prev_summary['overall_accuracy']

    solved_change = summary['total_tasks_solved'] - max(prev_solved, 0)
    accuracy_change = round(summary['overall_accuracy'] - prev_accuracy, 1)

    # Тренд
    if solved_change > 0 and accuracy_change >= 0:
        trend = 'improving'
    elif solved_change < 0 and accuracy_change < 0:
        trend = 'declining'
    else:
        trend = 'stable'

    # AI-резюме недели
    ai_advice = generate_ai_advice(user_id, plan_id)

    return {
        'period': 'weekly',
        'start_date': (date.today() - timedelta(days=7)).isoformat(),
        'end_date': date.today().isoformat(),
        'total_solved': summary['total_tasks_solved'],
        'total_attempted': summary['total_tasks_attempted'],
        'accuracy': summary['overall_accuracy'],
        'total_minutes': summary['total_minutes_spent'],
        'streak': summary['streak'],
        'trend': trend,
        'solved_change': solved_change,
        'accuracy_change': accuracy_change,
        'current_profile': summary['current_profile'],
        'ai_advice': ai_advice,
    }


def get_profile_dynamics(
    user_id: int,
    plan_id: int = None,
    days: int = 30,
) -> Dict:
    """Получить динамику профиля по темам за период.

    Args:
        user_id: ID пользователя.
        plan_id: ID плана.
        days: Период анализа.

    Returns:
        dict: {topic: [{'date': ..., 'pct': ...}, ...]}
    """
    since = date.today() - timedelta(days=days)

    query = ProgressLog.query.filter(
        ProgressLog.user_id == user_id,
        ProgressLog.log_date >= since,
        ProgressLog.profile_snapshot.isnot(None),
    )
    if plan_id:
        query = query.filter(ProgressLog.plan_id == plan_id)

    logs = query.order_by(ProgressLog.log_date.asc()).all()

    # Собираем динамику по каждой теме
    topic_dynamics: Dict[str, List[Dict]] = {}
    for log_entry in logs:
        profile = log_entry.profile_snapshot_dict
        for topic, data in profile.items():
            if topic not in topic_dynamics:
                topic_dynamics[topic] = []
            pct = data.get('pct', 0) if isinstance(data, dict) else data
            topic_dynamics[topic].append({
                'date': log_entry.log_date.isoformat(),
                'pct': pct,
            })

    return topic_dynamics


# ─── Внутренние функции ──────────────────────────────────────────────────────


def _recalc_streak(user_id: int) -> int:
    """Пересчитать текущую серию (количество дней подряд с активностью)."""
    logs = (
        ProgressLog.query
        .filter_by(user_id=user_id)
        .order_by(ProgressLog.log_date.desc())
        .all()
    )

    if not logs:
        return 0

    streak = 0
    expected = date.today()

    for log_entry in logs:
        if log_entry.log_date == expected:
            if log_entry.tasks_total > 0:
                streak += 1
            expected -= timedelta(days=1)
        elif log_entry.log_date < expected:
            break

    return streak


def _get_max_streak(user_id: int) -> int:
    """Получить максимальную серию из всех записей."""
    max_val = (
        db.session.query(db.func.max(ProgressLog.max_streak))
        .filter(ProgressLog.user_id == user_id)
        .scalar()
    )
    return max_val or 0


def _get_current_profile(user_id: int, plan_id: int) -> Dict:
    """Получить текущий профиль из плана или диагностики."""
    # Сначала пробуем из плана
    if plan_id:
        plan = db.session.get(LearningPlan, plan_id)
        if plan and plan.current_profile:
            profile = plan.current_profile_dict
            if profile:
                return profile

    # Пробуем из последней завершённой диагностики
    diagnostic = (
        StudentDiagnostic.query
        .filter_by(user_id=user_id, status='completed')
        .order_by(StudentDiagnostic.completed_at.desc())
        .first()
    )
    if diagnostic:
        return diagnostic.profile

    return {}


def _detect_stuck_internal(user_id: int, plan_id: int = None) -> bool:
    """Внутренняя проверка на stuck."""
    is_stuck, _ = _check_stuck(user_id, plan_id)
    return is_stuck


def _check_stuck(user_id: int, plan_id: int = None) -> Tuple[bool, int]:
    """Проверить stuck и вернуть (is_stuck, days_since_progress)."""
    # Находим последнюю запись с активностью
    last_log = (
        ProgressLog.query
        .filter_by(user_id=user_id)
        .filter(ProgressLog.tasks_total > 0)
        .order_by(ProgressLog.log_date.desc())
        .first()
    )

    if not last_log:
        # Если вообще нет активности, считаем stuck если план активен
        if plan_id:
            plan = db.session.get(LearningPlan, plan_id)
            if plan and plan.status == 'active':
                return True, 999
        return False, 0

    days_since = (date.today() - last_log.log_date).days

    if days_since >= STUCK_DAYS_THRESHOLD:
        return True, days_since

    return False, days_since


def _sync_plan_profile(plan_id: int):
    """Синхронизировать профиль в плане с последним ProgressLog."""
    plan = db.session.get(LearningPlan, plan_id)
    if not plan:
        return

    latest_log = (
        ProgressLog.query
        .filter_by(plan_id=plan_id)
        .order_by(ProgressLog.log_date.desc())
        .first()
    )

    if latest_log and latest_log.profile_snapshot:
        plan.current_profile = latest_log.profile_snapshot
        plan.updated_at = datetime.utcnow()
        db.session.commit()


def _save_advice_to_log(user_id: int, plan_id: int, advice: str):
    """Сохранить AI-совет в последний лог прогресса."""
    try:
        last_log = (
            ProgressLog.query
            .filter_by(user_id=user_id)
            .order_by(ProgressLog.log_date.desc())
            .first()
        )
        if last_log:
            last_log.ai_advice = advice
            db.session.commit()
    except Exception as e:
        logger.warning(f"[progress] Failed to save advice: {e}")


def _generate_stuck_advice(user_id: int, days_since: int) -> str:
    """Сгенерировать совет при застревании."""
    if days_since >= 7:
        return (
            'Ты не занимаешься уже неделю. Попробуй начать с малого — реши '
            'сегодня 1-2 задачи, чтобы вернуть ритм. Даже небольшая победа '
            'запустит momentum!'
        )
    elif days_since >= 3:
        return (
            'Вижу, что несколько дней без занятий. Не переживай, это нормально. '
            'Попробуй сегодня уделить 15 минут одной задаче — и ты снова в деле!'
        )
    return None


def _get_motivation_restart_message(user_id: int) -> str:
    """Мотивационное сообщение для возвращающихся."""
    messages = [
        'Рады снова тебя видеть! Начни с разминки — реши одну задачу.',
        'Каждый великий путь начинается с первого шага. Сделай его сегодня!',
        'Олимпиадная математика ждёт тебя! Начни с темы, которая тебе ближе.',
        'Неважно, сколько дней прошло — важно, что ты вернулся. Вперёд!',
    ]
    return random.choice(messages)


def _get_fallback_advice(summary: dict, streak: dict, stuck: dict) -> str:
    """Fallback-совет без AI."""
    if stuck['is_stuck']:
        return _generate_stuck_advice(summary.get('user_id', 0), stuck['days_since_progress'])

    if streak['current_streak'] >= 7:
        return (
            f'Отличная работа! Твоя серия уже {streak["current_streak"]} дней. '
            'Продолжай в том же духе — результат не заставит себя ждать!'
        )
    elif streak['current_streak'] >= 3:
        return (
            f'Хороший темп! {streak["current_streak"]} дней подряд — '
            'ты на правильном пути. Попробуй увеличить количество задач.'
        )
    elif summary['total_tasks_solved'] > 0:
        return (
            f'За последние 7 дней ты решил {summary["total_tasks_solved"]} задач '
            f'с точностью {summary["overall_accuracy"]}%. '
            'Регулярность — ключ к успеху. Занимайся каждый день хотя бы по 15 минут!'
        )
    else:
        return 'Начни заниматься уже сегодня! Реши одну задачу — и процесс пойдёт.'


# ─── AI-промпт ───────────────────────────────────────────────────────────────

_ADVICE_SYSTEM_PROMPT = (
    "Ты — AI-куратор платформы FORMYLA. Твоя задача — дать краткий, "
    "персонализированный совет ученику на основе его прогресса.\n\n"
    "ПРАВИЛА:\n"
    "1. Пиши на русском языке, обращайся на «ты».\n"
    "2. Будь конкретным: используй цифры из статистики.\n"
    "3. Если ученик застрял — мягко мотивируй и предложи конкретный шаг.\n"
    "4. Если есть прогресс — похвали и предложи, как улучшить.\n"
    "5. Максимум 200 символов.\n"
    "6. Не используй шаблонные фразы. Персонализируй совет."
)
