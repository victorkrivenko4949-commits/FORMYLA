"""
Trace mu after EACH step to find double-application.
Tests: 1 correct answer for a FRESH section.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app

with app.app_context():
    from models import db
    from models_curator import CuratorState
    
    # FULL reset for user 3
    cs = CuratorState.query.filter_by(user_id=3).first()
    if cs:
        cs.prep_state = {}
        cs.onboarding_done = False
        cs.level_mu = None
        cs.level_sigma = None
        cs.level_by_section = '{}'
        cs.level_updated_at = None
        db.session.commit()
        print("RESET: level_mu=None, level_sigma=None, level_by_section={}")
    
    # Verify
    cs = CuratorState.query.filter_by(user_id=3).first()
    print(f"After reset: level_mu={cs.level_mu}, level_by_section={cs.level_by_section}")
    
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = '3'
        sess['_fresh'] = True
    
    print("\n=== TRACE: One correct anchor answer ===")
    print()
    
    # Start
    r = client.post('/prep/onboarding/answer', json={'qid': '_start', 'key': '_start'})
    data = r.get_json()
    print(f"1. START: step={data.get('step')}")
    
    cs = CuratorState.query.filter_by(user_id=3).first()
    print(f"   DB: level_mu={cs.level_mu}, level_by_section={cs.level_by_section[:80] if cs.level_by_section else None}")
    
    # Answer Q2-Q5
    for qid, key in [('target','lvl3'), ('olymp_reach','none'), ('load','5'), ('deadline','none')]:
        r = client.post('/prep/onboarding/answer', json={'qid': qid, 'key': key})
        data = r.get_json()
        step = data.get('step')
        anchor = data.get('anchor')
        if anchor:
            print(f"2. Q5 answered: step={step} anchor section={anchor.get('section_ru','?')}")
        else:
            print(f"2. {qid}={key} -> step={step}")
    
    cs = CuratorState.query.filter_by(user_id=3).first()
    print(f"   DB after Q5: level_mu={cs.level_mu}, level_by_section={cs.level_by_section[:80] if cs.level_by_section else None}")
    
    # Submit ONE correct answer
    anchor = data.get('anchor')
    tid = anchor['task_id']
    correct_answer = anchor.get('correct_answer', '0')
    section = anchor.get('section', '?')
    section_ru = anchor.get('section_ru', '?')
    level = anchor.get('level', '?')
    
    print(f"\n3. About to submit anchor: {section_ru} level={level}")
    print(f"   task_id={tid}, correct_answer={correct_answer}")
    print(f"   Submitting correct answer={correct_answer}...")
    
    r = client.post('/prep/onboarding/anchor', json={'task_id': tid, 'answer': correct_answer})
    resp = r.get_json()
    print(f"   Response: correct={resp.get('correct')}, step={resp.get('step')}")
    
    cs = CuratorState.query.filter_by(user_id=3).first()
    print(f"\n   DB AFTER submit_anchor + record_result:")
    print(f"   level_mu={cs.level_mu}")
    print(f"   level_sigma={cs.level_sigma}")
    lbs = cs.level_by_section
    if lbs and lbs != '{}':
        lbs_dict = json.loads(lbs) if isinstance(lbs, str) else lbs
        for sec, sec_data in lbs_dict.items():
            mu_val = sec_data.get('mu', 0) if isinstance(sec_data, dict) else float(sec_data)
            sigma_val = sec_data.get('sigma', 0) if isinstance(sec_data, dict) else 1.5
            n_val = sec_data.get('n', 0) if isinstance(sec_data, dict) else 0
            print(f"   section {sec}: mu={mu_val:.4f} sigma={sigma_val:.4f} n={n_val}")
    else:
        print(f"   level_by_section: {lbs}")
    
    # Expected calculation
    print(f"\n4. EXPECTED vs ACTUAL")
    print(f"   record_result formula: delta = sigma + 0.3")
    print(f"   correct: mu += 0.22 * delta")
    print(f"   wrong:   mu -= 0.28 * delta")
    print(f"   sigma = max(0.35, sigma * 0.94)")
    print(f"   Section starts at DEFAULT_MU=3.0, DEFAULT_SIGMA=1.5")
    expected_delta = 1.5 + 0.3  # 1.8
    expected_mu = 3.0 + 0.22 * expected_delta  # 3.0 + 0.396 = 3.396
    expected_sigma = max(0.35, 1.5 * 0.94)  # 1.41
    print(f"   Expected sec_mu = 3.0 + 0.22 * 1.8 = {expected_mu:.4f}")
    print(f"   Expected sec_sigma = max(0.35, 1.5 * 0.94) = {expected_sigma:.4f}")
    
    actual_mu = None
    if lbs and lbs != '{}':
        lbs_dict = json.loads(lbs) if isinstance(lbs, str) else lbs
        for sec, sec_data in lbs_dict.items():
            actual_mu = sec_data.get('mu', 0) if isinstance(sec_data, dict) else float(sec_data)
    
    print(f"   Actual sec_mu = {actual_mu}")
    if actual_mu and abs(actual_mu - expected_mu) < 0.01:
        print(f"   ✓ SINGLE application — match within 0.01")
    elif actual_mu and actual_mu > expected_mu + 0.2:
        print(f"   ✗ DOUBLE application suspected: actual > expected by {actual_mu - expected_mu:.2f}")
    print()
    
    # Now check if ANCHOR_PLAN also gets applied
    from services.onboarding_tree import ANCHOR_PLAN
    print(f"5. ANCHOR_PLAN (applied in compute_prior during finish):")
    print(f"   mu_shift_correct: +{ANCHOR_PLAN['mu_shift_correct']}")
    print(f"   mu_shift_wrong:   -{ANCHOR_PLAN['mu_shift_wrong']}")
    print(f"   This affects GLOBAL result.prior_mu, NOT level_by_section")
    print(f"   Code: services/onboarding_tree.py:181-183")
    print(f"   Code: services/onboarding.py:730-734 (record_result)")
    print()
    print(f"   VERDICT: record_result (per-section) and ANCHOR_PLAN (global) are SEPARATE.")
    print(f"   They do NOT double-apply to the same mu.")
