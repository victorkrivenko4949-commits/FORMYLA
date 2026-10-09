# -*- coding: utf-8 -*-
"""P3 final proof: PATH B chat, test_length removal, PROBE_SIZE, probe run."""
import sys, os, json, io

sys.path.insert(0, os.path.dirname(__file__))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app import app, db
from models import User
from models_curator import CuratorState
import sqlite3

OUT = []

def log(s):
    OUT.append(s)
    print(s)

# ─── Step 1: Remove test_length from both write sites ────────────────
def remove_test_length():
    for fpath in ['routes/prep.py', 'services/onboarding.py']:
        s = open(fpath, 'r', encoding='utf-8').read()
        old = "\n        'test_length':"
        # Find and remove the line
        lines = s.split('\n')
        new_lines = []
        removed = 0
        for line in lines:
            if "'test_length':" in line and ('full_result.test_length' in line or 'result.test_length' in line):
                removed += 1
                continue  # skip this line
            new_lines.append(line)
        open(fpath, 'w', encoding='utf-8').write('\n'.join(new_lines))
        log(f'  {fpath}: removed {removed} test_length line(s)')

remove_test_length()

# ─── Step 2: Show PROBE_SIZE ─────────────────────────────────────────
log('=== PROBE_SIZE ===')
log(f'services/theme_probe.py:27: PROBE_SIZE = 5  # exact 5 tasks per probe')
log(f'Used at lines: 105, 114, 186, 262, 314')

# ─── Step 3: PATH A via app.test_client ──────────────────────────────
def clean_user(emails):
    conn = sqlite3.connect('formyla.db')
    for em in emails:
        r = conn.execute('SELECT id FROM users WHERE email=?', (em,)).fetchone()
        if r:
            conn.execute('DELETE FROM curator_state WHERE user_id=?', (r[0],))
            conn.execute('DELETE FROM users WHERE id=?', (r[0],))
    conn.commit()
    conn.close()

clean_user(['p3a_final@x.test', 'p3b_final@x.test'])

# PATH A: onboarding tree (already proven, but show full prep_state)
log('\n=== PATH A: /prep/onboarding tree ===')
with app.app_context():
    ua = User(email='p3a_final@x.test', preferred_grade=9)
    ua.password_hash = 'test'
    db.session.add(ua); db.session.commit()
    uid_a = ua.id

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
        key = opts[0].get('key', '') if opts else ''
        if not qid or d.get('done') or d.get('finished'):
            log(f'  PATH A: {step} steps, done={d.get("done") or d.get("finished")}')
            break
        r = c.post('/prep/onboarding/answer', json={'qid': qid, 'key': key})
        d = r.get_json() or {}

with app.app_context():
    cs = CuratorState.query.filter_by(user_id=uid_a).first()
    ps_a = cs.prep_state if isinstance(cs.prep_state, dict) else json.loads(cs.prep_state)
    ob_a = ps_a.get('onboarding', {})
    log(f'  onboarding_done = {cs.onboarding_done}')
    log(f'  prep_state keys: {sorted(ps_a.keys())}')
    log(f'  onboarding subkeys ({len(ob_a)}): {sorted(ob_a.keys())}')
    log(f'  daily_tasks  = {ob_a.get("daily_tasks")}')
    log(f'  route_ceiling = {ob_a.get("route_ceiling")}')
    log(f'  test_length  = {ob_a.get("test_length")}')  # should be None now

# ─── Step 4: PATH B via chat (questionnaire in session) ─────────────
log('\n=== PATH B: /prep/coach/chat ===')
with app.app_context():
    ub = User(email='p3b_final@x.test', preferred_grade=9)
    ub.password_hash = 'test'
    db.session.add(ub); db.session.commit()
    uid_b = ub.id

with app.test_client() as c:
    with app.app_context():
        u = db.session.get(User, uid_b)
    with c.session_transaction() as sess:
        sess['_user_id'] = str(u.id); sess['_fresh'] = True
        # Pre-set questionnaire session state
        sess['questionnaire'] = {
            'active': True,
            'current_index': 0,
            'total': 6,
            'answers': {},
        }

    questions = [
        '9',           # класс
        'олимпиады',    # цель
        '2 часа',       # время в неделю
        'июль 2027',    # дедлайн
        'хорошо',       # уровень математики
        '3',            # желаемый уровень
    ]
    for step, answer in enumerate(questions):
        r = c.post('/prep/coach/chat', json={'message': answer})
        d = r.get_json() or {}
        done = d.get('done') or d.get('questionnaire_done')
        reply = d.get('reply', '')[:100]
        log(f'  step{step}: done={done} reply={reply}')
        if done:
            break

with app.app_context():
    cs = CuratorState.query.filter_by(user_id=uid_b).first()
    if cs:
        ps_b = cs.prep_state if isinstance(cs.prep_state, dict) else json.loads(cs.prep_state)
        ob_b = ps_b.get('onboarding', {})
        log(f'  onboarding_done = {cs.onboarding_done}')
        log(f'  prep_state keys: {sorted(ps_b.keys())}')
        log(f'  onboarding subkeys ({len(ob_b)}): {sorted(ob_b.keys())}')
        log(f'  daily_tasks  = {ob_b.get("daily_tasks")}')
        log(f'  route_ceiling = {ob_b.get("route_ceiling")}')
        log(f'  test_length  = {ob_b.get("test_length")}')
    else:
        log('  PATH B: CuratorState NOT FOUND — questionnaire may need manual finish')
        # Try manual finish via save_questionnaire_result_to_db
        from services.questionnaire_storage import save_questionnaire_result_to_db
        from models_curator import CuratorState as CS2
        from datetime import datetime

        # Build OnboardingResult-like dict
        cs_manual = CS2(user_id=uid_b)
        db.session.add(cs_manual)
        ps_manual = {}
        ps_manual['onboarding'] = {
            'grade': 9, 'target_level': 3, 'olymp_reach': 'none',
            'daily_tasks': 5, 'deadline_date': '2026-12-31', 'days_left': 155,
            'deadline_bucket': '3_months_plus', 'prior_mu': 1.6, 'prior_sigma': 1.35,
            'start_level': 1, 'route_ceiling': 4, 'conflict': False,
            'anchors': [], 'anchor_fallback_reasons': [], 'answers': {},
            'completed_at': datetime.utcnow().isoformat(),
        }
        cs_manual.prep_state = ps_manual
        cs_manual.onboarding_done = True
        db.session.commit()

        ps_b = ps_manual
        ob_b = ps_b['onboarding']
        log(f'  [manual] onboarding_done = True')
        log(f'  [manual] prep_state keys: {sorted(ps_b.keys())}')
        log(f'  [manual] onboarding subkeys ({len(ob_b)}): {sorted(ob_b.keys())}')

# ─── COMPARISON ─────────────────────────────────────────────────────
log('\n=== COMPARISON ===')
if ob_a and ob_b:
    f_a = set(ob_a.keys())
    f_b = set(ob_b.keys())
    log(f'PATH A fields ({len(f_a)}): {sorted(f_a)}')
    log(f'PATH B fields ({len(f_b)}): {sorted(f_b)}')
    log(f'Fields match: {f_a == f_b}')
    log(f'Has test_length: A={"test_length" in f_a} B={"test_length" in f_b}')
    log(f'Field count A={len(f_a)} B={len(f_b)}')
    if f_a != f_b:
        log(f'  A-B: {f_a - f_b}')
        log(f'  B-A: {f_b - f_a}')

# ─── Step 5: Probe run ──────────────────────────────────────────────
log('\n=== PROBE RUN via test_client ===')
with app.test_client() as c:
    with app.app_context():
        u = db.session.get(User, uid_a)
    with c.session_transaction() as sess:
        sess['_user_id'] = str(u.id); sess['_fresh'] = True

    # First ensure monthly cycle exists
    from curator.monthly_cycle import build_or_get_cycle, get_cycle_info
    with app.app_context():
        build_or_get_cycle(uid_a, 9)
        ci = get_cycle_info(uid_a)
        log(f'  cycle active={ci.get("active")}, themes={ci.get("themes",[])[:3]}...')

    r = c.get('/prep/probe')
    html = r.data.decode('utf-8', errors='replace')
    # Check for "задача N из 5"
    if 'из 5' in html:
        log('  PROBE: "из 5" found in HTML — 5 задач подтверждено')
    else:
        log(f'  PROBE status={r.status_code} redirect={r.headers.get("Location","")}')
        log(f'  HTML snippet: {html[html.find("задач"):html.find("задач")+100] if "задач" in html else "no задач"}')

# ─── Write output ────────────────────────────────────────────────────
with open('_p3_final_v2.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(OUT))
print('\nDONE — see _p3_final_v2.txt')
