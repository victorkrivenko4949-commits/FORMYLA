# -*- coding: utf-8 -*-
"""Q6 «Готов заниматься регулярно?» в анкете: переходы q5 -> q6 -> anchors,
нумерация шагов 6/6 и 7..11 из 11, ответ сохраняется в intake.answers."""
import json

import pytest


@pytest.fixture
def intake_flow(app, monkeypatch):
    """Драйвит services.intake_service без HTTP, с state в памяти."""
    from services import intake_service as svc

    state_holder = {}
    monkeypatch.setattr(svc, '_get_session_state', lambda: state_holder.get('s'))
    monkeypatch.setattr(svc, '_save_session_state', lambda s: state_holder.__setitem__('s', s))
    monkeypatch.setattr(svc, '_clear_session_state', lambda: state_holder.pop('s', None))
    monkeypatch.setattr(svc, '_call_set_prior', lambda *a, **k: None)

    fake_anchors = [
        {'db_id': 9000 + i, 'statement': f'A{i}', 'section': 'algebra',
         'answer': '1', 'solution': 'sol', 'level': 1, 'figure_url': None}
        for i in range(5)
    ]
    monkeypatch.setattr(svc, 'pick_anchors', lambda grade: (fake_anchors, {}))
    monkeypatch.setattr(svc, 'check_anchor_answer', lambda a, b: str(a).strip() == str(b).strip())
    monkeypatch.setattr(svc, '_get_user_grade', lambda uid: 8)
    monkeypatch.setattr(svc, 'finish', lambda uid, state=None: {'done': True, 'result': {'answers': dict(state_holder['s']['answers'])}})
    return svc


def test_q6_flow(intake_flow):
    svc = intake_flow
    r = svc.start(user_id=1)
    assert r['question']['id'] == 'class' and r['total_questions'] == 6 and r['q_index'] == 1

    r = svc.answer(1, 'class', '8')
    assert r['step'] == 'q2' and r['q_index'] == 2 and r['total_questions'] == 6
    r = svc.answer(1, 'goal', 'region')
    assert r['step'] == 'q3' and r['q_index'] == 3
    r = svc.answer(1, 'experience', 'participated')
    assert r['step'] == 'q4' and r['q_index'] == 4
    r = svc.answer(1, 'time', 'm30')
    assert r['step'] == 'q5' and r['q_index'] == 5
    r = svc.answer(1, 'weak_sections', 'geometry')
    # теперь идёт Q6, а не якоря
    assert r['step'] == 'q6' and r['q_index'] == 6 and r['total_questions'] == 6
    assert r['question']['id'] == 'commitment'
    labels = [o['label'] for o in r['question']['options']]
    assert labels == ['Да, готов', 'Нет']

    r = svc.answer(1, 'commitment', 'yes')
    # якоря начинаются с шага 7 из 11
    assert r['step'] == 'anchors' and r['q_index'] == 7 and r['total_questions'] == 11
    assert r['anchor']['task_id'] == 9000

    idx_expected = 8
    for i in range(0, 5):
        r = svc.submit_anchor(1, 9000 + i, '1')
        if i < 4:
            assert r['q_index'] == idx_expected and r['total_questions'] == 11
            idx_expected += 1
    assert r['done'] is True
    assert r['result']['answers'].get('commitment') == 'yes'


def test_q6_answer_no_stored(intake_flow):
    svc = intake_flow
    svc.start(user_id=1)
    svc.answer(1, 'class', '8')
    svc.answer(1, 'goal', 'just_grow')
    svc.answer(1, 'experience', 'none')
    svc.answer(1, 'time', 'm30')
    svc.answer(1, 'weak_sections', 'dont_know')
    r = svc.answer(1, 'commitment', 'no')  # «Нет» не блокирует — просто сохраняется
    assert r['step'] == 'anchors'
    for i in range(5):
        r = svc.submit_anchor(1, 9000 + i, '0')
    assert r['done'] is True
    assert r['result']['answers'].get('commitment') == 'no'


def test_resume_at_q6(intake_flow):
    svc = intake_flow
    svc.start(user_id=1)
    svc.answer(1, 'class', '8')
    svc.answer(1, 'goal', 'region')
    svc.answer(1, 'experience', 'participated')
    svc.answer(1, 'time', 'm30')
    svc.answer(1, 'weak_sections', 'geometry')
    # перезагрузка страницы на шаге q6
    r = svc.start(user_id=1)
    assert r['step'] == 'q6' and r['q_index'] == 6 and r['total_questions'] == 6
    assert r['question']['id'] == 'commitment'
