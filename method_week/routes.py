# -*- coding: utf-8 -*-
"""Эндпоинты «Метода недели» (тестовый период: только METHOD_WEEK_ALLOWED_USERS).

GET  /method_week/api/today          — набор текущей недели (создаёт и запускает генерацию)
GET  /method_week/api/status         — polling генерации
GET  /method_week/api/<pos>/hint     — подсказка
POST /method_week/api/<pos>/submit   — ответ на задачу (проверка как в задачах дня)
GET  /method_week/api/curator_plan   — ежедневный план куратора + план методов на месяц
POST /method_week/api/regenerate     — перегенерация (тестовая группа)
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime

from flask import current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from models import db
from . import method_week_bp
from .models import MethodWeekSet, MethodWeekAnswer, ensure_tables
from .catalog import (method_for_week, user_grade, user_level, week_start,
                      get_or_build_month_plan, mark_covered, week_index_in_month)
from .access import user_allowed

logger = logging.getLogger(__name__)


@method_week_bp.before_request
def _only_allowed_users():
    """Тестовый период: раздел виден только аккаунтам из METHOD_WEEK_ALLOWED_USERS."""
    if not getattr(current_user, 'is_authenticated', False):
        return None  # login_required ответит сам
    if not user_allowed(current_user):
        return jsonify({'status': 'hidden', 'message': 'Раздел пока в закрытом тесте.'}), 404
    return None


def _today() -> date:
    try:
        from daily_tasks.services import today_in_user_tz
        return today_in_user_tz()
    except Exception:
        return date.today()


def _is_admin() -> bool:
    admin_emails = {e.strip().lower() for e in os.environ.get('ADMIN_EMAILS', '').split(',') if e.strip()}
    return current_user.id == 1 or (getattr(current_user, 'email', '') or '').lower() in admin_emails


def _current_set(user_id: int):
    ensure_tables()
    return MethodWeekSet.query.filter_by(user_id=user_id, week_start=week_start(_today())).first()


@method_week_bp.route('', methods=['GET'])
@method_week_bp.route('/', methods=['GET'])
@login_required
def method_week_page():
    """Отдельная страница «Метод недели»: разбор + 3 задачи (пилоты).

    Кнопка «сегодня изучаешь этот метод» с дашборда ведёт прямо сюда
    (владелец, 26.10). Гейт — before_request (METHOD_WEEK_ALLOWED_USERS).
    """
    return render_template('method_week/page.html')


def _get_or_create_set(user_id: int):
    s = _current_set(user_id)
    if s and s.status == 'generating' and s.created_at and \
            (datetime.utcnow() - s.created_at).total_seconds() > 900:
        s.status = 'failed'
        s.error_message = 'Генерация прервана (таймаут 15 мин)'
        db.session.commit()
    if s:
        return s
    method = method_for_week(user_id, _today())
    if not method:
        return None
    grade = user_grade(user_id) or 8
    level = user_level(user_id)
    s = MethodWeekSet(
        user_id=user_id, week_start=week_start(_today()), grade=grade, level=level,
        method_code=method.get('method_code') or '?',
        method_name=method.get('method_name') or '',
        section=method.get('section_slug'),
        status='generating', current_step='queued', progress_pct=0,
    )
    db.session.add(s)
    db.session.commit()
    from .generator import start_generation
    start_generation(current_app._get_current_object(), s.id, method, grade, level)
    return s


def _serialize(s: MethodWeekSet, user_id: int) -> dict:
    answers = {a.position: a for a in MethodWeekAnswer.query.filter_by(set_id=s.id, user_id=user_id).all()}
    tasks = []
    for t in s.tasks:
        pos = int(t.get('position') or len(tasks) + 1)
        a = answers.get(pos)
        answered = bool(a and a.user_answer)
        tasks.append({
            'position': pos,
            'statement': t.get('statement', ''),
            'difficulty': t.get('difficulty'),
            'hints_count': len(t.get('hints') or []),
            'is_answered': answered,
            'is_correct': (a.is_correct if a else None),
            'user_answer': (a.user_answer if a else None),
            'ai_feedback': (a.ai_feedback if a else None),
            # решение и ответ показываем только после ответа
            'solution': (t.get('solution') if answered else None),
            'correct_answer': (t.get('answer') if answered else None),
        })
    solved = sum(1 for t in tasks if t['is_answered'])
    return {
        'status': s.status,
        'set_id': s.id,
        'week_start': s.week_start.isoformat(),
        'method_code': s.method_code,
        'method_name': s.method_name,
        'section': s.section,
        'level': s.level,
        'progress_pct': s.progress_pct,
        'current_step': s.current_step,
        'error': s.error_message,
        'lesson_md': s.lesson_md if s.status == 'ready' else None,
        'tasks': tasks if s.status == 'ready' else [],
        'progress': {'completed': solved, 'total': len(tasks)},
        'model': s.model_name,
    }


@method_week_bp.route('/api/today', methods=['GET'])
@login_required
def api_today():
    try:
        s = _get_or_create_set(current_user.id)
    except Exception as exc:
        logger.exception("method_week: api_today failed: %s", exc)
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'Метод недели временно недоступен'}), 500
    if not s:
        return jsonify({'status': 'no_plan',
                        'message': 'Куратор ещё не составил план методов — пройди анкету и срез.'}), 200
    return jsonify(_serialize(s, current_user.id))


@method_week_bp.route('/api/status', methods=['GET'])
@login_required
def api_status():
    s = _current_set(current_user.id)
    if not s:
        return jsonify({'status': 'no_set'}), 404
    return jsonify({'status': s.status, 'progress_pct': s.progress_pct,
                    'current_step': s.current_step, 'error': s.error_message})


@method_week_bp.route('/api/<int:pos>/hint', methods=['GET'])
@login_required
def api_hint(pos: int):
    s = _current_set(current_user.id)
    if not s or s.status != 'ready':
        return jsonify({'status': 'error', 'message': 'Набор не готов'}), 404
    try:
        n = int(request.args.get('n', 1) or 1)
    except ValueError:
        n = 1
    for t in s.tasks:
        if int(t.get('position') or 0) == pos:
            hints = t.get('hints') or []
            if not hints:
                return jsonify({'status': 'ok', 'hint': 'Подсказок нет — перечитай разбор метода выше.', 'total': 0})
            idx = min(max(n, 1), len(hints)) - 1
            return jsonify({'status': 'ok', 'hint': hints[idx], 'total': len(hints)})
    return jsonify({'status': 'error', 'message': 'Задача не найдена'}), 404


@method_week_bp.route('/api/<int:pos>/submit', methods=['POST'])
@login_required
def api_submit(pos: int):
    """Проверка — тот же пайплайн, что в задачах дня (_submit_bank_answer)."""
    s = _current_set(current_user.id)
    if not s or s.status != 'ready':
        return jsonify({'status': 'error', 'message': 'Набор не готов'}), 404
    task = next((t for t in s.tasks if int(t.get('position') or 0) == pos), None)
    if not task:
        return jsonify({'status': 'error', 'message': 'Задача не найдена'}), 404

    ans = MethodWeekAnswer.query.filter_by(set_id=s.id, position=pos).first()
    if ans and ans.user_answer:
        return jsonify({
            'status': 'already_answered', 'already_answered': True,
            'is_correct': bool(ans.is_correct), 'user_answer': ans.user_answer,
            'feedback': ans.ai_feedback or '', 'correct_answer': task.get('answer', ''),
            'solution': task.get('solution', ''),
        }), 409

    data = request.get_json(silent=True) or {}
    user_answer = (data.get('user_answer') or data.get('answer') or '').strip()
    user_solution = (data.get('user_solution') or '').strip()
    if not user_answer:
        return jsonify({'status': 'error', 'message': 'Не указан ответ'}), 400

    raw_images = []
    single = data.get('solution_image_b64') or ''
    if single:
        raw_images.append(single)
    multi = data.get('solution_images_b64') or []
    if isinstance(multi, list):
        raw_images.extend([it for it in multi if isinstance(it, str) and it.strip()])
    images_b64 = [(b.split(',', 1)[-1] if b.startswith('data:') else b) for b in raw_images if b]
    if not user_solution and not images_b64:
        return jsonify({'status': 'error', 'error': 'Опиши решение или прикрепи фото.'}), 400

    is_correct, feedback, score, verdict = False, '', None, None
    try:
        from services.solution_check_pipeline import check_solution
        import concurrent.futures as _cf
        with _cf.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(
                check_solution,
                entity_type='daily_task',
                task_text=task.get('statement') or '',
                correct_answer=task.get('answer') or '',
                solution_ref=task.get('solution') or '',
                user_answer=user_answer,
                user_solution=user_solution,
                images_b64=images_b64,
                difficulty_level=int(task.get('difficulty') or 2),
            )
            try:
                verdict = fut.result(timeout=60)
            except _cf.TimeoutError:
                verdict = None
        if verdict:
            is_correct = bool(verdict.get('is_correct'))
            feedback = verdict.get('feedback') or ''
            score = verdict.get('score')
    except Exception as exc:
        logger.exception("method_week: check pipeline failed: %s", exc)

    if verdict and verdict.get('ocr_failed'):
        return jsonify({'status': 'error', 'ocr_failed': True,
                        'message': verdict.get('feedback') or
                        'Не удалось разобрать фото. Сфотографируй чётче или опиши шаги текстом.'}), 422

    if not feedback:
        try:
            from utils.math_answer_utils import compare_math_answers
            is_correct = bool(compare_math_answers(user_answer, task.get('answer') or ''))
        except Exception:
            is_correct = False
        feedback = 'Молодец, верно!' if is_correct else 'Неверно. Посмотри решение ниже.'

    try:
        if ans is None:
            ans = MethodWeekAnswer(set_id=s.id, user_id=current_user.id, position=pos)
            db.session.add(ans)
        ans.user_answer = user_answer[:4000]
        ans.user_solution = user_solution[:8000]
        ans.is_correct = is_correct
        ans.score = score if isinstance(score, int) else None
        ans.ai_feedback = (feedback or '')[:8000]
        ans.answered_at = datetime.utcnow()
        try:
            ans.time_spent_seconds = int(data.get('time_spent_seconds') or 0)
        except (TypeError, ValueError):
            ans.time_spent_seconds = 0
        if is_correct and not ans.xp_awarded:
            from models import User as _User
            u = db.session.get(_User, current_user.id)
            if u is not None:
                u.experience_points = (u.experience_points or 0) + 8
                u.total_problems_solved = (u.total_problems_solved or 0) + 1
                ans.xp_awarded = True
        db.session.commit()
        # все задачи недели отвечены -> метод пройден (в следующем месяце не повторится)
        done = MethodWeekAnswer.query.filter_by(set_id=s.id) \
            .filter(MethodWeekAnswer.user_answer.isnot(None)).count()
        if done >= len(s.tasks):
            mark_covered(current_user.id, s.method_code)
            # ── SESSION_PLAN_V1 (26.10.2026): все задачи метод-сета
            # отвечены — занятие «изучение метода» завершено (пилоты).
            try:
                from curator.session_plan import maybe_complete_method
                maybe_complete_method(current_user.id)
            except Exception:
                logger.exception("session_plan method hook failed")
    except Exception as exc:
        db.session.rollback()
        logger.exception("method_week: save answer failed: %s", exc)

    return jsonify({
        'status': 'success', 'score': score, 'feedback': feedback, 'is_correct': is_correct,
        'correct_answer': task.get('answer') or '', 'user_answer': user_answer,
        'solution': task.get('solution') or '',
    })


@method_week_bp.route('/api/curator_plan', methods=['GET'])
@login_required
def api_curator_plan():
    """Куратор: что у тебя сегодня, что делать, план методов на месяц."""
    try:
        from curator.daily_plan import get_daily_plan
        plan_msg = get_daily_plan(current_user.id, _today())
    except Exception as exc:
        logger.warning("method_week: get_daily_plan failed: %s", exc)
        plan_msg = None
    try:
        month = get_or_build_month_plan(current_user.id, _today())
    except Exception as exc:
        logger.warning("method_week: month plan failed: %s", exc)
        db.session.rollback()
        month = {}
    return jsonify({
        'daily': plan_msg,
        'month': {
            'month': month.get('month'),
            'current_week': week_index_in_month(_today()),
            'methods': [
                {'code': c, 'name': (month.get('names') or {}).get(c, c),
                 'section': (month.get('sections') or {}).get(c),
                 'reason': (month.get('reason') or {}).get(c, '')}
                for c in (month.get('methods') or [])
            ],
            'covered_total': len(month.get('covered') or []),
        },
    })


@method_week_bp.route('/api/regenerate', methods=['POST'])
@login_required
def api_regenerate():
    """Перезапуск набора недели. Доступен тестовой группе (before_request уже
    отсёк всех, кроме METHOD_WEEK_ALLOWED_USERS). Не чаще раза в 2 минуты."""
    s = _current_set(current_user.id)
    if s and s.status == 'generating' and s.created_at and \
            (datetime.utcnow() - s.created_at).total_seconds() < 120:
        return jsonify(_serialize(s, current_user.id))
    if s:
        MethodWeekAnswer.query.filter_by(set_id=s.id).delete()
        db.session.delete(s)
        db.session.commit()
    s = _get_or_create_set(current_user.id)
    return jsonify(_serialize(s, current_user.id) if s else {'status': 'no_plan'})
