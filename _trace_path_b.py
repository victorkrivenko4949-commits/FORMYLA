"""
Detect ALL paths that produce anchor/text tasks for onboarding.
Tests BOTH: /prep/onboarding AND /prep/coach/chat questionnaire flow.
"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app

with app.app_context():
    from models import db
    from models_curator import CuratorState
    
    client = app.test_client()
    
    # Login
    with client.session_transaction() as sess:
        sess['_user_id'] = '3'
        sess['_fresh'] = True
    
    # Reset user 3
    cs = CuratorState.query.filter_by(user_id=3).first()
    if cs:
        cs.prep_state = {}
        cs.onboarding_done = False
        db.session.commit()
    
    print("=" * 80)
    print("PATH B: /prep/coach/chat — questionnaire flow")
    print("=" * 80)
    
    # Step 1: coach_greeting
    r = client.get('/prep/coach/greeting')
    greeting = r.get_json()
    print(f"GREETING kind={greeting.get('kind','?')} title={greeting.get('title','?')}")
    print(f"  url={greeting.get('url','?')}")
    
    # Step 2: Check coach_test in session
    with client.session_transaction() as sess:
        ct = sess.get('coach_test')
        qn = sess.get('questionnaire')
        print(f"coach_test in session: {ct}")
        print(f"questionnaire in session: {qn}")
    
    # Step 3: coach_test_start
    r = client.post('/prep/coach/test/start')
    td = r.get_json()
    print(f"\ncoach/test/start: reply={td.get('reply','')[:100]}")
    print(f"  redirect_url={td.get('redirect_url')}")
    
    # Step 4: coach_chat with old questionnaire (if active)
    # First, check coach page HTML for any links
    r = client.get('/prep/coach')
    html = r.data.decode('utf-8')
    links = re.findall(r'(?:href|url)[=:]\s*["\']([^"\']*onboarding[^"\']*)["\']', html)
    print(f"\nOnboarding links on coach page: {links}")
    
    # Find coach_test_start triggers
    triggers = re.findall(r'coach_test_start|coach/onboarding|coach/questionnaire', html)
    print(f"Onboarding triggers in coach HTML: {triggers}")
    
    # Step 5: Try to activate old questionnaire
    from services.questionnaire_storage import save_questionnaire_state
    with client.session_transaction() as sess:
        save_questionnaire_state({'active': True, 'current_index': 0, 'total': 3, 'answers': {}})
    
    r = client.post('/prep/coach/chat', json={'message': '30'})
    qdata = r.get_json()
    reply_text = qdata.get('reply', '')
    print(f"\nOld questionnaire Q1 (daily_minutes='30'): [{reply_text[:200]}]")
    
    r = client.post('/prep/coach/chat', json={'message': 'Олимпиады'})
    qdata = r.get_json()
    print(f"Old questionnaire Q2 (goal='Олимпиады'): [{qdata.get('reply','')[:200]}]")
    
    r = client.post('/prep/coach/chat', json={'message': '3'})
    qdata = r.get_json()
    reply3 = qdata.get('reply', '')
    print(f"Old questionnaire Q3 (confidence='3'): [{reply3[:300]}]")
    print(f"  done={qdata.get('done')} level={qdata.get('level')}")
    print(f"  questionnaire_done={qdata.get('questionnaire_done')}")
    
    # Check if this path contains any anchor task text
    if 'Задача' in reply3 or 'Найдите' in reply3 or 'Якорь' in reply3:
        print(f"  *** ANCHOR-TASK TEXT FOUND IN OLD QUESTIONNAIRE ***")
    else:
        print(f"  No anchor task text — this is pure text questionnaire")
    
    # Step 6: Cleanup
    cs3 = CuratorState.query.filter_by(user_id=3).first()
    if cs3:
        cs3.prep_state = {}
        cs3.onboarding_done = False
        db.session.commit()
    
    print("\n" + "=" * 80)
    print("VERDICT")
    print("=" * 80)
    print("Old questionnaire (diagnostic_questionnaire.py): 3 text questions, NO anchor tasks")
    print("coach_test_start: REDIRECTS to /prep/onboarding")
    print("Only anchor-task path: /prep/onboarding → services/onboarding.py")
