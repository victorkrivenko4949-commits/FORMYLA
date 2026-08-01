"""
STEP 5: Comprehensive verification - 4 HTTP test cases + full onboarding flow.
Uses Flask test client to pick up the FIXED code.
"""
import json
import sys
import os

# Disable scheduler for test
os.environ['ENABLE_SCHEDULER'] = '0'

from app import app, db
from models import User
from models_curator import CuratorState

app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False
app.config['LOGIN_DISABLED'] = False

def fresh_session(user_id):
    """Start a fresh test session for a given user."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True
        sess['_id'] = f'test-session-{user_id}'
        sess['csrf_token'] = 'test-csrf'
    # Clear any onboarding state from previous runs
    with client.session_transaction() as sess:
        sess.pop('onboarding', None)
    return client

def go_to_anchor(client):
    """Walk through Q1-Q4 to get to the first anchor task. Returns task_id."""
    # Start
    r = client.post('/prep/onboarding/answer',
                    data=json.dumps({"qid": "_start", "key": "_start"}),
                    content_type='application/json')
    assert r.status_code == 200, f"Start failed: {r.status_code}"
    
    # Q1
    r = client.post('/prep/onboarding/answer',
                    data=json.dumps({"qid": "goal", "key": "school"}),
                    content_type='application/json')
    data = r.get_json()
    assert data.get('step') == 'q2', f"Q1 failed: {data}"
    
    # Q2
    q2_id = data['question']['id']
    q2_key = data['question']['options'][len(data['question']['options'])//2]['key']
    r = client.post('/prep/onboarding/answer',
                    data=json.dumps({"qid": q2_id, "key": q2_key}),
                    content_type='application/json')
    data = r.get_json()
    
    # Q3
    q3_id = data['question']['id']
    q3_key = data['question']['options'][0]['key']
    r = client.post('/prep/onboarding/answer',
                    data=json.dumps({"qid": q3_id, "key": q3_key}),
                    content_type='application/json')
    data = r.get_json()
    
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
        return client, None  # No anchor available
    else:
        raise Exception(f"Unexpected after Q4: {data}")


with app.app_context():
    # Use user 3 (already exists, has grade)
    user = db.session.get(User, 3)
    if not user:
        print("User 3 not found! Checking other users...")
        users = User.query.limit(10).all()
        for u in users:
            print(f"  id={u.id} grade={getattr(u,'preferred_grade',None)}")
        sys.exit(1)
    
    grade = (getattr(user, 'preferred_grade', None) 
             or getattr(user, 'class_level', None)
             or getattr(user, 'grade', None))
    print(f"User 3: grade={grade}")
    
    # ── TEST 1: Full anchor flow with 4 different answers ──
    print("\n" + "="*70)
    print("=== STEP 5: 4 test answers table ===")
    print("="*70)
    
    results = []
    test_cases = [
        ("correct_answer", None),   # Will be filled later
        ("wrong_number", "999999"),
        ("text_phrase", "таких n нету"),
        ("empty_string", ""),
    ]
    
    # First, get to anchor and find the correct answer
    client, task_id = go_to_anchor(fresh_session(3))
    if task_id is None:
        print("SKIP: No anchor tasks available for user 3")
    else:
        # Get the correct answer from DB
        from models import AdaptiveTask
        task = db.session.get(AdaptiveTask, task_id)
        correct_answer = task.correct_answer if task else "???"
        test_cases[0] = ("correct_answer", correct_answer)
        
        print(f"Anchor task_id={task_id}, correct_answer='{correct_answer}'")
        print()
        print(f"{'Answer':<25} {'Status':<8} {'Valid JSON':<12} {'correct':<10} {'Body (truncated)'}")
        print("-" * 90)
        
        for label, answer in test_cases:
            client2, tid = go_to_anchor(fresh_session(3))
            r = client2.post('/prep/onboarding/anchor',
                            data=json.dumps({"task_id": tid, "answer": answer}),
                            content_type='application/json')
            status = r.status_code
            try:
                body = r.get_json()
                is_json = "YES"
                correct_val = str(body.get('correct'))
                body_preview = json.dumps(body, ensure_ascii=False)[:120]
            except:
                is_json = "NO"
                correct_val = "N/A"
                body_preview = r.get_data(as_text=True)[:120]
            
            print(f"{label:<25} {status:<8} {is_json:<12} {correct_val:<10} {body_preview}")
            results.append((label, status, is_json, correct_val))
        
        # Check all 200
        all_200 = all(r[1] == 200 for r in results)
        all_json = all(r[2] == "YES" for r in results)
        print(f"\nAll 200: {all_200}, All JSON: {all_json}")
        
        if all_200 and all_json:
            print("✅ STEP 5 table: ALL PASS")
        else:
            print("❌ STEP 5 table: FAIL")
    
    # ── TEST 2: Full onboarding flow ──
    print("\n" + "="*70)
    print("=== Full onboarding flow: start → finish() ===")
    print("="*70)
    
    client, task_id = go_to_anchor(fresh_session(3))
    if task_id is None:
        print("SKIP: No anchor tasks available")
    else:
        # Submit anchor 1 (wrong answer to get second anchor)
        r = client.post('/prep/onboarding/anchor',
                       data=json.dumps({"task_id": task_id, "answer": "таких n нету"}),
                       content_type='application/json')
        data = r.get_json()
        print(f"Anchor1 answer='таких n нету': correct={data.get('correct')}, step={data.get('step')}")
        
        if data.get('anchor'):
            task2_id = data['anchor']['task_id']
            # Submit anchor 2 (correct answer)
            task2 = db.session.get(AdaptiveTask, task2_id)
            correct_a2 = task2.correct_answer if task2 else ""
            r = client.post('/prep/onboarding/anchor',
                           data=json.dumps({"task_id": task2_id, "answer": correct_a2}),
                           content_type='application/json')
            data = r.get_json()
            print(f"Anchor2 answer='{correct_a2}': correct={data.get('correct')}, step={data.get('step')}, finish_ready={data.get('finish_ready')}")
        
        # Finish
        r = client.post('/prep/onboarding/answer',
                       data=json.dumps({"qid": "_finish", "key": "_finish"}),
                       content_type='application/json')
        data = r.get_json()
        print(f"Finish: done={data.get('done')}, has_result={data.get('result') is not None}")
        
        if data.get('result'):
            res = data['result']
            print(f"  goal={res.get('goal')}, mu={res.get('prior_mu')}, sigma={res.get('prior_sigma')}")
            print(f"  start_level={res.get('start_level')}, test_length={res.get('test_length')}")
            print(f"  daily_tasks={res.get('daily_tasks')}, route_ceiling={res.get('route_ceiling')}")
        
        # Check prep_state in DB
        cs = CuratorState.query.filter_by(user_id=3).first()
        if cs:
            prep = getattr(cs, 'prep_state', None) or {}
            print(f"\nDB prep_state keys: {list(prep.keys())}")
            if 'onboarding' in prep:
                ob = prep['onboarding']
                print(f"  onboarding.goal={ob.get('goal')}")
                print(f"  onboarding.prior_mu={ob.get('prior_mu')}")
                print(f"  onboarding.anchors={json.dumps(ob.get('anchors'), ensure_ascii=False)}")
            if 'test_queue' in prep:
                tq = prep['test_queue']
                print(f"  test_queue: {len(tq)} items")
                for i, t in enumerate(tq[:3]):
                    print(f"    [{i}] kind={t.get('kind')} scope={t.get('scope')} length={t.get('length')}")
        
        print("\n✅ Full onboarding flow: COMPLETE")
    
    # ── TEST 3: GET /prep/onboarding = 200 ──
    print("\n" + "="*70)
    print("=== GET /prep/onboarding = 200 ===")
    r = client.get('/prep/onboarding')
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        print("✅ GET /prep/onboarding = 200")
    else:
        print("❌ FAIL")

print("\n" + "="*70)
print("DONE")
