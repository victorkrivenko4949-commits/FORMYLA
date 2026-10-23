"""
Detect which module forms anchor tasks by injecting markers and testing.
Markers:
  [MARKER-A] — services/onboarding.py
  [MARKER-B] — services/onboarding_tree.py
  [MARKER-C] — templates/prep/onboarding.html
"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app

with app.app_context():
    from models import db, User
    from models_curator import CuratorState
    
    # Reset user 3 onboarding
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
    
    # Start
    r = client.post('/prep/onboarding/answer', json={'qid': '_start', 'key': '_start'})
    data = r.get_json()
    print(f"START: step={data.get('step')}")
    
    # Answer Q2-Q5 quickly
    for qid, key in [('target','lvl3'), ('olymp_reach','none'), ('load','5'), ('deadline','none')]:
        r = client.post('/prep/onboarding/answer', json={'qid': qid, 'key': key})
        data = r.get_json()
        print(f"  {qid}={key} -> step={data.get('step')}")
    
    # Now look at the anchor response
    anchor = data.get('anchor', {})
    task_text = anchor.get('task_text', '')
    section = anchor.get('section', '?')
    section_ru = anchor.get('section_ru', '?')
    idx = anchor.get('idx', '?')
    total = anchor.get('total', '?')
    
    print(f"\n=== ANCHOR DETECTION ===")
    print(f"task_text: [{task_text[:120]}]")
    print(f"section: {section}")
    print(f"section_ru: {section_ru}")
    print(f"idx: {idx}")
    print(f"total: {total}")
    
    # Find markers
    found = []
    if 'MARKER-A' in task_text:
        found.append('MARKER-A (onboarding.py)')
    if 'MARKER-B' in task_text:
        found.append('MARKER-B (onboarding_tree.py)')
    if 'MARKER-C' in task_text:
        found.append('MARKER-C (template)')
    
    # Also check for old patterns
    if 'Задача' in task_text and 'Найдите x' in task_text:
        found.append('OLD STUB: "Задача N класс..."')
    if 'Якорь 1 из 3' in json.dumps(data):
        found.append('OLD COUNTER: "Якорь 1 из 3"')
    if 'Якорь 1 из 5' in json.dumps(data):
        found.append('NEW COUNTER: "Якорь 1 из 5"')
    
    print(f"\nFOUND MARKERS: {found}")
    
    if not found:
        print("NO MARKERS FOUND — checking raw JSON:")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:500])
    
    # Also check template for MARKER-C directly
    r = client.get('/prep/onboarding')
    html = r.data.decode('utf-8')
    if 'MARKER-C' in html:
        print("\nMARKER-C found in template HTML")
    else:
        print("\nMARKER-C NOT in template HTML")
    
    # Cleanup
    cs = CuratorState.query.filter_by(user_id=3).first()
    if cs:
        cs.prep_state = {}
        cs.onboarding_done = False
        db.session.commit()
