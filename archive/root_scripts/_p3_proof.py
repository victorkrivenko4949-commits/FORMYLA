# -*- coding: utf-8 -*-
import sys, os, json, io

sys.path.insert(0, os.path.dirname(__file__))

from app import app, db
from models import User
from models_curator import CuratorState

OUT = []
def log(s): OUT.append(s)

def create_user(email, grade):
    with app.app_context():
        u = User(email=email, preferred_grade=grade)
        u.password_hash = 'test'
        db.session.add(u)
        db.session.commit()
        return u.id

def delete_user(uid):
    with app.app_context():
        try:
            u = db.session.get(User, uid)
            if u:
                # Manually delete CS first to avoid cascade issues
                cs = CuratorState.query.filter_by(user_id=uid).first()
                if cs:
                    db.session.delete(cs)
                    db.session.flush()
                db.session.delete(u)
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            log(f'  delete_user warning: {e}')

def login(client, email):
    with app.app_context():
        u = User.query.filter_by(email=email).first()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(u.id)
        sess['_fresh'] = True
    return u.id

def dump_prep_state(uid):
    with app.app_context():
        cs = CuratorState.query.filter_by(user_id=uid).first()
        if not cs or not cs.prep_state:
            return {}, False
        ps = cs.prep_state
        if isinstance(ps, str):
            ps = json.loads(ps)
        return ps, cs.onboarding_done

# ─── PATH A ─────────────────────────────────────────────────────────
log('=== PATH A: /prep/onboarding tree ===')
uid_a = create_user('p3a@test.formyla', 9)
with app.test_client() as c:
    login(c, 'p3a@test.formyla')
    r = c.post('/prep/onboarding/answer', json={'qid': '_start', 'key': ''})
    d = r.get_json() or {}
    for step in range(30):
        qid = d.get('qid') or ''
        opts = d.get('options') or []
        key = opts[0].get('key','') if opts else ''
        if not qid or d.get('done') or d.get('finished'):
            log(f'  -> {step} steps, done={d.get("done") or d.get("finished")}')
            break
        r = c.post('/prep/onboarding/answer', json={'qid': qid, 'key': key})
        d = r.get_json() or {}

ps_a, od_a = dump_prep_state(uid_a)
log(f'  onboarding_done = {od_a}')
log(f'  prep_state keys: {sorted(ps_a.keys())}')
if 'onboarding' in ps_a:
    ob = ps_a['onboarding']
    log(f'  onboarding subkeys ({len(ob)}): {sorted(ob.keys())}')
    for k in ['daily_tasks','route_ceiling','test_length','grade','target_level']:
        log(f'    {k} = {ob.get(k)}')
    log(f'    FULL onboarding: {json.dumps(ob, ensure_ascii=False, default=str)}')
else:
    log(f'  NO onboarding! Full prep_state: {json.dumps(ps_a, ensure_ascii=False, default=str)[:500]}')
delete_user(uid_a)

# ─── PATH B ─────────────────────────────────────────────────────────
log('')
log('=== PATH B: /prep/coach/chat curator ===')
uid_b = create_user('p3b@test.formyla', 9)
with app.test_client() as c:
    login(c, 'p3b@test.formyla')
    for step in range(25):
        msg = 'привет' if step == 0 else f'ответ {step}'
        r = c.post('/prep/coach/chat', json={'message': msg})
        d = r.get_json() or {}
        done = d.get('done') or d.get('questionnaire_done')
        reply = d.get('reply','')[:100]
        if step <= 4 or done:
            log(f'  step{step}: done={done} reply={reply}')
        if done:
            break

ps_b, od_b = dump_prep_state(uid_b)
log(f'  onboarding_done = {od_b}')
log(f'  prep_state keys: {sorted(ps_b.keys())}')
if 'onboarding' in ps_b:
    ob = ps_b['onboarding']
    log(f'  onboarding subkeys ({len(ob)}): {sorted(ob.keys())}')
    for k in ['daily_tasks','route_ceiling','test_length','grade','target_level']:
        log(f'    {k} = {ob.get(k)}')
    log(f'    FULL onboarding: {json.dumps(ob, ensure_ascii=False, default=str)}')
else:
    log(f'  NO onboarding! Full prep_state: {json.dumps(ps_b, ensure_ascii=False, default=str)[:500]}')
delete_user(uid_b)

# ─── COMPARISON ─────────────────────────────────────────────────────
log('')
log('=== COMPARISON ===')
log(f'PATH A keys: {sorted(ps_a.keys()) if ps_a else "empty"}')
log(f'PATH B keys: {sorted(ps_b.keys()) if ps_b else "empty"}')
log(f'PATH A onboarding_done: {od_a}')
log(f'PATH B onboarding_done: {od_b}')

if ps_a and ps_b and 'onboarding' in ps_a and 'onboarding' in ps_b:
    f_a = set(ps_a['onboarding'].keys())
    f_b = set(ps_b['onboarding'].keys())
    log(f'Onboarding field count A={len(f_a)} B={len(f_b)}')
    log(f'Fields match: {f_a == f_b}')
    log(f'Both have 17 fields: A={len(f_a)==17} B={len(f_b)==17}')
    if f_a != f_b:
        log(f'  Only in A: {f_a - f_b}')
        log(f'  Only in B: {f_b - f_a}')
    ob_a = ps_a['onboarding']
    ob_b = ps_b['onboarding']
    common = f_a & f_b
    diffs = [(k, ob_a.get(k), ob_b.get(k)) for k in sorted(common) if ob_a.get(k) != ob_b.get(k)]
    log(f'Differing values: {len(diffs)}')
    for k, va, vb in diffs:
        log(f'  {k}: A={va!r} B={vb!r}')
else:
    log('Cannot compare — one path has no onboarding key')

out_path = os.path.join(os.path.dirname(__file__), '_p3_proof_result.txt')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(OUT))
print(f'Done. {len(OUT)} lines -> {out_path}')
