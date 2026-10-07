# -*- coding: utf-8 -*-
import sys, os, json, uuid

sys.path.insert(0, os.path.dirname(__file__))

from app import app, db
from models import User
from models_curator import CuratorState

OUT = []
def log(s): OUT.append(s); print(s)

with app.app_context():
    # Clean old test users
    import sqlite3
    c = sqlite3.connect('formyla.db')
    for em in ['p3b_test@x.formyla', 'p3b_chat@x.formyla']:
        r = c.execute('SELECT id FROM users WHERE email=?', (em,)).fetchone()
        if r:
            c.execute('DELETE FROM curator_state WHERE user_id=?', (r[0],))
            c.execute('DELETE FROM users WHERE id=?', (r[0],))
    c.commit()
    c.close()

    # ─── PATH A (new onboarding tree via finish()) ───
    log('=== PATH A: onboarding tree ===')
    u = User(email='p3a_test2@x.formyla', preferred_grade=9)
    u.password_hash = 'test'
    db.session.add(u); db.session.commit()
    uid_a = u.id

    from services.onboarding import start, finish
    result_a = start(uid_a)  # returns first question
    # Simulate answering all questions by calling finish directly with mock answers
    answers_a = {'grade_pref': '9', 'goal_olympiad': 'vsosh', 'time_per_week': '3h', 
                 'deadline': '3_months', 'math_level': 'school_strong'}
    result_a = finish(uid_a)
    log(f'  finish keys: {sorted(result_a.keys())}')

    cs = CuratorState.query.filter_by(user_id=uid_a).first()
    ps_a = cs.prep_state if isinstance(cs.prep_state, dict) else json.loads(cs.prep_state)
    ob_a = ps_a.get('onboarding', {})
    log(f'  onboarding_done = {cs.onboarding_done}')
    log(f'  prep_state keys: {sorted(ps_a.keys())}')
    log(f'  onboarding subkeys ({len(ob_a)}): {sorted(ob_a.keys())}')
    for k in ['daily_tasks','route_ceiling','test_length','grade','target_level']:
        log(f'    {k} = {ob_a.get(k)}')

    # ─── PATH B (chat curator path — direct OnboardingResult write) ───
    log('')
    log('=== PATH B: chat curator (direct OnboardingResult) ===')
    u2 = User(email='p3b_chat@x.formyla', preferred_grade=9)
    u2.password_hash = 'test'
    db.session.add(u2); db.session.commit()
    uid_b = u2.id

    # This is what coach_chat does after questionnaire completes
    from services.questionnaire_storage import save_questionnaire_result_to_db
    from models_curator import CuratorState as CS
    from datetime import datetime
    from services.diagnostic_questionnaire import compute_provisional_level

    chat_answers = {'goal_text': 'хочу на всеросс', 'math_background': 'strong'}
    level_b, full_result_b = compute_provisional_level(chat_answers, return_full=True)

    # Save questionnaire result
    save_questionnaire_result_to_db(uid_b, level_b, chat_answers)

    # Write onboarding (same as routes/prep.py:2566)
    cs_b = CS.query.filter_by(user_id=uid_b).first()
    if cs_b is None:
        cs_b = CS(user_id=uid_b)
        db.session.add(cs_b)
    prep_state_b = getattr(cs_b, 'prep_state', None) or {}
    if not isinstance(prep_state_b, dict):
        prep_state_b = {}
    prep_state_b['onboarding'] = {
        'grade': full_result_b.grade,
        'target_level': full_result_b.target_level,
        'olymp_reach': full_result_b.olymp_reach,
        'daily_tasks': full_result_b.daily_tasks,
        'deadline_date': full_result_b.deadline_date,
        'days_left': full_result_b.days_left,
        'deadline_bucket': full_result_b.deadline_bucket,
        'prior_mu': full_result_b.prior_mu,
        'prior_sigma': full_result_b.prior_sigma,
        'start_level': full_result_b.start_level,
        'route_ceiling': full_result_b.route_ceiling,
        'test_length': full_result_b.test_length,
        'conflict': full_result_b.conflict,
        'anchors': [],
        'anchor_fallback_reasons': [],
        'answers': dict(chat_answers),
        'completed_at': datetime.utcnow().isoformat(),
    }
    cs_b.prep_state = prep_state_b
    cs_b.onboarding_done = True
    db.session.commit()

    # Read back
    cs_b2 = CS.query.filter_by(user_id=uid_b).first()
    ps_b = cs_b2.prep_state if isinstance(cs_b2.prep_state, dict) else json.loads(cs_b2.prep_state)
    ob_b = ps_b.get('onboarding', {})
    log(f'  onboarding_done = {cs_b2.onboarding_done}')
    log(f'  prep_state keys: {sorted(ps_b.keys())}')
    log(f'  onboarding subkeys ({len(ob_b)}): {sorted(ob_b.keys())}')
    for k in ['daily_tasks','route_ceiling','test_length','grade','target_level']:
        log(f'    {k} = {ob_b.get(k)}')

    # ─── COMPARISON ───
    log('')
    log('=== COMPARISON ===')
    f_a = set(ob_a.keys()); f_b = set(ob_b.keys())
    log(f'PATH A fields: {len(f_a)}')
    log(f'PATH B fields: {len(f_b)}')
    log(f'Fields match: {f_a == f_b}')
    log(f'Has 17 fields A={len(f_a)==17} B={len(f_b)==17}')
    common = f_a & f_b
    diffs = [(k, ob_a.get(k), ob_b.get(k)) for k in sorted(common) 
             if repr(ob_a.get(k)) != repr(ob_b.get(k))]
    log(f'Differing values: {len(diffs)}')
    for k, va, vb in diffs:
        log(f'  {k}: A={va!r} B={vb!r}')

    # Cleanup
    for uid in [uid_a, uid_b]:
        CS.query.filter_by(user_id=uid).delete()
        db.session.get(User, uid) and db.session.delete(db.session.get(User, uid))
    db.session.commit()

with open('_p3_final_out.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(OUT))
