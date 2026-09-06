# -*- coding: utf-8 -*-
"""
services/intake_service.py — Оркестратор новой анкеты входа (P9 Intake).

API:
  start(user_id) -> dict              # первый вопрос
  answer(user_id, qid, key) -> dict   # записать ответ, вернуть следующий шаг
  submit_anchor(user_id, task_id, user_answer) -> dict  # проверка якоря
  finish(user_id) -> dict             # финализация: compute_prior, сохранение в БД

Состояние: Flask session['intake'].

Q1 теперь содержит опции teacher/parent наряду с классами 5-11.
Выбор teacher/parent → сразу завершает анкету, проставляет user.role
и редиректит в раздел учителя/родителя.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from services.intake_questions import (
    Q1_CLASS, Q2_GOAL, Q3_EXPERIENCE, Q4_TIME, Q5_WEAK_SECTIONS,
    ANCHOR_SECTION_ORDER, compute_prior, IntakeResult,
    assign_goal,
)
from services.anchors import pick_anchors
from services.anchors import check_answer as check_anchor_answer

logger = logging.getLogger(__name__)

# Ключи ролей, которые могут быть выбраны в Q1
TEACHER_ROLE_KEY = "teacher"
PARENT_ROLE_KEY = "parent"
NON_STUDENT_ROLE_KEYS = {TEACHER_ROLE_KEY, PARENT_ROLE_KEY}


# ══════════════════════════════════════════════════════════════════════
# Вспомогательные функции
# ══════════════════════════════════════════════════════════════════════

def _get_session_state() -> Optional[Dict]:
    """Получить состояние анкеты из Flask-сессии, с fallback в CuratorState."""
    from flask import session
    from flask_login import current_user
    state = session.get('intake', None)
    if state is not None:
        return state
    # Fallback: восстановить из CuratorState если сессия сбросилась
    try:
        from models_curator import CuratorState
        if current_user and current_user.is_authenticated:
            cs = CuratorState.query.filter_by(user_id=current_user.id).first()
            if cs:
                ps = dict(cs.prep_state) if isinstance(cs.prep_state, dict) else {}
                fallback = ps.get('_intake_session', None)
                if fallback:
                    session['intake'] = fallback
                    return fallback
    except Exception:
        pass
    return None


def _save_session_state(state: Dict) -> None:
    """Сохранить состояние в сессию и в CuratorState как fallback."""
    from flask import session
    from flask_login import current_user
    session['intake'] = state
    try:
        from models_curator import CuratorState
        from models import db
        if current_user and current_user.is_authenticated:
            cs = CuratorState.query.filter_by(user_id=current_user.id).first()
            if not cs:
                cs = CuratorState(user_id=current_user.id, prep_state={})
                db.session.add(cs)
            ps = dict(cs.prep_state) if isinstance(cs.prep_state, dict) else {}
            ps['_intake_session'] = state
            cs.prep_state = ps
            db.session.commit()
    except Exception:
        pass


def _call_set_prior(user_id: int, mu: float, sigma: float) -> None:
    """Вызвать set_prior в level_engine ОДИН раз до якорей."""
    try:
        from services.level_engine import set_prior
        set_prior(user_id, mu, sigma)
        logger.info(
            f"intake: set_prior called for user={user_id} mu={mu:.2f} sigma={sigma:.2f}"
        )
    except Exception as e:
        logger.warning(f"intake: set_prior failed for user={user_id}: {e}")


def _clear_session_state() -> None:
    """Очистить состояние анкеты из сессии."""
    from flask import session
    from flask_login import current_user
    session.pop('intake', None)
    try:
        from models_curator import CuratorState
        if current_user and current_user.is_authenticated:
            cs = CuratorState.query.filter_by(user_id=current_user.id).first()
            if cs:
                ps = dict(cs.prep_state) if isinstance(cs.prep_state, dict) else {}
                ps.pop('_intake_session', None)
                cs.prep_state = ps
                from models import db
                db.session.commit()
    except Exception:
        pass


def _get_user_grade(user_id: int) -> Optional[int]:
    """Получить класс ученика из профиля."""
    from models import db, User
    user = db.session.get(User, user_id)
    if user is None:
        return None
    grade = getattr(user, 'preferred_grade', None) or getattr(user, 'grade', None)
    try:
        return int(grade) if grade is not None else None
    except (TypeError, ValueError):
        return None


def _format_question(qdef: Dict) -> Dict:
    """Форматировать определение вопроса для API."""
    return {
        'id': qdef['id'],
        'text': qdef['text'],
        'options': [
            {'key': o['key'], 'label': o['label']}
            for o in qdef['options']
        ],
        'multi': qdef.get('multi', False),
    }


# ══════════════════════════════════════════════════════════════════════
# Публичный API
# ══════════════════════════════════════════════════════════════════════

def _save_non_student_role(user_id: int, role: str) -> None:
    """Сохранить роль teacher/parent в User.role и отметку onboarded_at."""
    from models import db, User
    user = db.session.get(User, user_id)
    if user is not None:
        user.role = role
        from datetime import datetime as _dt
        if not user.onboarded_at:
            user.onboarded_at = _dt.utcnow()
        db.session.commit()
        logger.info(
            f"intake: user={user_id} set role={role}, onboarded_at set"
        )


def start(user_id: int) -> Dict[str, Any]:
    """Начать анкету. Возвращает первый вопрос.

    Если класс уже известен из профиля — Q1 пропускается.
    """
    grade_from_profile = _get_user_grade(user_id)

    state = {
        'step': 'q1',
        'q_index': 1,          # 1-based index for progress display
        'total_questions': 5,
        'answers': {},
        'anchor_tasks': [],
        'anchor_results': [],
        'anchor_task_ids': [],
        'anchor_sections': [],
        'current_anchor_idx': 0,
    }

    if grade_from_profile is not None:
        state['answers']['class'] = str(grade_from_profile)
        state['step'] = 'q2'
        state['q_index'] = 2
        _save_session_state(state)
        return {
            'done': False,
            'question': _format_question(Q2_GOAL),
            'step': 'q2',
            'q_index': 2,
            'total_questions': 5,
            'grade_auto': grade_from_profile,
        }

    _save_session_state(state)
    return {
        'done': False,
        'question': _format_question(Q1_CLASS),
        'step': 'q1',
        'q_index': 1,
        'total_questions': 5,
    }


def answer(user_id: int, qid: str, key: str) -> Dict[str, Any]:
    """Записать ответ на вопрос и вернуть следующий шаг."""
    state = _get_session_state()
    if not state:
        return {'done': True, 'error': 'Сессия истекла. Начните заново.'}

    state['answers'][qid] = key
    current_step = state['step']

    # ── Q1: проверяем, не выбрал ли пользователь teacher/parent ─────
    if current_step == 'q1' and qid == 'class' and key in NON_STUDENT_ROLE_KEYS:
        # Сохраняем роль в БД
        _save_non_student_role(user_id, key)
        _clear_session_state()
        redirect_url = (
            '/teacher' if key == TEACHER_ROLE_KEY
            else '/parent'
        )
        return {
            'done': True,
            'role': key,
            'redirect_url': redirect_url,
            'message': (
                'Вы зарегистрированы как учитель. Добро пожаловать в панель учителя!'
                if key == TEACHER_ROLE_KEY
                else 'Вы зарегистрированы как родитель. Добро пожаловать в панель родителя!'
            ),
        }

    # ── Flow: q1 -> q2 -> q3 -> q4 -> q5 -> anchors ──────────────────

    transitions = {
        'q1': ('q2', Q2_GOAL, 2),
        'q2': ('q3', Q3_EXPERIENCE, 3),
        'q3': ('q4', Q4_TIME, 4),
        'q4': ('q5', Q5_WEAK_SECTIONS, 5),
    }

    if current_step in transitions:
        next_step, next_q, qi = transitions[current_step]
        state['step'] = next_step
        state['q_index'] = qi
        _save_session_state(state)
        return {
            'done': False,
            'question': _format_question(next_q),
            'step': next_step,
            'q_index': qi,
            'total_questions': 5,
            'anchor': None,
        }

    # ── q5 -> выбираем якоря и показываем первый ──────────────────
    if current_step == 'q5' and qid == 'weak_sections':
        # Выбираем 5 якорей
        grade = int(state['answers'].get('class', 9))
        state['step'] = 'anchors'
        state['q_index'] = 6  # "шаг 6 из 10"
        state['total_questions'] = 10  # 5 вопросов + 5 якорей

        from services.intake_questions import EXPERIENCE_PRIOR
        exp_key = state['answers'].get('experience', 'none')
        exp_opt = EXPERIENCE_PRIOR.get(exp_key, EXPERIENCE_PRIOR["none"])
        mu = exp_opt["mu"]
        sigma = 1.35 if exp_opt["w"] >= 0.8 else 1.9

        # ── set_prior ДО первого якоря (как требует ТЗ) ──────────
        _call_set_prior(user_id, mu, sigma)

        # Use anchors.pick_anchors for the canonical anchored tasks
        anchor_tasks, anchor_meta = pick_anchors(grade)

        if not anchor_tasks:
            logger.warning(f"intake: no anchors for grade={grade}")
            state['anchors_unavailable'] = True
            _save_session_state(state)
            return finish(user_id, state)

        state['anchor_tasks'] = anchor_tasks
        state['anchor_task_ids'] = [a['db_id'] for a in anchor_tasks]
        state['anchor_sections'] = [a['section'] for a in anchor_tasks]
        state['current_anchor_idx'] = 0
        _save_session_state(state)

        return _format_anchor_response(state, 0)

    # ── anchors: уже внутри якорного этапа ───────────────────────
    if current_step == 'anchors':
        return {'done': False, 'error': 'Используйте submit_anchor для якорей.'}

    return {'done': True, 'error': f'Неизвестный шаг: {current_step}'}


def submit_anchor(user_id: int, task_id: int, user_answer: str) -> Dict[str, Any]:
    """Проверить ответ на якорную задачу и вернуть следующую."""
    state = _get_session_state()
    if not state or state['step'] != 'anchors':
        return {'done': True, 'error': 'Нет активной анкеты.'}

    idx = state['current_anchor_idx']
    anchor_tasks = state.get('anchor_tasks', [])

    if idx >= len(anchor_tasks):
        return finish(user_id, state)

    current_anchor = anchor_tasks[idx]
    correct_answer = current_anchor.get('answer', '')
    is_correct = check_anchor_answer(user_answer, correct_answer)

    state['anchor_results'].append({
        'task_id': current_anchor['db_id'],
        'correct': is_correct,
        'section': current_anchor['section'],
        'level': current_anchor.get('level', 1),
        'user_answer': user_answer,
    })

    idx += 1
    state['current_anchor_idx'] = idx
    state['q_index'] = 6 + idx  # 6, 7, 8, 9, 10

    if idx >= len(anchor_tasks):
        # Все якоря пройдены -> финал
        _save_session_state(state)
        return finish(user_id, state)

    _save_session_state(state)
    return _format_anchor_response(state, idx)


def _format_anchor_response(state: Dict, idx: int) -> Dict[str, Any]:
    """Сформировать ответ с якорной задачей."""
    anchor = state['anchor_tasks'][idx]
    return {
        'done': False,
        'question': None,
        'step': 'anchors',
        'q_index': 6 + idx,
        'total_questions': 10,
        'anchor': {
            'task_id': anchor['db_id'],
            'statement': anchor['statement'],
            'section': anchor['section'],
            'section_ru': {
                'algebra': 'Алгебра',
                'number_theory': 'Теория чисел',
                'geometry': 'Геометрия',
                'combinatorics': 'Комбинаторика',
                'logic': 'Логика',
            }.get(anchor['section'], anchor['section']),
            'anchor_idx': idx + 1,
            'total_anchors': len(state['anchor_tasks']),
            'figure_url': anchor.get('figure_url'),
            'solution': anchor.get('solution', ''),
            'answer': anchor.get('answer', ''),
        },
    }


def finish(user_id: int, state: Optional[Dict] = None) -> Dict[str, Any]:
    """Финализировать анкету: вычислить prior, сохранить в БД.

    Сохраняет в CuratorState.prep_state.intake:
      - answers (все ответы анкеты)
      - goal, goal_auto
      - daily_tasks (дневная норма)
      - weak_sections, weak_priority
      - prior_mu, prior_sigma
      - anchor_results
      - completed_at
    """
    if state is None:
        state = _get_session_state()
    if not state:
        return {'done': True, 'error': 'Нет данных анкеты.'}

    # Вычисляем результат
    result = compute_prior(state.get('answers', {}), state.get('anchor_results', []))

    # Собираем решения всех 5 якорей для финального показа
    anchor_solutions = []
    anchor_tasks = state.get('anchor_tasks', [])
    anchor_results = state.get('anchor_results', [])
    for i, task in enumerate(anchor_tasks):
        user_correct = None
        if i < len(anchor_results):
            user_correct = anchor_results[i].get('correct')
        anchor_solutions.append({
            'section': task.get('section', ''),
            'section_ru': {
                'algebra': 'Алгебра',
                'number_theory': 'Теория чисел',
                'geometry': 'Геометрия',
                'combinatorics': 'Комбинаторика',
                'logic': 'Логика',
            }.get(task.get('section', ''), task.get('section', '')),
            'statement': task.get('statement', ''),
            'answer': task.get('answer', ''),
            'solution': task.get('solution', ''),
            'correct': user_correct,
        })

    # Сохраняем в БД
    _save_intake_to_db(user_id, result, state)

    # Очищаем сессию
    _clear_session_state()

    return {
        'done': True,
        'result': {
            'class_level': result.class_level,
            'goal': result.goal,
            'goal_auto': result.goal_auto,
            'experience': result.experience,
            'daily_tasks': result.daily_tasks,
            'weak_sections': result.weak_sections,
            'weak_priority': result.weak_priority,
            'prior_mu': result.prior_mu,
            'prior_sigma': result.prior_sigma,
            'anchors_count': len(result.anchors),
            'anchors_correct': sum(1 for a in result.anchors if a.get('correct')),
            'anchor_solutions': anchor_solutions,
        },
    }


def _save_intake_to_db(user_id: int, result: IntakeResult, state: Dict) -> None:
    """Сохранить результат анкеты в CuratorState.prep_state.intake."""
    from models import db
    from models_curator import CuratorState

    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if cs is None:
        cs = CuratorState(user_id=user_id)
        db.session.add(cs)

    prep_state = dict(cs.prep_state) if isinstance(cs.prep_state, dict) else {}

    prep_state['intake'] = {
        'completed': True,
        'completed_at': datetime.utcnow().isoformat(),
        'class_level': result.class_level,
        'goal': result.goal,
        'goal_auto': result.goal_auto,
        'experience': result.experience,
        'daily_tasks': result.daily_tasks,
        'weak_sections': result.weak_sections,
        'weak_priority': result.weak_priority,
        'prior_mu': result.prior_mu,
        'prior_sigma': result.prior_sigma,
        'answers': state.get('answers', {}),
        'anchor_results': state.get('anchor_results', []),
    }

    cs.prep_state = prep_state
    cs.onboarding_done = True

    # Также сохраняем grade и daily_tasks в User и CuratorState
    if result.class_level:
        try:
            from models import User
            user = db.session.get(User, user_id)
            if user and not user.preferred_grade:
                user.preferred_grade = int(result.class_level)
        except Exception:
            pass

    cs.grade = result.class_level
    db.session.commit()
    logger.info(
        f"intake saved: user={user_id} class={result.class_level} "
        f"goal={result.goal} auto={result.goal_auto} "
        f"daily={result.daily_tasks} weak={result.weak_sections} "
        f"mu={result.prior_mu} sigma={result.prior_sigma}"
    )
