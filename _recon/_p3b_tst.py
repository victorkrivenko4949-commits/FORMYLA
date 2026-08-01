# -*- coding: utf-8 -*-
import sys, os, json, uuid

sys.path.insert(0, os.path.dirname(__file__))
from app import app, db
from models import User
from models_curator import CuratorState

OUT = []
def log(s): OUT.append(s)

with app.app_context():
    import sqlite3
    conn = sqlite3.connect('formyla.db')
    for em in ['p3bb@x.test']:
        r = conn.execute('SELECT id FROM users WHERE email=?',(em,)).fetchone()
        if r:
            conn.execute('DELETE FROM curator_state WHERE user_id=?',(r[0],))
            conn.execute('DELETE FROM users WHERE id=?',(r[0],))
    conn.commit(); conn.close()

    uid_b = None
    u = User(email='p3bb@x.test', preferred_grade=9)
    u.password_hash = 'test'
    db.session.add(u); db.session.commit()
    uid_b = u.id
    log(f'PATH B user created: {uid_b}')

with app.test_client() as c:
    with app.app_context():
        u = db.session.get(User, uid_b)
    with c.session_transaction() as sess:
        sess['_user_id'] = str(u.id); sess['_fresh'] = True

    # Step 1: trigger questionnaire
    for step in range(20):
        msg = 'привет' if step == 0 else f'ответ {step+1}'
        r = c.post('/prep/coach/chat', json={'message': msg})
        d = r.get_json() or {}
        done = d.get('done') or d.get('questionnaire_done')
        reply = d.get('reply','')[:150]
        if step <= 5 or done:
            log(f'  step{step}: done={done} reply={reply}')
        if done:
            break

with app.app_context():
    cs = CuratorState.query.filter_by(user_id=uid_b).first()
    if cs:
        ps = cs.prep_state if isinstance(cs.prep_state, dict) else json.loads(cs.prep_state)
        ob = ps.get('onboarding', {})
        log(f'\nonboarding_done = {cs.onboarding_done}')
        log(f'prep_state keys: {sorted(ps.keys())}')
        log(f'onboarding subkeys ({len(ob)}): {sorted(ob.keys())}')
        for k in ['daily_tasks','route_ceiling','test_length','grade','target_level','prior_mu','prior_sigma','start_level','conflict']:
            log(f'  {k} = {ob.get(k)}')
    else:
        log('CuratorState NOT FOUND!')

    # Cleanup
    conn2 = sqlite3.connect('formyla.db')
    conn2.execute('DELETE FROM curator_state WHERE user_id=?',(uid_b,))
    conn2.execute('DELETE FROM users WHERE id=?',(uid_b,))
    conn2.commit(); conn2.close()

with open('_p3b_result.txt','w',encoding='utf-8') as f:
    f.write('\n'.join(OUT))
print('DONE')
