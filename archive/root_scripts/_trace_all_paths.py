"""
Detect ALL paths that produce anchor/text tasks for onboarding.
Tests BOTH: /prep/onboarding AND /prep/coach/chat questionnaire flow.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app

with app.app_context():
    from models import db
    from models_curator import CuratorState
    
    # Reset user 3
    cs = CuratorState.query.filter_by(user_id=3).first()
    if cs:
        cs.prep_state = {}
        cs.onboarding_done = False
        db.session.commit()
    
    client = app.test_client()
    
    # Login
    with client.session_transaction() as sess:
        sess['_user_id'] = '3'
        sess['_fresh'] = True
    
    print("=" * 80)
    print("PATH A: /prep/onboarding (fixed)")
    print("=" * 80)
    
    # Start
    r = client.post('/prep/onboarding/answer', json={'qid': '_start', 'key': '_start'})
    data = r.get_json()
    print(f"START: step={data.get('step')} grade_auto={data.get('grade_auto')}")
    
    for qid, key in [('target','lvl3'), ('olymp_reach','none'), ('load','5'), ('deadline','none')]:
        r = client.post('/prep/onboarding/answer', json={'qid': qid, 'key': key})
        data = r.get_json()
        anchor = data.get('anchor')
        if anchor:
            print(f"  ANCHOR idx={anchor.get('idx')}/{anchor.get('total')} section={anchor.get('section_ru','?')} text=[{anchor.get('task_text','')[:80]}]")
    
    # Now walk through remaining anchors
    for i in range(5):
        anchor = data.get('anchor')
        if not anchor:
            break
        tid = anchor['task_id']
        r = client.post('/prep/onboarding/anchor', json={'task_id': tid, 'answer': '0'})
        data = r.get_json()
        next_anchor = data.get('anchor')
        if next_anchor:
            print(f"  ANCHOR idx={next_anchor.get('idx')}/{next_anchor.get('total')} section={next_anchor.get('section_ru','?')} text=[{next_anchor.get('task_text','')[:80]}]")
        if data.get('finish_ready'):
            break
    
    # Cleanup path A
    cs2 = CuratorState.query.filter_by(user_id=3).first()
    if cs2:
        cs2.prep_state = {}
        cs2.onboarding_done = False
        db.session.commit()
    
    print("\n" + "=" * 80)
    print("PATH B: /prep/coach/chat questionnaire flow")
    print("=" * 80)
    
    # Reset session for path B
    client2 = app.test_client()
    with client2.session_transaction() as sess:
        sess['_user_id'] = '3'
        sess['_fresh'] = True
    
    # Step 1: check if coach_greeting has any "coach_test" reference
    r = client2.get('/prep/coach/greeting')
    greeting = r.get_json()
    print(f"GREETING: kind={greeting.get('kind','?')} title={greeting.get('title','?')}")
    print(f"  url={greeting.get('url','?')}")
    print(f"  reason={greeting.get('reason','?')}")
    
    # Step 2: check if there's an active questionnaire in the chat
    from services.questionnaire_storage import get_questionnaire_state
    with client2.session_transaction() as sess:
        q_state = get_questionnaire_state()
        print(f"questionnaire_state: {q_state}")
    
    # Step 3: check /prep/coach page for any "coach_test" in session
    with client2.session_transaction() as sess:
        ct = sess.get('coach_test')
        print(f"coach_test in session: {ct}")
    
    # Step 4: Try the old coach/chat questionnaire path
    r = client2.get('/prep/coach')
    html = r.data.decode('utf-8')
    if 'coach_test_start' in html:
        print("Found coach_test_start in coach page HTML")
    if 'onboarding' in html:
        # Find onboarding-related links
        import re
        links = re.findall(r'href="([^"]*onboarding[^"]*)"', html)
        print(f"Onboarding links in coach page: {links}")
    
    # Step 5: try coach_chat with a message to trigger old questionnaire
    r = client2.post('/prep/coach/chat', json={'message': 'привет'})
    chat_data = r.get_json()
    print(f"\ncoach_chat('привет') reply: [{chat_data.get('reply','')[:200]}]")
    print(f"  done={chat_data.get('done')}")
    
    # Step 6: Check if coach_test_start still works
    r = client2.post('/prep/coach/test/start')
    test_data = r.get_json()
    print(f"\ncoach/test/start: reply={test_data.get('reply','')[:100]}")
    print(f"  redirect_url={test_data.get('redirect_url')}")
    
    print("\n" + "=" * 80)
    print("PATH C: Old questionnaire via coach_chat (3 text questions)")
    print("=" * 80)
    
    # Simulate the old questionnaire flow
    from services.questionnaire_storage import save_questionnaire_state
    with client2.session_transaction() as sess:
        save_questionnaire_state({'active': True, 'current_index': 0, 'total': 3, 'answers': {}})
    
    r = client2.post('/prep/coach/chat', json={'message': '30'})
    qdata = r.get_json()
    print(f"Q1 answer='30': [{qdata.get('reply','')[:200]}]")
    
    r = client2.post('/prep/coach/chat', json={'message': 'Олимпиады'})
    qdata = r.get_json()
    print(f"Q2 answer='Олимпиады': [{qdata.get('reply','')[:200]}]")
    
    r = client2.post('/prep/coach/chat', json={'message': '3'})
    qdata = r.get_json()
    print(f"Q3 answer='3': [{qdata.get('reply','')[:200]}]")
    print(f"  done={qdata.get('done')} level={qdata.get('level')}")
    
    # Cleanup
    cs3 = CuratorState.query.filter_by(user_id=3).first()
    if cs3:
        cs3.prep_state = {}
        cs3.onboarding_done = False
        db.session.commit()
    
    print("\nDONE - all paths traced")
