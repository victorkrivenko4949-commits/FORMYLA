# -*- coding: utf-8 -*-
"""
routes/intake.py — Blueprint новой анкеты входа (P9 Intake).

Endpoints:
  GET  /intake           — страница анкеты (HTML)
  POST /intake/start     — начать анкету (JSON)
  POST /intake/answer    — записать ответ (JSON)
  POST /intake/anchor    — проверить якорь (JSON)
  POST /intake/back      — вернуться на шаг назад (JSON)
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from flask import Blueprint, jsonify, render_template, request, session
from flask_login import current_user, login_required

logger = logging.getLogger(__name__)

intake_bp = Blueprint('intake', __name__, url_prefix='/intake')


# ══════════════════════════════════════════════════════════════════════
# GET /intake — страница анкеты
# ══════════════════════════════════════════════════════════════════════

@intake_bp.route('/', methods=['GET'])
@login_required
def intake_page():
    """Страница анкеты входа."""
    # Если уже пройдена — редирект на /daily_tasks
    try:
        from models_curator import CuratorState
        cs = CuratorState.query.filter_by(user_id=current_user.id).first()
        if cs:
            ps = dict(cs.prep_state) if isinstance(cs.prep_state, dict) else {}
            if ps.get('intake', {}).get('completed'):
                from flask import redirect, url_for
                return redirect(url_for('index'))
    except Exception:
        pass

    return render_template('intake.html')


# ══════════════════════════════════════════════════════════════════════
# POST /intake/start
# ══════════════════════════════════════════════════════════════════════

@intake_bp.route('/start', methods=['POST'])
@login_required
def start_intake():
    """Начать анкету. Возвращает первый вопрос."""
    from services.intake_service import start
    result = start(current_user.id)
    return jsonify(result), 200


# ══════════════════════════════════════════════════════════════════════
# POST /intake/answer
# ══════════════════════════════════════════════════════════════════════

@intake_bp.route('/answer', methods=['POST'])
@login_required
def answer_intake():
    """Записать ответ на вопрос анкеты.

    Request JSON: {"qid": "goal", "key": "region"}
    """
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    qid = str(data.get('qid', '') or '')
    key = str(data.get('key', '') or '')

    if not qid or not key:
        return jsonify({'done': False, 'error': 'qid и key обязательны.'}), 400

    from services.intake_service import answer
    result = answer(current_user.id, qid, key)
    return jsonify(result), 200


# ══════════════════════════════════════════════════════════════════════
# POST /intake/anchor
# ══════════════════════════════════════════════════════════════════════

@intake_bp.route('/anchor', methods=['POST'])
@login_required
def submit_intake_anchor():
    """Проверить ответ на якорную задачу.

    Request JSON: {"task_id": 1234, "answer": "42"}
    """
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    task_id = data.get('task_id')
    user_answer = str(data.get('answer', '') or '')

    if not task_id or not user_answer:
        return jsonify({'done': False, 'error': 'task_id и answer обязательны.'}), 400

    from services.intake_service import submit_anchor
    result = submit_anchor(current_user.id, int(task_id), user_answer)
    return jsonify(result), 200


# ══════════════════════════════════════════════════════════════════════
# POST /intake/back
# ══════════════════════════════════════════════════════════════════════

@intake_bp.route('/back', methods=['POST'])
@login_required
def intake_back():
    """Вернуться на шаг назад без потери ответов.

    Возвращает предыдущий вопрос с сохранённым ответом.
    """
    from flask import session as flask_session

    state = flask_session.get('intake', None)
    if not state:
        return jsonify({'done': False, 'error': 'Нет активной анкеты.'}), 400

    current_step = state.get('step', 'q1')

    from services.intake_questions import (
        Q1_CLASS, Q2_GOAL, Q3_EXPERIENCE, Q4_TIME, Q5_WEAK_SECTIONS,
    )

    # Определяем предыдущий шаг
    steps = ['q1', 'q2', 'q3', 'q4', 'q5']
    if current_step not in steps:
        return jsonify({'done': False, 'error': f'Нельзя вернуться с шага {current_step}.'}), 400

    idx = steps.index(current_step)
    if idx == 0:
        return jsonify({'done': False, 'error': 'Вы на первом вопросе.'}), 400

    prev_step = steps[idx - 1]
    questions = {
        'q1': Q1_CLASS,
        'q2': Q2_GOAL,
        'q3': Q3_EXPERIENCE,
        'q4': Q4_TIME,
        'q5': Q5_WEAK_SECTIONS,
    }
    q_index = idx  # 1-based after going back

    state['step'] = prev_step
    state['q_index'] = q_index
    flask_session['intake'] = state

    prev_q = questions[prev_step]
    return jsonify({
        'done': False,
        'question': {
            'id': prev_q['id'],
            'text': prev_q['text'],
            'options': [{'key': o['key'], 'label': o['label']} for o in prev_q['options']],
            'multi': prev_q.get('multi', False),
        },
        'step': prev_step,
        'q_index': q_index,
        'total_questions': 5,
        'saved_answer': state['answers'].get(prev_q['id'], None),
        'anchor': None,
    }), 200
