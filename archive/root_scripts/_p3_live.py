# -*- coding: utf-8 -*-
import sys, os, json

sys.path.insert(0, os.path.dirname(__file__))

from app import app, db
from models import User
from models_curator import CuratorState

def log(msg):
    with open('_p3_live_out.txt', 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

# Show PATH A result from user 10023
with app.app_context():
    cs = CuratorState.query.filter_by(user_id=10023).first()
    if cs:
        ps = cs.prep_state if isinstance(cs.prep_state, dict) else json.loads(cs.prep_state)
        ob = ps.get('onboarding', {})
        log('=== PATH A (user 10023, /prep/onboarding tree) ===')
        log(f'onboarding_done = {cs.onboarding_done}')
        log(f'prep_state keys: {sorted(ps.keys())}')
        log(f'onboarding subkeys ({len(ob)}): {sorted(ob.keys())}')
        for k in ['daily_tasks','route_ceiling','test_length','grade','target_level','prior_mu','prior_sigma','start_level','conflict','completed_at']:
            log(f'  {k} = {ob.get(k)}')
    else:
        log('PATH A user 10023: NOT FOUND')

# Now PATH B — use a fresh unique email
import uuid
email_b = f'p3b_{uuid.uuid4().hex[:8]}@test.formyla'
uid_b = None

with app.app_context():
    u = User(email=email_b, preferred_grade=9)
    u.password_hash = 'test'
    db.session.add(u)
    db.session.commit()
    uid_b = u.id
    log(f'\n=== PATH B: created user {uid_b} ({email_b}) ===')

# Login + chat
with app.test_client() as c:
    with app.app_context():
        u = User.query.filter_by(id=uid_b).first()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(u.id)
        sess['_fresh'] = True

    for step in range(30):
        msg = 'привет' if step == 0 else f'да {step}'
        r = c.post('/prep/coach/chat', json={'message': msg})
        d = r.get_json() or {}
        done = d.get('done') or d.get('questionnaire_done')
        reply = d.get('reply', '')[:120]
        if step <= 5 or done:
            log(f'  step{step}: done={done} reply={reply}')
        if done:
            break

# Read result
with app.app_context():
    cs = CuratorState.query.filter_by(user_id=uid_b).first()
    if cs:
        ps = cs.prep_state if isinstance(cs.prep_state, dict) else json.loads(cs.prep_state)
        ob = ps.get('onboarding', {})
        log(f'\n=== PATH B RESULT (user {uid_b}, /prep/coach/chat) ===')
        log(f'onboarding_done = {cs.onboarding_done}')
        log(f'prep_state keys: {sorted(ps.keys())}')
        log(f'onboarding subkeys ({len(ob)}): {sorted(ob.keys())}')
        for k in ['daily_tasks','route_ceiling','test_length','grade','target_level','prior_mu','prior_sigma','start_level','conflict','completed_at']:
            log(f'  {k} = {ob.get(k)}')
    else:
        log(f'PATH B user {uid_b}: CuratorState NOT FOUND!')

# Also get coach page for both
log('\n=== /prep/coach pages ===')
with app.test_client() as c:
    # Login as user 10023
    with app.app_context():
        u = db.session.get(User, 10023)
    with c.session_transaction() as sess:
        sess['_user_id'] = str(u.id)
        sess['_fresh'] = True
    r = c.get('/prep/coach')
    html_a = r.data.decode('utf-8', errors='replace')
    # Extract main action block
    if 'mainActionBlock' in html_a:
        idx = html_a.find('mainActionTitle')
        title_a = html_a[idx:idx+200]
        log(f'  PATH A mainActionTitle: {title_a}')
    if 'cycleBlock' in html_a:
        log('  PATH A: cycleBlock PRESENT')
    else:
        log('  PATH A: cycleBlock ABSENT')
    # Check CTAs
    if 'onboarding_done=False' in html_a or 'Пройти анкету' in html_a:
        log('  PATH A: onboarding CTA visible')
    if 'Пройти утренний срез' in html_a:
        log('  PATH A: Пройти утренний срез button PRESENT')

print('done — see _p3_live_out.txt')
