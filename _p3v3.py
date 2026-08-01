# -*- coding: utf-8 -*-
import sys, os, json, sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import User
from models_curator import CuratorState

OUT = []
def log(s):
    OUT.append(s)
    sys.stderr.write(s + '\n')

# ─── remove test_length ──────────────────────────────────────────────
for fpath in ['routes/prep.py', 'services/onboarding.py']:
    s = open(fpath, 'r', encoding='utf-8').read()
    lines = s.split('\n')
    new_lines = []
    removed = 0
    for line in lines:
        if "'test_length':" in line and ('full_result.test_length' in line or 'result.test_length' in line):
            removed += 1
            continue
        new_lines.append(line)
    open(fpath, 'w', encoding='utf-8').write('\n'.join(new_lines))
    log(f'REMOVED test_length from {fpath}: {removed} lines')

# ─── PROBE_SIZE ──────────────────────────────────────────────────────
log(f'\nPROBE_SIZE: services/theme_probe.py:27 = 5')
log(f'Used at lines: 105, 114, 186, 262, 314')

# ─── Clean ───────────────────────────────────────────────────────────
def clean(e):
    conn = sqlite3.connect('formyla.db')
    r = conn.execute('SELECT id FROM users WHERE email=?',(e,)).fetchone()
    if r:
        conn.execute('DELETE FROM curator_state WHERE user_id=?',(r[0],))
        conn.execute('DELETE FROM users WHERE id=?',(r[0],))
    conn.commit(); conn.close()

clean('p3af@x.test'); clean('p3bf@x.test')

# ─── PATH A ──────────────────────────────────────────────────────────
log('\n=== PATH A: onboarding tree ===')
with app.app_context():
    u = User(email='p3af@x.test', preferred_grade=9)
    u.password_hash = 'test'
    db.session.add(u); db.session.commit()
    uid_a = u.id

with app.test_client() as c:
    with app.app_context():
        u = db.session.get(User, uid_a)
    with c.session_transaction() as sess:
        sess['_user_id'] = str(u.id); sess['_fresh'] = True

    r = c.post('/prep/onboarding/answer', json={'qid': '_start', 'key': ''})
    d = r.get_json() or {}
    for step in range(30):
        qid = d.get('qid') or ''
        opts = d.get('options') or []
        key = opts[0].get('key','') if opts else ''
        if not qid or d.get('done') or d.get('finished'):
            log(f'  {step} steps, done={d.get("done") or d.get("finished")}')
            break
        r = c.post('/prep/onboarding/answer', json={'qid': qid, 'key': key})
        d = r.get_json() or {}

with app.app_context():
    cs = CuratorState.query.filter_by(user_id=uid_a).first()
    ps_a = cs.prep_state if isinstance(cs.prep_state, dict) else json.loads(cs.prep_state)
    ob_a = ps_a.get('onboarding', {})
    log(f'  onboarding_done={cs.onboarding_done}')
    log(f'  prep_state keys: {sorted(ps_a.keys())}')
    log(f'  onboarding subkeys ({len(ob_a)}): {sorted(ob_a.keys())}')
    log(f'  test_length = {ob_a.get("test_length")}')

# ─── PATH B: chat via session ────────────────────────────────────────
log('\n=== PATH B: chat curator ===')
with app.app_context():
    u = User(email='p3bf@x.test', preferred_grade=9)
    u.password_hash = 'test'
    db.session.add(u); db.session.commit()
    uid_b = u.id

with app.test_client() as c:
    with app.app_context():
        u = db.session.get(User, uid_b)
    with c.session_transaction() as sess:
        sess['_user_id'] = str(u.id); sess['_fresh'] = True
        sess['questionnaire'] = {
            'active': True, 'current_index': 0,
            'total': 6, 'answers': {},
        }

    answers = ['9','олимпиады','2 часа','июль 2027','хорошо','3']
    for step, ans in enumerate(answers):
        r = c.post('/prep/coach/chat', json={'message': ans})
        d = r.get_json() or {}
        done = d.get('done') or d.get('questionnaire_done')
        log(f'  step{step}: done={done} reply={d.get("reply","")[:80]}')
        if done:
            break

with app.app_context():
    cs = CuratorState.query.filter_by(user_id=uid_b).first()
    if cs:
        ps_b = cs.prep_state if isinstance(cs.prep_state, dict) else json.loads(cs.prep_state)
        ob_b = ps_b.get('onboarding', {})
        log(f'  onboarding_done={cs.onboarding_done}')
        log(f'  prep_state keys: {sorted(ps_b.keys())}')
        log(f'  onboarding subkeys ({len(ob_b)}): {sorted(ob_b.keys())}')
        log(f'  test_length = {ob_b.get("test_length")}')
    else:
        log('  PATH B FAILED — CuratorState not found')

# ─── COMPARISON ──────────────────────────────────────────────────────
log('\n=== COMPARISON ===')
f_a = set(ob_a.keys()) if ob_a else set()
f_b = set(ob_b.keys()) if ob_b else set()
log(f'PATH A fields ({len(f_a)}): {sorted(f_a)}')
log(f'PATH B fields ({len(f_b)}): {sorted(f_b)}')
log(f'test_length present: A={"test_length" in f_a} B={"test_length" in f_b}')
log(f'Fields match: {f_a == f_b}')

# ─── /prep/coach HTML ────────────────────────────────────────────────
log('\n=== /prep/coach HTML ===')
with app.test_client() as c:
    with app.app_context():
        u = db.session.get(User, uid_a)
    with c.session_transaction() as sess:
        sess['_user_id'] = str(u.id); sess['_fresh'] = True
    r = c.get('/prep/coach')
    html = r.data.decode('utf-8', errors='replace')
    # main action
    idx = html.find('mainActionTitle')
    log(f'  mainActionTitle: {html[idx:idx+200] if idx>=0 else "NOT FOUND"}')
    log(f'  cycleBlock: {"PRESENT" if "cycleBlock" in html else "ABSENT"}')
    # first 3 themes
    idx = html.find('cycle_themes')
    if idx >= 0:
        for line in html[idx:idx+500].split('\n')[:15]:
            if 't.name' in line or 'G9_' in line:
                log(f'  theme: {line.strip()[:120]}')

# Write output
with open('_p3_final_v3.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(OUT))
sys.stderr.write('\nDONE\n')
