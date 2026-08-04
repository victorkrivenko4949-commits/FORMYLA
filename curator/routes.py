# -*- coding: utf-8 -*-
"""
routes.py — REST API endpoints для модуля «Куратор» (AI-наставник).

Префикс: /curator (задан в __init__.py).

Эндпоинты:
  Диагностика:
    POST   /curator/diagnostics/start        — начать диагностику
    GET    /curator/diagnostics/<id>/next     — следующий вопрос
    POST   /curator/diagnostics/<id>/answer   — отправить ответ
    GET    /curator/diagnostics/<id>/result   — результаты
    POST   /curator/diagnostics/<id>/summary  — AI-резюме

  План обучения:
    POST   /curator/plans                     — создать план
    GET    /curator/plans                     — список планов
    GET    /curator/plans/<id>                — детали плана
    POST   /curator/plans/<id>/recompute      — пересчитать план
    POST   /curator/plans/<id>/advance        — следующая неделя
    POST   /curator/plans/<id>/pause          — пауза
    POST   /curator/plans/<id>/resume         — возобновить
    GET    /curator/plans/<id>/tasks          — задачи недели

  AI-тьютор:
    POST   /curator/tutor/hints               — подсказки
    POST   /curator/tutor/review              — проверка решения
    POST   /curator/tutor/explain             — объяснение метода
    GET    /curator/tutor/attempts/<user_id>/<task_id> — история попыток

  Прогресс:
    GET    /curator/progress/<user_id>        — сводка прогресса
    GET    /curator/progress/<user_id>/streak — информация о серии
    GET    /curator/progress/<user_id>/stuck  — проверка застревания
    GET    /curator/progress/<user_id>/weekly — недельный отчёт
    POST   /curator/progress/<user_id>/advice — AI-совет
    GET    /curator/progress/<user_id>/dynamics — динамика профиля
"""

import json
import logging
from datetime import date, datetime

from flask import jsonify, request, g, current_app

from curator import curator_bp
from curator.diagnostics import (
    start_diagnostic_session,
    get_next_question,
    submit_answer,
    get_diagnostic_result,
    generate_ai_summary,
)
from curator.planner import (
    create_plan_from_diagnostic,
    get_plan,
    recompute_plan,
    advance_week,
    pause_plan,
    resume_plan,
    get_tasks_for_week,
)
from curator.tutor import (
    get_hints,
    review_solution,
    get_task_explanation,
    get_user_attempts,
)
from curator.progress import (
    get_progress_summary,
    get_streak,
    detect_stuck,
    get_weekly_report,
    generate_ai_advice,
    get_profile_dynamics,
    create_or_update_daily_log,
)

from curator.topic_analyzer import analyze_topics
from curator.olympiad_advisor import recommend_olympiads

from models import db
from curator.models import StudentDiagnostic, LearningPlan

logger = logging.getLogger(__name__)


# ─── Вспомогательные функции ─────────────────────────────────────────────────


def _get_current_user_id() -> int:
    """Получить ID текущего пользователя ТОЛЬКО из Flask-Login сессии.

    Fallback на параметры запроса (request.args / request.json) УБРАН —
    нельзя действовать от чужого имени, передав ?user_id=X.
    """
    try:
        from flask_login import current_user
        if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
            return current_user.id
    except (ImportError, Exception):
        pass
    return None


def _json_response(data, status=200):
    """Сформировать JSON-ответ."""
    return jsonify({'ok': status < 400, 'data': data}), status


def _error_response(message, status=400):
    """Сформировать JSON-ответ с ошибкой."""
    return jsonify({'ok': False, 'error': message}), status


def _require_user_id():
    """Проверить, что user_id передан."""
    user_id = _get_current_user_id()
    if not user_id:
        return None, _error_response('user_id is required', 401)
    return user_id, None


def _verify_session_ownership(session_id: int):
    """Проверить, что текущий пользователь владеет сессией диагностики.

    Returns: (user_id, None) if owner, (None, error_response) otherwise.
    """
    current_uid = _get_current_user_id()
    if not current_uid:
        # Если пользователь не аутентифицирован — пропускаем проверку
        # (может быть guest-сессия, где user_id не совпадает)
        return current_uid, None

    session = db.session.get(StudentDiagnostic, session_id)
    if not session:
        return None, _error_response('Session not found', 404)

    if current_uid != session.user_id:
        return None, _error_response('Access denied', 403)

    return current_uid, None


def _verify_plan_ownership(plan_id: int):
    """Проверить, что текущий пользователь владеет планом обучения.

    Returns: (user_id, None) if owner, (None, error_response) otherwise.
    """
    current_uid = _get_current_user_id()
    if not current_uid:
        return current_uid, None

    plan = db.session.get(LearningPlan, plan_id)
    if not plan:
        return None, _error_response('Plan not found', 404)

    if current_uid != plan.user_id:
        return None, _error_response('Access denied', 403)

    return current_uid, None


# ─── ДИАГНОСТИКА ─────────────────────────────────────────────────────────────


@curator_bp.route('/diagnostics/start', methods=['POST'])
def api_diagnostics_start():
    """Начать диагностическую сессию.

    POST /curator/diagnostics/start
    Body: {"user_id": 123, "grade": 9} (grade optional)
    """
    data = request.get_json(silent=True) or {}
    user_id = _get_current_user_id()
    if not user_id:
        return _error_response('user_id is required', 401)

    grade = data.get('grade')
    session = start_diagnostic_session(user_id=int(user_id), grade=int(grade) if grade else None)

    return _json_response({
        'session_id': session.id,
        'user_id': session.user_id,
        'status': session.status,
        'started_at': session.started_at.isoformat() if session.started_at else None,
        'message': 'Диагностика начата. Используй /curator/diagnostics/<id>/next для получения вопросов.',
    }, 201)


@curator_bp.route('/diagnostics/<int:session_id>/next', methods=['GET'])
def api_diagnostics_next(session_id: int):
    """Получить следующий вопрос диагностики.

    GET /curator/diagnostics/<session_id>/next
    """
    # Проверка доступа
    _, err = _verify_session_ownership(session_id)
    if err:
        return err

    question = get_next_question(session_id)
    if question is None:
        # Тест завершён — возвращаем результат
        result = get_diagnostic_result(session_id)
        if result:
            return _json_response({
                'test_complete': True,
                'result': result,
                'message': 'Диагностика завершена. Используй /curator/diagnostics/<id>/result для деталей.',
            })
        return _error_response('Session not found or already completed', 404)

    return _json_response({
        'test_complete': False,
        'question': question,
    })


@curator_bp.route('/diagnostics/<int:session_id>/answer', methods=['POST'])
def api_diagnostics_answer(session_id: int):
    """Отправить ответ на вопрос диагностики.

    POST /curator/diagnostics/<session_id>/answer
    Body: {"task_id": 456, "answer": "42", "time_spent_sec": 120}
    """
    # Проверка доступа
    _, err = _verify_session_ownership(session_id)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    task_id = data.get('task_id')
    answer = data.get('answer', '')
    time_spent_sec = data.get('time_spent_sec')

    if not task_id or not answer:
        return _error_response('task_id and answer are required', 400)

    result = submit_answer(
        session_id=session_id,
        task_id=int(task_id),
        answer=str(answer),
        time_spent_sec=int(time_spent_sec) if time_spent_sec else None,
    )

    if 'error' in result:
        return _error_response(result['error'], 404)

    return _json_response(result)


@curator_bp.route('/diagnostics/<int:session_id>/result', methods=['GET'])
def api_diagnostics_result(session_id: int):
    """Получить результаты диагностики.

    GET /curator/diagnostics/<session_id>/result
    """
    # Проверка доступа
    _, err = _verify_session_ownership(session_id)
    if err:
        return err

    result = get_diagnostic_result(session_id)
    if not result:
        return _error_response('Session not found', 404)

    return _json_response(result)


@curator_bp.route('/diagnostics/<int:session_id>/summary', methods=['POST'])
def api_diagnostics_summary(session_id: int):
    """Сгенерировать AI-резюме по результатам диагностики.

    POST /curator/diagnostics/<session_id>/summary
    """
    # Проверка доступа
    _, err = _verify_session_ownership(session_id)
    if err:
        return err

    summary = generate_ai_summary(session_id)
    if not summary:
        return _error_response('Session not found or not completed', 404)

    return _json_response({
        'session_id': session_id,
        'ai_summary': summary,
    })


# ─── ПЛАН ОБУЧЕНИЯ ────────────────────────────────────────────────────────────


@curator_bp.route('/plans', methods=['POST'])
def api_plans_create():
    """Создать учебный план на основе диагностики.

    POST /curator/plans
    Body: {
      "user_id": 123,
      "diagnostic_id": 1,
      "target_olympiad": "ВсОШ",
      "target_stage": "муниципальный",
      "target_date": "2026-12-01",
      "daily_tasks_count": 5,
      "title": "Подготовка к ВсОШ 9 класс"
    }
    """
    data = request.get_json(silent=True) or {}
    user_id = _get_current_user_id()
    if not user_id:
        return _error_response('user_id is required', 401)

    diagnostic_id = data.get('diagnostic_id')
    if not diagnostic_id:
        return _error_response('diagnostic_id is required', 400)

    target_date = None
    if data.get('target_date'):
        try:
            target_date = date.fromisoformat(data['target_date'])
        except (ValueError, TypeError):
            return _error_response('Invalid target_date format (use YYYY-MM-DD)', 400)

    plan = create_plan_from_diagnostic(
        user_id=int(user_id),
        diagnostic_id=int(diagnostic_id),
        target_olympiad=data.get('target_olympiad'),
        target_stage=data.get('target_stage'),
        target_date=target_date,
        daily_tasks_count=int(data.get('daily_tasks_count', 5)),
        title=data.get('title'),
    )

    if not plan:
        return _error_response(
            'Failed to create plan. Check that diagnostic_id is valid and completed.', 400
        )

    return _json_response({'plan_id': plan.id, 'status': 'created'}, 201)


@curator_bp.route('/plans', methods=['GET'])
def api_plans_list():
    """Получить список планов пользователя.

    GET /curator/plans?user_id=123
    """
    user_id = _get_current_user_id()
    if not user_id:
        return _error_response('user_id is required', 401)

    from curator.models import LearningPlan
    plans = (
        LearningPlan.query
        .filter_by(user_id=int(user_id))
        .order_by(LearningPlan.created_at.desc())
        .all()
    )

    return _json_response([
        {
            'id': p.id,
            'title': p.title,
            'status': p.status,
            'goal': p.goal,
            'target_olympiad': p.target_olympiad,
            'target_date': p.target_date.isoformat() if p.target_date else None,
            'total_weeks': p.total_weeks,
            'current_week': p.current_week,
            'created_at': p.created_at.isoformat() if p.created_at else None,
        }
        for p in plans
    ])


@curator_bp.route('/plans/<int:plan_id>', methods=['GET'])
def api_plans_detail(plan_id: int):
    """Получить детали плана.

    GET /curator/plans/<plan_id>
    """
    # Проверка доступа
    _, err = _verify_plan_ownership(plan_id)
    if err:
        return err

    plan = get_plan(plan_id)
    if not plan:
        return _error_response('Plan not found', 404)

    return _json_response(plan)


@curator_bp.route('/plans/<int:plan_id>/recompute', methods=['POST'])
def api_plans_recompute(plan_id: int):
    """Пересчитать план на основе текущего прогресса.

    POST /curator/plans/<plan_id>/recompute
    """
    # Проверка доступа
    _, err = _verify_plan_ownership(plan_id)
    if err:
        return err

    plan = recompute_plan(plan_id)
    if not plan:
        return _error_response('Plan not found or not active', 404)

    return _json_response({'plan_id': plan.id, 'status': 'recomputed'})


@curator_bp.route('/plans/<int:plan_id>/advance', methods=['POST'])
def api_plans_advance(plan_id: int):
    """Перейти к следующей неделе плана.

    POST /curator/plans/<plan_id>/advance
    """
    # Проверка доступа
    _, err = _verify_plan_ownership(plan_id)
    if err:
        return err

    success = advance_week(plan_id)
    if not success:
        return _error_response('Plan not found or not active', 404)

    from curator.models import LearningPlan
    plan = db.session.get(LearningPlan, plan_id)
    return _json_response({
        'plan_id': plan_id,
        'current_week': plan.current_week if plan else None,
        'total_weeks': plan.total_weeks if plan else None,
        'status': plan.status if plan else None,
    })


@curator_bp.route('/plans/<int:plan_id>/pause', methods=['POST'])
def api_plans_pause(plan_id: int):
    """Поставить план на паузу.

    POST /curator/plans/<plan_id>/pause
    """
    # Проверка доступа
    _, err = _verify_plan_ownership(plan_id)
    if err:
        return err

    success = pause_plan(plan_id)
    if not success:
        return _error_response('Plan not found', 404)
    return _json_response({'plan_id': plan_id, 'status': 'paused'})


@curator_bp.route('/plans/<int:plan_id>/resume', methods=['POST'])
def api_plans_resume(plan_id: int):
    """Возобновить план.

    POST /curator/plans/<plan_id>/resume
    """
    # Проверка доступа
    _, err = _verify_plan_ownership(plan_id)
    if err:
        return err

    success = resume_plan(plan_id)
    if not success:
        return _error_response('Plan not found', 404)
    return _json_response({'plan_id': plan_id, 'status': 'active'})


@curator_bp.route('/plans/<int:plan_id>/tasks', methods=['GET'])
def api_plans_tasks(plan_id: int):
    """Получить задачи текущей (или указанной) недели плана.

    GET /curator/plans/<plan_id>/tasks?week=2
    """
    # Проверка доступа
    _, err = _verify_plan_ownership(plan_id)
    if err:
        return err

    week = request.args.get('week', type=int)
    week_data = get_tasks_for_week(plan_id, week)
    if not week_data:
        return _error_response('Plan not found or no tasks for this week', 404)

    return _json_response(week_data)


# ─── AI-ТЬЮТОР ────────────────────────────────────────────────────────────────


@curator_bp.route('/tutor/hints', methods=['POST'])
def api_tutor_hints():
    """Получить подсказки для задачи.

    POST /curator/tutor/hints
    Body: {
      "task_id": 123,
      "task_text": "Условие задачи...",
      "topic": "algebra",
      "difficulty": 5,
      "hints_already_shown": 0
    }
    """
    data = request.get_json(silent=True) or {}
    task_id = data.get('task_id')
    task_text = data.get('task_text', '')
    topic = data.get('topic', 'algebra')
    difficulty = int(data.get('difficulty', 4))
    hints_shown = int(data.get('hints_already_shown', 0))

    if not task_id or not task_text:
        return _error_response('task_id and task_text are required', 400)

    hints = get_hints(
        task_id=int(task_id),
        task_text=task_text,
        topic=topic,
        difficulty=difficulty,
        hints_already_shown=hints_shown,
    )

    return _json_response({
        'task_id': task_id,
        'hints': hints,
        'hints_count': len(hints),
    })


@curator_bp.route('/tutor/review', methods=['POST'])
def api_tutor_review():
    """Проверить решение задачи.

    POST /curator/tutor/review
    Body: {
      "user_id": 123,
      "task_id": 456,
      "task_text": "Условие задачи...",
      "user_answer": "Ответ ученика",
      "correct_answer": "Правильный ответ",
      "solution": "Решение (опционально)",
      "topic": "algebra",
      "difficulty": 5,
      "plan_id": 1 (опционально),
      "task_source": "curator_plan" (опционально)
    }
    """
    data = request.get_json(silent=True) or {}
    user_id = _get_current_user_id()
    if not user_id:
        return _error_response('user_id is required', 401)

    task_id = data.get('task_id')
    task_text = data.get('task_text', '')
    user_answer = data.get('user_answer', '')
    correct_answer = data.get('correct_answer', '')

    if not task_id or not task_text or not user_answer:
        return _error_response('task_id, task_text, and user_answer are required', 400)

    result = review_solution(
        user_id=int(user_id),
        task_id=int(task_id),
        task_text=task_text,
        user_answer=user_answer,
        correct_answer=correct_answer,
        solution=data.get('solution', ''),
        topic=data.get('topic', ''),
        difficulty=int(data['difficulty']) if data.get('difficulty') else None,
        plan_id=int(data['plan_id']) if data.get('plan_id') else None,
        task_source=data.get('task_source', 'curator_plan'),
    )

    # Если есть план — обновляем профиль прогресса
    if data.get('plan_id') and result.get('attempt_id'):
        try:
            from curator.models import CuratorTaskAttempt
            attempt = db.session.get(CuratorTaskAttempt, result['attempt_id'])
            if attempt:
                from curator.progress import update_profile_after_attempt
                update_profile_after_attempt(attempt, plan_id=int(data['plan_id']))
        except Exception as e:
            logger.warning(f"[routes] Failed to update progress after review: {e}")

    return _json_response(result)


@curator_bp.route('/tutor/explain', methods=['POST'])
def api_tutor_explain():
    """Получить объяснение метода решения задачи.

    POST /curator/tutor/explain
    Body: {
      "task_text": "Условие задачи...",
      "solution": "Решение...",
      "topic": "algebra"
    }
    """
    data = request.get_json(silent=True) or {}
    task_text = data.get('task_text', '')
    solution = data.get('solution', '')
    topic = data.get('topic', 'algebra')

    if not task_text:
        return _error_response('task_text is required', 400)

    explanation = get_task_explanation(
        task_text=task_text,
        solution=solution,
        topic=topic,
    )

    return _json_response({
        'explanation': explanation,
    })


@curator_bp.route('/tutor/attempts/<int:user_id>/<int:task_id>', methods=['GET'])
def api_tutor_attempts(user_id: int, task_id: int):
    """Получить историю попыток пользователя по задаче.

    GET /curator/tutor/attempts/<user_id>/<task_id>
    """
    # Проверка доступа
    current_uid = _get_current_user_id()
    if current_uid and current_uid != user_id:
        return _error_response('Access denied', 403)

    attempts = get_user_attempts(user_id, task_id)
    return _json_response({
        'user_id': user_id,
        'task_id': task_id,
        'attempts': attempts,
        'attempts_count': len(attempts),
    })


# ─── ПРОГРЕСС ─────────────────────────────────────────────────────────────────


@curator_bp.route('/progress/<int:user_id>', methods=['GET'])
def api_progress_summary(user_id: int):
    """Получить сводку прогресса.

    GET /curator/progress/<user_id>?plan_id=1&days=30
    """
    # Проверка доступа
    current_uid = _get_current_user_id()
    if current_uid and current_uid != user_id:
        return _error_response('Access denied', 403)

    plan_id = request.args.get('plan_id', type=int)
    days = request.args.get('days', 30, type=int)
    days = min(max(days, 1), 365)  # 1-365 дней

    summary = get_progress_summary(user_id, plan_id=plan_id, days=days)
    return _json_response(summary)


@curator_bp.route('/progress/<int:user_id>/streak', methods=['GET'])
def api_progress_streak(user_id: int):
    """Получить информацию о серии (streak).

    GET /curator/progress/<user_id>/streak
    """
    current_uid = _get_current_user_id()
    if current_uid and current_uid != user_id:
        return _error_response('Access denied', 403)

    streak = get_streak(user_id)
    return _json_response(streak)


@curator_bp.route('/progress/<int:user_id>/stuck', methods=['GET'])
def api_progress_stuck(user_id: int):
    """Проверить, застрял ли ученик.

    GET /curator/progress/<user_id>/stuck?plan_id=1
    """
    current_uid = _get_current_user_id()
    if current_uid and current_uid != user_id:
        return _error_response('Access denied', 403)

    plan_id = request.args.get('plan_id', type=int)
    stuck_info = detect_stuck(user_id, plan_id=plan_id)
    return _json_response(stuck_info)


@curator_bp.route('/progress/<int:user_id>/weekly', methods=['GET'])
def api_progress_weekly(user_id: int):
    """Получить недельный отчёт.

    GET /curator/progress/<user_id>/weekly?plan_id=1
    """
    current_uid = _get_current_user_id()
    if current_uid and current_uid != user_id:
        return _error_response('Access denied', 403)

    plan_id = request.args.get('plan_id', type=int)
    report = get_weekly_report(user_id, plan_id=plan_id)
    return _json_response(report)


@curator_bp.route('/progress/<int:user_id>/advice', methods=['POST'])
def api_progress_advice(user_id: int):
    """Сгенерировать AI-совет.

    POST /curator/progress/<user_id>/advice
    Body: {"plan_id": 1} (optional)
    """
    current_uid = _get_current_user_id()
    if current_uid and current_uid != user_id:
        return _error_response('Access denied', 403)

    data = request.get_json(silent=True) or {}
    plan_id = data.get('plan_id')

    advice = generate_ai_advice(user_id, plan_id=plan_id)
    return _json_response({
        'user_id': user_id,
        'advice': advice,
    })


@curator_bp.route('/progress/<int:user_id>/dynamics', methods=['GET'])
def api_progress_dynamics(user_id: int):
    """Получить динамику профиля по темам.

    GET /curator/progress/<user_id>/dynamics?plan_id=1&days=30
    """
    current_uid = _get_current_user_id()
    if current_uid and current_uid != user_id:
        return _error_response('Access denied', 403)

    plan_id = request.args.get('plan_id', type=int)
    days = request.args.get('days', 30, type=int)
    days = min(max(days, 1), 365)

    dynamics = get_profile_dynamics(user_id, plan_id=plan_id, days=days)
    return _json_response(dynamics)


# ─── ЛОГ ПРОГРЕССА (ручное создание/обновление) ──────────────────────────────


@curator_bp.route('/progress/<int:user_id>/log', methods=['POST'])
def api_progress_log(user_id: int):
    """Создать или обновить запись прогресса вручную.

    POST /curator/progress/<user_id>/log
    Body: {
      "plan_id": 1 (optional),
      "tasks_solved": 5,
      "tasks_total": 7,
      "minutes_spent": 30,
      "log_type": "daily" (daily/weekly/session)
    }
    """
    current_uid = _get_current_user_id()
    if current_uid and current_uid != user_id:
        return _error_response('Access denied', 403)

    data = request.get_json(silent=True) or {}

    log_entry = create_or_update_daily_log(
        user_id=user_id,
        plan_id=data.get('plan_id'),
        tasks_solved=int(data.get('tasks_solved', 0)),
        tasks_total=int(data.get('tasks_total', 0)),
        minutes_spent=float(data.get('minutes_spent', 0.0)),
        log_type=data.get('log_type', 'daily'),
    )

    return _json_response({
        'log_id': log_entry.id,
        'date': log_entry.log_date.isoformat(),
        'streak': log_entry.streak_days,
        'is_stuck': log_entry.is_stuck,
    }, 201)


# ─── КОМБО-ЭНДПОИНТ: полный цикл диагностики -> план ─────────────────────────


@curator_bp.route('/onboarding', methods=['POST'])
def api_onboarding():
    """Полный цикл онбординга: диагностика -> создание плана.

    POST /curator/onboarding
    Body: {
      "user_id": 123,
      "grade": 9,
      "target_olympiad": "ВсОШ",
      "target_stage": "муниципальный",
      "target_date": "2026-12-01"
    }

    Этот эндпоинт запускает полный цикл:
    1. Создаёт сессию диагностики
    2. Возвращает первый вопрос
    3. Клиент должен последовательно вызывать /answer и в конце /summary
    4. Затем /plans для создания плана
    """
    data = request.get_json(silent=True) or {}
    user_id = _get_current_user_id()
    if not user_id:
        return _error_response('user_id is required', 401)

    # Создаём диагностику
    grade = data.get('grade')
    session = start_diagnostic_session(
        user_id=int(user_id),
        grade=int(grade) if grade else None,
    )

    return _json_response({
        'session_id': session.id,
        'user_id': session.user_id,
        'status': 'onboarding_started',
        'next_step': {
            'method': 'GET',
            'url': f'/curator/diagnostics/{session.id}/next',
            'description': 'Получить первый вопрос диагностики',
        },
        'after_diagnostics': {
            'create_plan': {
                'method': 'POST',
                'url': '/curator/plans',
                'body': {
                    'user_id': int(user_id),
                    'diagnostic_id': session.id,
                    'target_olympiad': data.get('target_olympiad'),
                    'target_stage': data.get('target_stage'),
                    'target_date': data.get('target_date'),
                },
            },
        },
    }, 201)


# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────


@curator_bp.route('/analyze/topics', methods=['POST'])
def api_analyze_topics():
    """Анализ успеваемости ученика по темам (Topic Analyzer).

    Body JSON:
      - user_id: int (обязательный, или в query-параметре)

    Returns:
      JSON с per-topic метриками и общей сводкой.
    """
    try:
        user_id = _get_current_user_id()
        if not user_id:
            user_id = request.json.get('user_id') if request.is_json else None
        if not user_id:
            return _error_response('user_id is required', 400)
        result = analyze_topics(user_id)
        return _json_response(result)
    except Exception as e:
        logger.exception(f"[routes] analyze/topics failed for user_id={user_id}: {e}")
        return _error_response(f'Topic analysis failed: {e}', 500)


# ─── OLYMPIAD ADVISOR ─────────────────────────────────────────────────────


@curator_bp.route('/analyze/olympiads', methods=['POST'])
def api_analyze_olympiads():
    """Рекомендации олимпиад на основе анализа тем ученика.

    Body JSON (опционально):
      - user_id: int (если не определён из сессии)
      - grade: int (класс, если не указан — берётся из User.preferred_grade)

    Returns:
      JSON с рекомендациями, анализом тем и AI-советом.
    """
    try:
        user_id = _get_current_user_id()
        if not user_id:
            user_id = request.json.get('user_id') if request.is_json else None
        if not user_id:
            return _error_response('user_id is required', 400)

        grade = request.json.get('grade') if request.is_json else None

        result = recommend_olympiads(user_id, grade=grade)
        return _json_response(result)

    except Exception as e:
        logger.exception(f"[routes] analyze/olympiads failed for user_id={user_id}: {e}")
        return _error_response(f'Olympiad recommendation failed: {e}', 500)


# ─── Monthly Cycle (Prep) endpoints ─────────────────────────────────────────


@curator_bp.route('/prep/today', methods=['GET'])
def api_prep_today():
    """Получить информацию о сегодняшнем дне в цикле подготовки.

    GET /curator/prep/today

    Returns:
        {
            "subtopic": "quadratic_parameters",
            "subtopic_title": "Параметры квадратичной функции",
            "is_test_day": true,
            "tested": false,
            "cycle_day": 3,
            "has_tasks": false,
            "level": 2
        }
    """
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return _error_response('user_id is required', 401)

        from curator.monthly_cycle import get_today_info
        info = get_today_info(user_id)
        return _json_response(info)
    except Exception as e:
        logger.error(f"[routes] prep/today failed: {e}")
        return _error_response(f'Failed: {e}', 500)


@curator_bp.route('/prep/morning-test', methods=['GET'])
def api_prep_morning_test():
    """Получить тестовые задачи для утреннего теста.

    GET /curator/prep/morning-test

    Returns 5 задач для теста по подтеме дня.
    Если сегодня не тестовый день — возвращает {"is_test_day": false, "reason": "..."}.
    """
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return _error_response('user_id is required', 401)

        from curator.monthly_cycle import get_morning_test
        result = get_morning_test(user_id)
        return _json_response(result)
    except Exception as e:
        logger.error(f"[routes] prep/morning-test failed: {e}")
        return _error_response(f'Failed: {e}', 500)


@curator_bp.route('/prep/submit-test', methods=['POST'])
def api_prep_submit_test():
    """Принять результаты теста и запустить вечернюю генерацию задач.

    POST /curator/prep/submit-test
    Body: {
        "results": [
            {"task_id": 123, "is_correct": true, "user_answer": "42", "difficulty_level": 3},
            ...
        ],
        "subtopic": "quadratic_parameters"  # optional
    }

    Returns:
        {
            "success": true,
            "subtopic": "quadratic_parameters",
            "level": 3,
            "correct": 3,
            "total": 5,
            "generation_queued": true,
            "message": "..."
        }
    """
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return _error_response('user_id is required', 401)

        data = request.get_json(silent=True) or {}
        results = data.get('results', [])
        if not results:
            return _error_response('results is required', 400)

        subtopic = data.get('subtopic')

        from curator.monthly_cycle import submit_test_and_generate_tasks
        result = submit_test_and_generate_tasks(user_id, results, subtopic)
        return _json_response(result)
    except Exception as e:
        logger.error(f"[routes] prep/submit-test failed: {e}")
        return _error_response(f'Failed: {e}', 500)


@curator_bp.route('/prep/evening-generate', methods=['POST'])
def api_prep_evening_generate():
    """Сгенерировать задачи дня без теста (для task-only дней 8-30).

    POST /curator/prep/evening-generate
    Body: {"subtopic": "quadratic_parameters"}  # optional

    Returns:
        {
            "success": true,
            "subtopic": "quadratic_parameters",
            "level": 2,
            "generation_queued": true,
            "message": "..."
        }
    """
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return _error_response('user_id is required', 401)

        data = request.get_json(silent=True) or {}
        subtopic = data.get('subtopic')

        from curator.monthly_cycle import generate_tasks_only
        result = generate_tasks_only(user_id, subtopic)
        return _json_response(result)
    except Exception as e:
        logger.error(f"[routes] prep/evening-generate failed: {e}")
        return _error_response(f'Failed: {e}', 500)


@curator_bp.route('/prep/progress', methods=['GET'])
def api_prep_progress():
    """Получить общий прогресс по циклу подготовки.

    GET /curator/prep/progress

    Returns:
        {
            "cycle_day": 3,
            "total_days": 30,
            "tested_subtopics": ["quadratic_parameters"],
            "remaining_tests": 6,
            "subtopics_total": 7,
            "level": 2,
            "is_complete": false
        }
    """
    try:
        user_id = _get_current_user_id()
        if not user_id:
            return _error_response('user_id is required', 401)

        from curator.monthly_cycle import get_cycle_progress
        progress = get_cycle_progress(user_id)
        return _json_response(progress)
    except Exception as e:
        logger.error(f"[routes] prep/progress failed: {e}")
        return _error_response(f'Failed: {e}', 500)


# ─── Evening check + Health ──────────────────────────────────────────────────


@curator_bp.route('/notify/evening-check', methods=['POST'])
def api_curator_evening_check():
    """Вручную запустить вечернюю проверку куратора для текущего пользователя.

    Куратор оценивает прогресс за сегодня и отправляет push-уведомление
    с персонализированным сообщением (мотивация / дисциплина / похвала).

    POST /curator/notify/evening-check
    Body: {"user_id": 123} (optional — если не передан, берётся из сессии)
          {"force": true} (optional — отправить даже если всё решено)

    Returns:
        {
            "ok": true,
            "data": {
                "sent": true/false,
                "message": "...",
                "stats": {...}
            }
        }
    """
    try:
        data = request.get_json(silent=True) or {}
        user_id = _get_current_user_id()

        if not user_id:
            return _error_response('user_id is required', 401)

        force = data.get('force', False)

        from curator.push_service import check_and_notify_user
        result = check_and_notify_user(user_id=user_id, force=force)

        return _json_response({
            'sent': result['sent'],
            'message': result['message'],
            'stats': result['stats'],
        })
    except Exception as e:
        logger.error(f"[routes] Evening check failed: {e}")
        return _error_response(f'Evening check failed: {e}', 500)


@curator_bp.route('/', methods=['GET'])
@curator_bp.route('', methods=['GET'])
def curator_index():
    """Корневой маршрут куратора — редирект на /prep/coach."""
    from flask import redirect, url_for
    return redirect(url_for('prep.coach'))


@curator_bp.route('/health', methods=['GET'])
def api_curator_health():
    """Проверка работоспособности модуля Куратор."""
    from curator.models import StudentDiagnostic, LearningPlan, CuratorTaskAttempt, ProgressLog

    try:
        # Проверяем, что таблицы существуют
        diagnostic_count = StudentDiagnostic.query.count()
        plan_count = LearningPlan.query.count()
        attempt_count = CuratorTaskAttempt.query.count()
        log_count = ProgressLog.query.count()

        return _json_response({
            'status': 'healthy',
            'tables': {
                'student_diagnostics': diagnostic_count,
                'learning_plans': plan_count,
                'task_attempts': attempt_count,
                'progress_log': log_count,
            },
            'timestamp': datetime.utcnow().isoformat(),
        })
    except Exception as e:
        return _error_response(f'Health check failed: {e}', 500)


# ──────────────────────────────────────────────────────────────────────
# T7: Curator plan — monthly subtopic rotation
# ──────────────────────────────────────────────────────────────────────

@curator_bp.route("/plan", methods=["GET", "POST"])
@login_required
def curator_plan():
    """GET: show plan form. POST: save plan."""
    if request.method == "POST":
        from services.curator_plan_service import set_plan
        data = request.get_json() or {}
        items = data.get("items", [])
        parsed = [(it["subtopic"], int(it["month_number"]), int(it["position"]))
                  for it in items]
        set_plan(parsed)
        return jsonify({"success": True, "count": len(parsed)})

    # GET: show existing plan
    from services.curator_plan_service import check_plan_status
    status = check_plan_status()
    from models import CuratorPlanItem
    items = (CuratorPlanItem.query
             .order_by(CuratorPlanItem.month_number, CuratorPlanItem.position)
             .all())
    return render_template(
        "admin/curator_plan.html",
        plan_items=[{
            "subtopic": i.subtopic,
            "month_number": i.month_number,
            "position": i.position,
        } for i in items],
        status=status,
    )


@curator_bp.route("/plan-status")
@login_required
def curator_plan_status():
    """Show plan completeness for curator."""
    from services.curator_plan_service import check_plan_status
    status = check_plan_status()
    return render_template("admin/curator_plan_status.html", status=status)
