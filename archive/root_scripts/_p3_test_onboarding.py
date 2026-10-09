# -*- coding: utf-8 -*-
"""p3_test_onboarding.py — доказывает П3.6 через app.test_client()."""
import sys, os, json, io

sys.path.insert(0, os.path.dirname(__file__))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app import app, db
from models import User
from models_curator import CuratorState

# ─── Helpers ────────────────────────────────────────────────────────
def create_user(email, grade=9):
    """Создать пользователя и записать его в БД."""
    with app.app_context():
        u = User(email=email, preferred_grade=grade)
        u.password_hash = 'test_hash'
        db.session.add(u)
        db.session.commit()
        uid = u.id
    return uid

def delete_user(user_id):
    with app.app_context():
        u = db.session.get(User, user_id)
        if u:
            db.session.delete(u)
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if cs:
            db.session.delete(cs)
        db.session.commit()

def login(client, email):
    """Залогиниться через сессию."""
    with app.app_context():
        u = User.query.filter_by(email=email).first()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(u.id)
        sess['_fresh'] = True
    return u.id

# ─── PATH A: /prep/onboarding (new tree-based) ─────────────────────
def path_onboarding(email):
    """Пройти новую анкету через /prep/onboarding/answer."""
    with app.test_client() as c:
        uid = login(c, email)

        # _start — инициализация
        r = c.post('/prep/onboarding/answer',
                   json={'qid': '_start', 'key': ''})
        data = r.get_json()
        assert 'question' in data or 'next' in data or 'error' not in data, f'start failed: {data}'
        print(f'[_start] status={r.status_code} keys={list(data.keys()) if data else "none"}')

        # Проходим все вопросы, отвечая дефолтными значениями
        # onboarding tree: questions come with options, we pick first option
        attempts = 0
        while attempts < 30:
            attempts += 1
            if data.get('done') or data.get('finished'):
                print(f'  -> finished after {attempts} steps')
                break

            qid = data.get('qid') or data.get('id') or data.get('question_id')
            options = data.get('options') or []
            key = options[0].get('key', 'default') if options else 'default'
            if not qid:
                print(f'  -> no qid, data={json.dumps(data, ensure_ascii=False)[:200]}')
                break

            r = c.post('/prep/onboarding/answer',
                       json={'qid': qid, 'key': key})
            data = r.get_json() or {}
            if attempts % 3 == 0:
                print(f'  step {attempts}: qid={qid} key={key} -> status={r.status_code}')

        # _finish
        r = c.post('/prep/onboarding/answer',
                   json={'qid': '_finish', 'key': ''})
        data = r.get_json()
        print(f'[_finish] status={r.status_code} keys={list(data.keys()) if data else "none"}')
        if data:
            print(f'  result: {json.dumps(data, ensure_ascii=False, default=str)[:400]}')

        # Get prep_state
        with app.app_context():
            cs = CuratorState.query.filter_by(user_id=uid).first()
            if cs and cs.prep_state:
                ps = cs.prep_state if isinstance(cs.prep_state, dict) else json.loads(cs.prep_state)
                return ps, cs.onboarding_done
        return {}, False

# ─── PATH B: chat curator (coach_chat questionnaire) ───────────────
def path_chat_curator(email):
    """Пройти анкету через чат куратора."""
    with app.test_client() as c:
        uid = login(c, email)

        # Send "привет" to trigger greeting
        r = c.post('/prep/coach/chat', json={'message': 'привет'})
        data = r.get_json()
        print(f'[chat:привет] reply={data.get("reply","")[:80]}')

        # The greeting may trigger onboarding test or questionnaire.
        # If scenario == start_questionnaire, we need to answer questions.
        # Check what the response contains
        for i in range(10):
            r = c.post('/prep/coach/chat', json={'message': f'ответ {i+1}'})
            data = r.get_json()
            reply = data.get('reply', '')[:150]
            done_flag = data.get('done') or data.get('questionnaire_done')
            print(f'[chat:step{i+1}] done={done_flag} reply={reply[:80]}')
            if done_flag:
                break

        # Get prep_state
        with app.app_context():
            cs = CuratorState.query.filter_by(user_id=uid).first()
            if cs and cs.prep_state:
                ps = cs.prep_state if isinstance(cs.prep_state, dict) else json.loads(cs.prep_state)
                return ps, cs.onboarding_done
        return {}, False

# ─── MAIN ──────────────────────────────────────────────────────────
print('=' * 60)
print('P3.6: Proof via app.test_client()')
print('=' * 60)

email_a = 'test_onb_tree@formyla.test'
uid_a = create_user(email_a, 9)
print(f'\n=== PATH A: onboarding tree (user {uid_a}) ===')
try:
    ps_a, od_a = path_onboarding(email_a)
    print(f'\n  onboarding_done = {od_a}')
    print(f'  prep_state keys: {sorted(ps_a.keys())}')
    if 'onboarding' in ps_a:
        ob = ps_a['onboarding']
        print(f'  onboarding subkeys ({len(ob)}): {sorted(ob.keys())}')
        print(f'    daily_tasks  = {ob.get("daily_tasks")}')
        print(f'    route_ceiling = {ob.get("route_ceiling")}')
        print(f'    test_length  = {ob.get("test_length")}')
        print(f'    grade         = {ob.get("grade")}')
        print(f'    target_level  = {ob.get("target_level")}')
finally:
    delete_user(uid_a)

email_b = 'test_chat_curator@formyla.test'
uid_b = create_user(email_b, 9)
print(f'\n=== PATH B: chat curator (user {uid_b}) ===')
try:
    ps_b, od_b = path_chat_curator(email_b)
    print(f'\n  onboarding_done = {od_b}')
    print(f'  prep_state keys: {sorted(ps_b.keys())}')
    if 'onboarding' in ps_b:
        ob = ps_b['onboarding']
        print(f'  onboarding subkeys ({len(ob)}): {sorted(ob.keys())}')
        print(f'    daily_tasks  = {ob.get("daily_tasks")}')
        print(f'    route_ceiling = {ob.get("route_ceiling")}')
        print(f'    test_length  = {ob.get("test_length")}')
        print(f'    grade         = {ob.get("grade")}')
        print(f'    target_level  = {ob.get("target_level")}')
finally:
    delete_user(uid_b)

print()
print('=' * 60)
print('P3.6 DONE')
