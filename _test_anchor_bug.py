"""Direct Flask test client to reproduce anchor bug - bypasses auth/CSRF."""
import json
import sys

# Set up Flask app and context
from app import app, db
from models import User

app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False
app.config['LOGIN_DISABLED'] = False

with app.test_client() as client:
    # Login as user 3
    with client.session_transaction() as sess:
        sess['_user_id'] = '3'
        sess['_fresh'] = True
        sess['_id'] = 'test-session-id'
        sess['csrf_token'] = 'test-csrf'
    
    # Verify login
    r = client.get('/prep/onboarding')
    print(f"GET /prep/onboarding: {r.status_code}")
    if r.status_code != 200:
        print("NOT AUTHENTICATED!")
        sys.exit(1)
    print("AUTHENTICATED\n")
    
    # Start onboarding
    print("=== Step: Start ===")
    r = client.post('/prep/onboarding/answer',
                    data=json.dumps({"qid": "_start", "key": "_start"}),
                    content_type='application/json')
    print(f"Status: {r.status_code}")
    data = r.get_json()
    print(f"Keys: {list(data.keys())}")
    print(f"Step: {data.get('step')}")
    print(f"Body: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}\n")
    
    # Answer Q1
    print("=== Step: Q1 (goal=school) ===")
    r = client.post('/prep/onboarding/answer',
                    data=json.dumps({"qid": "goal", "key": "school"}),
                    content_type='application/json')
    data = r.get_json()
    print(f"Status: {r.status_code}, Step: {data.get('step')}")
    q2_id = data['question']['id']
    q2_key = data['question']['options'][len(data['question']['options'])//2]['key']
    print(f"Q2 id={q2_id}\n")
    
    # Answer Q2
    print(f"=== Step: Q2 ({q2_id}={q2_key}) ===")
    r = client.post('/prep/onboarding/answer',
                    data=json.dumps({"qid": q2_id, "key": q2_key}),
                    content_type='application/json')
    data = r.get_json()
    print(f"Status: {r.status_code}, Step: {data.get('step')}")
    q3_id = data['question']['id']
    q3_key = data['question']['options'][0]['key']
    print(f"Q3 id={q3_id}\n")
    
    # Answer Q3
    print(f"=== Step: Q3 ({q3_id}={q3_key}) ===")
    r = client.post('/prep/onboarding/answer',
                    data=json.dumps({"qid": q3_id, "key": q3_key}),
                    content_type='application/json')
    data = r.get_json()
    print(f"Status: {r.status_code}, Step: {data.get('step')}")
    q4_id = data['question']['id']
    q4_key = data['question']['options'][0]['key']
    print(f"Q4 id={q4_id}\n")
    
    # Answer Q4
    print(f"=== Step: Q4 ({q4_id}={q4_key}) ===")
    r = client.post('/prep/onboarding/answer',
                    data=json.dumps({"qid": q4_id, "key": q4_key}),
                    content_type='application/json')
    data = r.get_json()
    print(f"Status: {r.status_code}")
    print(f"Step: {data.get('step')}")
    
    if data.get('anchor'):
        task_id = data['anchor']['task_id']
        print(f"Anchor task_id={task_id}")
    elif data.get('anchors_unavailable'):
        print("ANCHORS UNAVAILABLE - trying different Q2 option")
        print(f"Full data: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}")
        sys.exit(1)
    else:
        print(f"UNEXPECTED: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}")
        sys.exit(1)
    
    # ── BUG REPRO ──
    print("\n" + "="*60)
    print("=== BUG REPRO: 'таких n нету' ===")
    print("="*60)
    r = client.post('/prep/onboarding/anchor',
                    data=json.dumps({"task_id": task_id, "answer": "таких n нету"}),
                    content_type='application/json')
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.content_type}")
    print(f"Body: {r.get_data(as_text=True)}")
    
    try:
        body = r.get_json()
        print(f"\nJSON keys: {list(body.keys())}")
        print(f"correct: {body.get('correct')}")
        print(f"anchor: {body.get('anchor')}")
        print(f"finish_ready: {body.get('finish_ready')}")
        print(f"error: {body.get('error')}")
        print(f"done: {body.get('done')}")
        print(f"step: {body.get('step')}")
    except:
        print("NOT VALID JSON!")
    
    # ── Test: empty string ──
    print("\n" + "="*60)
    print("=== Test: empty string ===")
    r = client.post('/prep/onboarding/anchor',
                    data=json.dumps({"task_id": task_id, "answer": ""}),
                    content_type='application/json')
    print(f"Status: {r.status_code}")
    print(f"Body: {r.get_data(as_text=True)[:300]}")
    
    # ── Test: spaces only ──
    print("\n" + "="*60)
    print("=== Test: spaces only ===")
    r = client.post('/prep/onboarding/anchor',
                    data=json.dumps({"task_id": task_id, "answer": "   "}),
                    content_type='application/json')
    print(f"Status: {r.status_code}")
    print(f"Body: {r.get_data(as_text=True)[:300]}")
    
    # ── Test: wrong number ──
    print("\n" + "="*60)
    print("=== Test: wrong number ===")
    r = client.post('/prep/onboarding/anchor',
                    data=json.dumps({"task_id": task_id, "answer": "999999"}),
                    content_type='application/json')
    print(f"Status: {r.status_code}")
    print(f"Body: {r.get_data(as_text=True)[:300]}")
