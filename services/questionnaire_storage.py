# -*- coding: utf-8 -*-
"""
Хранение состояния анкеты.
Сохраняется в БД через CuratorState.prep_state (раздел questionnaire).
"""

from datetime import datetime


def init_questionnaire(total):
    """Инициализировать анкету — сохраняет total в сессию Flask."""
    from flask import session
    session['questionnaire'] = {
        'active': True,
        'current_index': 0,
        'total': total,
        'answers': {},
    }


def get_questionnaire_state():
    """Получить текущее состояние анкеты из Flask-сессии."""
    from flask import session
    return session.get('questionnaire', {})


def save_questionnaire_state(state):
    """Сохранить состояние анкеты в Flask-сессию."""
    from flask import session
    session['questionnaire'] = state


def save_questionnaire_result_to_db(user_id, level, answers):
    """Сохранить результат анкеты в CuratorState.

    Записывает в prep_state раздел `questionnaire`:
    {
        "questionnaire": {
            "completed": true,
            "level": 3,
            "answers": {...},
            "completed_at": "2026-07-26T..."
        }
    }
    И обновляет grade, goal_text, onboarding_done.
    """
    from models import db
    from models_curator import CuratorState

    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if cs is None:
        cs = CuratorState(user_id=user_id)
        db.session.add(cs)

    prep_state = getattr(cs, 'prep_state', None) or {}
    if not isinstance(prep_state, dict):
        prep_state = {}

    prep_state['questionnaire'] = {
        'completed': True,
        'level': int(level),
        'answers': dict(answers) if answers else {},
        'completed_at': datetime.utcnow().isoformat(),
    }
    cs.prep_state = prep_state
    cs.onboarding_done = True

    # Сохраняем цель
    goal = str(answers.get('goal_text', '')) if answers else ''
    if goal and not cs.goal_text:
        cs.goal_text = goal

    db.session.commit()


def get_questionnaire_level(user_id):
    """Получить уровень из анкеты (1-5), или None если анкета не пройдена."""
    from models_curator import CuratorState
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs:
        return None
    prep_state = getattr(cs, 'prep_state', None) or {}
    if not isinstance(prep_state, dict):
        return None
    q = prep_state.get('questionnaire') or {}
    if q.get('completed') and q.get('level'):
        return int(q['level'])
    return None
