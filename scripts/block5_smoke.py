# -*- coding: utf-8 -*-
"""BLOCK 5: End-to-end path for clean student via test_client.
qid comes from question['id'] (e.g. 'target', 'olymp_reach', 'load', 'deadline').
"""
import json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app import app, db
from models import User
from models_curator import CuratorState
from daily_tasks.models import DailyTaskSet, DailyTaskItem

app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = False
app.config['SERVER_NAME'] = 'localhost'

client = app.test_client()
uid_email = f'nt29_{int(time.time())}@t.test'

with app.app_context():
    existing = User.query.filter_by(email=uid_email).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
    u = User(email=uid_email, name='Night29', is_guest=False)
    db.session.add(u)
    db.session.commit()
    uid = u.id
    print(f'STEP 0: Created user {uid}')

with client.session_transaction() as sess:
    sess['_user_id'] = str(uid)
    sess['_fresh'] = True
print('STEP 0.1: Logged in')

# ── 5.1: Home ──
r = client.get('/')
print(f'5.1 GET /: {r.status_code}')

# ── 5.2: Greeting ──
r = client.get('/prep/coach/greeting')
d = json.loads(r.data)
print(f'5.2 Greeting: {r.status_code} scenario={d.get("scenario")} cta_url={d.get("cta_url")}')

# ── 5.3: Set grade ──
r = client.post('/prep/coach/set_grade', json={'grade': 9})
print(f'5.3a set_grade: {r.status_code}')
r = client.get('/prep/coach/greeting')
d = json.loads(r.data)
print(f'5.3b scenario={d.get("scenario")} cta_url={d.get("cta_url")} cta_text={d.get("cta_text")}')

# ── 5.4: Onboarding questionnaire ──
r = client.post('/prep/onboarding/answer', json={'qid': '_start', 'key': ''})
d = json.loads(r.data)
print(f'\n5.4a _start: {r.status_code} done={d.get("done")} step={d.get("step")}')
q = d.get('question', {})
print(f'  q.id={q.get("id","?")} text={q.get("text","")[:80]}')
opts = q.get('options', [])
print(f'  options: {[o.get("key") for o in opts]}')

# Loop through questions using question['id'] as qid
for it in range(10):
    if d.get('done'):
        break
    step = d.get('step')
    q = d.get('question', {})
    anchors = d.get('anchors')  # may be present at end
    qid_val = q.get('id', '') if q else ''
    opts = q.get('options', []) if q else []

    if anchors is not None and not q:
        print(f'  anchors appeared before done, breaking loop')
        break
    if not qid_val or not opts:
        print(f'  no qid or options at step={step}')
        break

    key = opts[0].get('key', '')
    r = client.post('/prep/onboarding/answer', json={'qid': qid_val, 'key': key})
    d = json.loads(r.data)
    print(f'  answer: qid={qid_val} key={key} -> status={r.status_code} done={d.get("done")} step={d.get("step")}')
    if d.get('done'):
        break
    next_q = d.get('question')
    if not next_q and not d.get('anchor'):
        print(f'  no question and no anchor, breaking')
        break

# Check for anchors
anchors_list = []
if not d.get('done'):
    anchor = d.get('anchor')
    while anchor:
        tid = anchor.get('task_id')
        ca = anchor.get('correct_answer', '')
        sec = anchor.get('section', '?')
        r = client.post('/prep/onboarding/anchor', json={'task_id': tid, 'answer': ca})
        ad = json.loads(r.data)
        print(f'  anchor: section={sec} correct={ad.get("correct")} done={ad.get("done")} step={ad.get("step")}')
        if ad.get('done'):
            d = ad
            break
        next_a = ad.get('anchor')
        if not next_a:
            # done or need to answer more
            if ad.get('done'):
                d = ad
                break
            # If anchors done but questionnaire still going
            if ad.get('question'):
                q_next = ad.get('question')
                qid_next = q_next.get('id', '') if q_next else ''
                opts_next = q_next.get('options', []) if q_next else []
                if qid_next and opts_next:
                    key = opts_next[0].get('key', '')
                    r = client.post('/prep/onboarding/answer', json={'qid': qid_next, 'key': key})
                    d = json.loads(r.data)
                    print(f'  post-anchor q: qid={qid_next} step={d.get("step")} done={d.get("done")}')
                    anchor = d.get('anchor')
                    continue
                break
        anchor = next_a

# Finish
r = client.post('/prep/onboarding/answer', json={'qid': '_finish', 'key': ''})
d = json.loads(r.data)
print(f'5.4e _finish: {r.status_code}')
print(f'  priority={d.get("priority","?")} prior_mu={d.get("prior_mu","?")} ceiling={d.get("ceiling","?")}')
err = d.get('error', '')
if err:
    print(f'  ERROR: {err[:200]}')

# ── 5.5: Post-onboarding ──
r = client.get('/prep/coach/greeting')
d = json.loads(r.data)
print(f'\n5.5 post-onboarding: {r.status_code}')
print(f'  scenario={d.get("scenario")} cta_url={d.get("cta_url")} cta_text={d.get("cta_text")}')
na = d.get('next_action', {})
print(f'  kind={na.get("kind","?")} url={na.get("url","?")}')

# ── 5.6: Onboarding page ──
r = client.get('/prep/onboarding')
print(f'5.6 GET /prep/onboarding: {r.status_code}')

# ── 5.7: Daily tasks ──
r = client.get('/daily-set')
print(f'\n5.7a GET /daily-set: {r.status_code}')
try:
    dd = json.loads(r.data)
    tasks = dd.get('tasks', [])
    print(f'  tasks_count={len(tasks)}')
    if tasks:
        subjects = set(t.get('subject','?') for t in tasks)
        levels = [t.get('difficulty_level','?') for t in tasks]
        print(f'  subjects={subjects}')
        print(f'  levels={levels}')
except:
    print(f'  body[:150]={r.data[:150]}')

r = client.get('/daily_tasks/')
print(f'5.7b GET /daily_tasks/: {r.status_code}')

# ── 5.8: Curator ──
r = client.get('/prep/coach')
print(f'\n5.8 GET /prep/coach: {r.status_code}')

# ── DB state ──
with app.app_context():
    cs = CuratorState.query.filter_by(user_id=uid).first()
    if cs:
        print(f'\nFINAL: mu={cs.level_mu} sigma={cs.level_sigma} onboarding_done={cs.onboarding_done}')
        lb = cs.level_by_section
        if lb:
            if isinstance(lb, str):
                try:
                    lb = json.loads(lb)
                except:
                    pass
            if isinstance(lb, dict):
                for sec, v in lb.items():
                    print(f'  {sec}: {v}')
        ps = cs.prep_state
        if isinstance(ps, dict):
            ob = ps.get('onboarding', {})
            print(f'  daily_tasks={ob.get("daily_tasks","?")} ceiling={ob.get("route_ceiling","?")}')
    dts = DailyTaskSet.query.filter_by(user_id=uid).order_by(DailyTaskSet.id.desc()).first()
    if dts:
        print(f'  DailyTaskSet: id={dts.id} status={dts.status} triggered_by={dts.triggered_by}')
        items = DailyTaskItem.query.filter_by(daily_set_id=dts.id).all()
        print(f'  items={len(items)}')
        for it in items:
            spec = json.loads(it.gemini_spec_json or '{}')
            print(f'    #{it.position}: {it.subject} {it.topic} L{it.difficulty_level} section={spec.get("section","?")}')
    else:
        print('  DailyTaskSet: NONE')

print('\n=== BLOCK 5 COMPLETE ===')
