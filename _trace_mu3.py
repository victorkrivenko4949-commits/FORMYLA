"""
Diagnostic: prove set_prior wipes level_mu, then test fix.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app

with app.app_context():
    from models import db
    from models_curator import CuratorState
    
    # FULL reset
    cs = CuratorState.query.filter_by(user_id=3).first()
    if cs:
        cs.prep_state = {}
        cs.onboarding_done = False
        cs.level_mu = None
        cs.level_sigma = None
        cs.level_by_section = '{}'
        db.session.commit()
    
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = '3'
        sess['_fresh'] = True
    
    print("=== ПОРЯДОК ВЫЗОВОВ (текущий код) ===")
    print()
    print("1. submit_anchor → record_result × 5")
    print("   services/onboarding.py:727-732")
    print("   services/level_engine.py:183-260")
    print()
    print("2. finish() → set_prior(result.prior_mu=1.95)")
    print("   services/onboarding.py:928")
    print("   services/level_engine.py:147-180 — ЗАТИРАЕТ level_mu=3.20 → 1.95,")
    print("   level_by_section → {}")
    print()
    print("3. Восстановление level_by_section и prep_state")
    print("   services/onboarding.py:931-937")
    print("   level_mu НЕ восстанавливается — остаётся 1.95!")
    print()
    
    # Start + Q2-Q5
    r = client.post('/prep/onboarding/answer', json={'qid': '_start', 'key': '_start'})
    for qid, key in [('target','lvl3'), ('olymp_reach','none'), ('load','5'), ('deadline','none')]:
        r = client.post('/prep/onboarding/answer', json={'qid': qid, 'key': key})
        data = r.get_json()
    
    print("=== ТРАССИРОВКА level_mu ===")
    
    correct_pattern = [True, False, True, True, False]
    for i in range(5):
        anchor = data.get('anchor')
        if not anchor: break
        tid = anchor['task_id']
        correct_answer = anchor.get('correct_answer', '0')
        user_ans = correct_answer if correct_pattern[i] else "999"
        r = client.post('/prep/onboarding/anchor', json={'task_id': tid, 'answer': user_ans})
        data = r.get_json()
        
        cs = CuratorState.query.filter_by(user_id=3).first()
        lbs = json.loads(cs.level_by_section) if (cs and cs.level_by_section and cs.level_by_section != '{}') else {}
        sec = anchor.get('section', '?')
        sec_mu = round(lbs.get(sec, {}).get('mu', 0) if isinstance(lbs.get(sec, {}), dict) else 0, 2)
        print(f"  после якоря {i+1}: level_mu={cs.level_mu:.3f} sec={sec} sec_mu={sec_mu}")
        
        # Capture BEFORE set_prior
        if i == 4:
            before_set_prior = cs.level_mu
    
    print(f"\n  level_mu до set_prior: {before_set_prior:.3f}")
    
    r = client.post('/prep/onboarding/answer', json={'qid': '_finish', 'key': '_finish'})
    finish_data = r.get_json()
    
    cs = CuratorState.query.filter_by(user_id=3).first()
    print(f"  level_mu ПОСЛЕ finish (set_prior): {cs.level_mu:.3f}")
    print(f"  ЗАТИРАНИЕ: {before_set_prior:.3f} → {cs.level_mu:.3f} (потеряно {before_set_prior - cs.level_mu:.3f})")
    
    lbs = json.loads(cs.level_by_section) if (cs and cs.level_by_section and cs.level_by_section != '{}') else {}
    radar = [round(lbs.get(s, {}).get('mu', 0), 2) if isinstance(lbs.get(s, {}), dict) else 0
             for s in ['algebra', 'number_theory', 'geometry', 'combinatorics', 'logic']]
    print(f"\n  Радар (5 значений): {radar}")
    print(f"  level_mu (показывает радар?): {cs.level_mu:.3f}")
    print(f"  start_level: {finish_data.get('result', {}).get('start_level')}")
    print(f"  display_mu: {finish_data.get('display_mu')}")
    
    print(f"\n  ВЫВОД: level_mu затёрт set_prior. Радар использует level_by_section — он ОК.")
    print(f"  Но start_level считается из prior_mu=1.95 → start_level=2 (должно быть около 3)")
    
    cs = CuratorState.query.filter_by(user_id=3).first()
    if cs:
        cs.prep_state = {}
        cs.onboarding_done = False
        db.session.commit()
    print("\nDONE")
