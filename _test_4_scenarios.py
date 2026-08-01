# -*- coding: utf-8 -*-
"""
ШАГ 5: 4 сценария полного прохождения онбординга через HTTP.

A. Оба якоря верно
B. Оба якоря неверно  
C. Первый верно, второй неверно
D. Ответы фразой и пустой строкой
"""
import json
import os
import sys
import copy

os.environ['ENABLE_SCHEDULER'] = '0'

from app import app, db
from models import User, AdaptiveTask
from models_curator import CuratorState

app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False

TEST_USER_ID = 3


def fresh_session():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(TEST_USER_ID)
        sess['_fresh'] = True
        sess['_id'] = f'test-session-{os.urandom(4).hex()}'
        sess['csrf_token'] = 'test-csrf'
    with client.session_transaction() as sess:
        sess.pop('onboarding', None)
    return client


def _clear_onboarding_state():
    """Clear onboarding state from DB for user 3."""
    cs = CuratorState.query.filter_by(user_id=TEST_USER_ID).first()
    if cs:
        cs.onboarding_done = False
        ps = dict(cs.prep_state) if cs.prep_state else {}
        ps.pop('onboarding', None)
        ps.pop('test_queue', None)
        cs.prep_state = ps
        cs.level_mu = None
        cs.level_sigma = None
        cs.level_by_section = None
        cs.level_updated_at = None
        db.session.commit()


def walk_to_anchor(client):
    """Walk through Q1-Q4 and return (client, anchor_task_id) or (client, None)."""
    # _start
    r = client.post('/prep/onboarding/answer',
                    data=json.dumps({"qid": "_start", "key": "_start"}),
                    content_type='application/json')
    assert r.status_code == 200

    # Q1
    r = client.post('/prep/onboarding/answer',
                    data=json.dumps({"qid": "goal", "key": "olympiad"}),
                    content_type='application/json')
    data = r.get_json()
    assert data.get('step') == 'q2'

    # Q2
    q2_id = data['question']['id']
    q2_key = data['question']['options'][len(data['question']['options'])//2]['key']
    r = client.post('/prep/onboarding/answer',
                    data=json.dumps({"qid": q2_id, "key": q2_key}),
                    content_type='application/json')
    data = r.get_json()
    assert data.get('step') == 'q3'

    # Q3
    q3_id = data['question']['id']
    q3_key = data['question']['options'][0]['key']
    r = client.post('/prep/onboarding/answer',
                    data=json.dumps({"qid": q3_id, "key": q3_key}),
                    content_type='application/json')
    data = r.get_json()
    assert data.get('step') == 'q4'

    # Q4
    q4_id = data['question']['id']
    q4_key = data['question']['options'][0]['key']
    r = client.post('/prep/onboarding/answer',
                    data=json.dumps({"qid": q4_id, "key": q4_key}),
                    content_type='application/json')
    data = r.get_json()

    if data.get('anchor'):
        return client, data['anchor']['task_id']
    elif data.get('anchors_unavailable'):
        return client, None
    else:
        raise Exception(f"Unexpected after Q4: {json.dumps(data, ensure_ascii=False)}")


def fmt(data):
    """Format response data, truncating task_text for readability."""
    if not isinstance(data, dict):
        return str(data)[:2000]
    d = copy.deepcopy(data)
    if 'question' in d and isinstance(d['question'], dict):
        pass  # keep
    if 'anchor' in d and isinstance(d['anchor'], dict):
        if 'task_text' in d['anchor']:
            d['anchor']['task_text'] = d['anchor']['task_text'][:80] + '…'
    if 'result' in d and isinstance(d['result'], dict):
        pass
    return json.dumps(d, indent=2, ensure_ascii=False, default=str)


with app.app_context():
    user = db.session.get(User, TEST_USER_ID)
    if not user:
        print(f"User {TEST_USER_ID} not found")
        sys.exit(1)

    grade = (getattr(user, 'preferred_grade', None)
             or getattr(user, 'class_level', None)
             or getattr(user, 'grade', None))
    print(f"User {TEST_USER_ID}: grade={grade}")
    print()

    # =====================================================================
    # СЦЕНАРИЙ A: оба якоря верно
    # =====================================================================
    print("=" * 80)
    print("СЦЕНАРИЙ A: оба якоря верно")
    print("=" * 80)
    _clear_onboarding_state()

    client, task1_id = walk_to_anchor(fresh_session())
    assert task1_id is not None, "Anchor1 missing!"
    task1 = db.session.get(AdaptiveTask, task1_id)
    a1_correct = task1.correct_answer if task1 else "???"

    # Anchor 1 — верно
    r = client.post('/prep/onboarding/anchor',
                    data=json.dumps({"task_id": task1_id, "answer": a1_correct}),
                    content_type='application/json')
    data1 = r.get_json()
    print(f"\n[POST /onboarding/anchor task1={task1_id} answer='{a1_correct}']")
    print(f"Response: {fmt(data1)}")

    if data1.get('anchor'):
        task2_id = data1['anchor']['task_id']
        task2 = db.session.get(AdaptiveTask, task2_id)
        a2_correct = task2.correct_answer if task2 else "???"
        assert data1['step'] == 'anchor2'

        # Anchor 2 — верно
        r = client.post('/prep/onboarding/anchor',
                        data=json.dumps({"task_id": task2_id, "answer": a2_correct}),
                        content_type='application/json')
        data2 = r.get_json()
        print(f"\n[POST /onboarding/anchor task2={task2_id} answer='{a2_correct}']")
        print(f"Response: {fmt(data2)}")

        # Finish
        r = client.post('/prep/onboarding/answer',
                        data=json.dumps({"qid": "_finish", "key": "_finish"}),
                        content_type='application/json')
        finished = r.get_json()
        print(f"\n[POST /onboarding/answer _finish]")
        print(f"Response: {fmt(finished)}")
    elif data1.get('anchor_done') or data1.get('finish_ready'):
        # Anchor2 skipped — finish
        r = client.post('/prep/onboarding/answer',
                        data=json.dumps({"qid": "_finish", "key": "_finish"}),
                        content_type='application/json')
        finished = r.get_json()
        print(f"\n[Anchor2 skipped, _finish]")
        print(f"Response: {fmt(finished)}")

    cs = CuratorState.query.filter_by(user_id=TEST_USER_ID).first()
    if cs:
        ps = cs.prep_state or {}
        print(f"\nDB prep_state['onboarding']: {json.dumps(ps.get('onboarding', {}), indent=2, ensure_ascii=False, default=str)}")
        print(f"DB prep_state['test_queue']: {json.dumps(ps.get('test_queue', []), indent=2, ensure_ascii=False, default=str)}")

    # =====================================================================
    # СЦЕНАРИЙ B: оба якоря неверно
    # =====================================================================
    print("\n" + "=" * 80)
    print("СЦЕНАРИЙ B: оба якоря неверно")
    print("=" * 80)
    _clear_onboarding_state()

    client, task1_id = walk_to_anchor(fresh_session())
    assert task1_id is not None, "Anchor1 missing!"

    # Anchor 1 — неверно
    r = client.post('/prep/onboarding/anchor',
                    data=json.dumps({"task_id": task1_id, "answer": "неправильный_ответ_999"}),
                    content_type='application/json')
    data1 = r.get_json()
    print(f"\n[POST /onboarding/anchor task1={task1_id} answer='неправильный_ответ_999']")
    print(f"Response: {fmt(data1)}")

    if data1.get('anchor'):
        task2_id = data1['anchor']['task_id']
        # Anchor 2 — неверно
        r = client.post('/prep/onboarding/anchor',
                        data=json.dumps({"task_id": task2_id, "answer": "тоже_неправильно"}),
                        content_type='application/json')
        data2 = r.get_json()
        print(f"\n[POST /onboarding/anchor task2={task2_id} answer='тоже_неправильно']")
        print(f"Response: {fmt(data2)}")

        # Finish
        r = client.post('/prep/onboarding/answer',
                        data=json.dumps({"qid": "_finish", "key": "_finish"}),
                        content_type='application/json')
        finished = r.get_json()
        print(f"\n[POST /onboarding/answer _finish]")
        print(f"Response: {fmt(finished)}")
    elif data1.get('anchor_done') or data1.get('finish_ready'):
        r = client.post('/prep/onboarding/answer',
                        data=json.dumps({"qid": "_finish", "key": "_finish"}),
                        content_type='application/json')
        finished = r.get_json()
        print(f"\n[Anchor2 skipped, _finish]")
        print(f"Response: {fmt(finished)}")

    cs = CuratorState.query.filter_by(user_id=TEST_USER_ID).first()
    if cs:
        ps = cs.prep_state or {}
        print(f"\nDB prep_state['onboarding']: {json.dumps(ps.get('onboarding', {}), indent=2, ensure_ascii=False, default=str)}")
        print(f"DB prep_state['test_queue']: {json.dumps(ps.get('test_queue', []), indent=2, ensure_ascii=False, default=str)}")

    # =====================================================================
    # СЦЕНАРИЙ C: первый верно, второй неверно
    # =====================================================================
    print("\n" + "=" * 80)
    print("СЦЕНАРИЙ C: первый верно, второй неверно")
    print("=" * 80)
    _clear_onboarding_state()

    client, task1_id = walk_to_anchor(fresh_session())
    assert task1_id is not None, "Anchor1 missing!"
    task1 = db.session.get(AdaptiveTask, task1_id)
    a1_correct = task1.correct_answer if task1 else "???"

    # Anchor 1 — верно
    r = client.post('/prep/onboarding/anchor',
                    data=json.dumps({"task_id": task1_id, "answer": a1_correct}),
                    content_type='application/json')
    data1 = r.get_json()
    print(f"\n[POST /onboarding/anchor task1={task1_id} answer='{a1_correct}']")
    print(f"Response: {fmt(data1)}")

    if data1.get('anchor'):
        task2_id = data1['anchor']['task_id']
        # Anchor 2 — неверно
        r = client.post('/prep/onboarding/anchor',
                        data=json.dumps({"task_id": task2_id, "answer": "неправильно"}),
                        content_type='application/json')
        data2 = r.get_json()
        print(f"\n[POST /onboarding/anchor task2={task2_id} answer='неправильно']")
        print(f"Response: {fmt(data2)}")

        r = client.post('/prep/onboarding/answer',
                        data=json.dumps({"qid": "_finish", "key": "_finish"}),
                        content_type='application/json')
        finished = r.get_json()
        print(f"\n[POST /onboarding/answer _finish]")
        print(f"Response: {fmt(finished)}")
    elif data1.get('anchor_done') or data1.get('finish_ready'):
        r = client.post('/prep/onboarding/answer',
                        data=json.dumps({"qid": "_finish", "key": "_finish"}),
                        content_type='application/json')
        finished = r.get_json()
        print(f"\n[Anchor2 skipped, _finish]")
        print(f"Response: {fmt(finished)}")

    cs = CuratorState.query.filter_by(user_id=TEST_USER_ID).first()
    if cs:
        ps = cs.prep_state or {}
        print(f"\nDB prep_state['onboarding']: {json.dumps(ps.get('onboarding', {}), indent=2, ensure_ascii=False, default=str)}")
        print(f"DB prep_state['test_queue']: {json.dumps(ps.get('test_queue', []), indent=2, ensure_ascii=False, default=str)}")

    # =====================================================================
    # СЦЕНАРИЙ D: ответы фразой и пустой строкой
    # =====================================================================
    print("\n" + "=" * 80)
    print("СЦЕНАРИЙ D: ответы фразой и пустой строкой")
    print("=" * 80)
    _clear_onboarding_state()

    client, task1_id = walk_to_anchor(fresh_session())
    assert task1_id is not None, "Anchor1 missing!"

    # Anchor 1 — фразой
    r = client.post('/prep/onboarding/anchor',
                    data=json.dumps({"task_id": task1_id, "answer": "таких n нету"}),
                    content_type='application/json')
    data1 = r.get_json()
    print(f"\n[POST /onboarding/anchor task1={task1_id} answer='таких n нету']")
    print(f"Response: {fmt(data1)}")

    if data1.get('anchor'):
        task2_id = data1['anchor']['task_id']
        # Anchor 2 — пустой строкой
        r = client.post('/prep/onboarding/anchor',
                        data=json.dumps({"task_id": task2_id, "answer": ""}),
                        content_type='application/json')
        data2 = r.get_json()
        print(f"\n[POST /onboarding/anchor task2={task2_id} answer='' (empty)]")
        print(f"Response: {fmt(data2)}")

        r = client.post('/prep/onboarding/answer',
                        data=json.dumps({"qid": "_finish", "key": "_finish"}),
                        content_type='application/json')
        finished = r.get_json()
        print(f"\n[POST /onboarding/answer _finish]")
        print(f"Response: {fmt(finished)}")
    elif data1.get('anchor_done') or data1.get('finish_ready'):
        r = client.post('/prep/onboarding/answer',
                        data=json.dumps({"qid": "_finish", "key": "_finish"}),
                        content_type='application/json')
        finished = r.get_json()
        print(f"\n[Anchor2 skipped, _finish]")
        print(f"Response: {fmt(finished)}")

    cs = CuratorState.query.filter_by(user_id=TEST_USER_ID).first()
    if cs:
        ps = cs.prep_state or {}
        print(f"\nDB prep_state['onboarding']: {json.dumps(ps.get('onboarding', {}), indent=2, ensure_ascii=False, default=str)}")
        print(f"DB prep_state['test_queue']: {json.dumps(ps.get('test_queue', []), indent=2, ensure_ascii=False, default=str)}")

    # =====================================================================
    # VERIFICATION: GET /prep/onboarding = 200
    # =====================================================================
    print("\n" + "=" * 80)
    print("VERIFICATION: GET /prep/onboarding = 200")
    print("=" * 80)
    client = fresh_session()
    r = client.get('/prep/onboarding')
    print(f"GET /prep/onboarding → {r.status_code}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    print("✅ GET /prep/onboarding = 200 OK")

    print("\n" + "=" * 80)
    print("ВСЕ 4 СЦЕНАРИЯ ПРОЙДЕНЫ")
    print("=" * 80)
