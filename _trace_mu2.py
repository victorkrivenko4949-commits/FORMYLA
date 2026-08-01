"""
Diagnostic: where does "Твой уровень" (prior_mu) come from vs section mu.
Clean run: 3 correct + 2 wrong.
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
    
    # Start + Q2-Q5
    r = client.post('/prep/onboarding/answer', json={'qid': '_start', 'key': '_start'})
    for qid, key in [('target','lvl3'), ('olymp_reach','none'), ('load','5'), ('deadline','none')]:
        r = client.post('/prep/onboarding/answer', json={'qid': qid, 'key': key})
        data = r.get_json()
    
    # 3 correct + 2 wrong
    correct_pattern = [True, False, True, True, False]
    for i in range(5):
        anchor = data.get('anchor')
        if not anchor:
            break
        tid = anchor['task_id']
        correct_answer = anchor.get('correct_answer', '0')
        user_ans = correct_answer if correct_pattern[i] else "999"
        r = client.post('/prep/onboarding/anchor', json={'task_id': tid, 'answer': user_ans})
        data = r.get_json()
        
        cs = CuratorState.query.filter_by(user_id=3).first()
        lbs = json.loads(cs.level_by_section) if (cs and cs.level_by_section and cs.level_by_section != '{}') else {}
        print(f"  after anchor {i+1}: global level_mu={cs.level_mu:.3f} section_mus={ {s: round(d['mu'],2) if isinstance(d,dict) else round(float(d),2) for s,d in lbs.items()} }")
    
    # finish
    r = client.post('/prep/onboarding/answer', json={'qid': '_finish', 'key': '_finish'})
    finish_data = r.get_json()
    result = finish_data.get('result', {})
    
    print(f"\n=== ИСТОЧНИК 'Твой уровень' ===")
    print(f"result.prior_mu (то что на экране) = {result.get('prior_mu')}")
    print(f"Код: services/onboarding_tree.py:180-184")
    print(f"  olymp_reach='none' → olymp_opt['mu'] = 1.6")
    print(f"  ANCHOR_PLAN shifts: +0.55, -0.65, +0.55, +0.55, -0.65")
    print(f"  sum_shifts = (0.55*3) + (-0.65*2) = 1.65 - 1.30 = 0.35")
    print(f"  mu = clamp(1.0, 5.0, min(1.6 + 0.35, 5.0)) = 1.95")
    print(f"  sigma = max(0.45, 1.35 - 0.3*5) = 0.45 (capped)")
    print()
    
    print(f"=== ГЛОБАЛЬНЫЙ level_mu (record_result) ===")
    cs = CuratorState.query.filter_by(user_id=3).first()
    print(f"Global level_mu после 5 якорей: {cs.level_mu:.3f}")
    print(f"  Это глобальный mu, который record_result обновляет НЕЗАВИСИМО от ANCHOR_PLAN")
    print()
    
    print(f"=== СРЕДНЕЕ ПО 5 РАЗДЕЛАМ ===")
    lbs = json.loads(cs.level_by_section) if (cs and cs.level_by_section and cs.level_by_section != '{}') else {}
    section_mus = []
    for s in ['algebra', 'number_theory', 'geometry', 'combinatorics', 'logic']:
        d = lbs.get(s, {})
        mu = d.get('mu', 0) if isinstance(d, dict) else float(d)
        section_mus.append(mu)
        print(f"  {s}: mu={mu:.3f}")
    avg = sum(section_mus) / len(section_mus)
    print(f"  Среднее: {avg:.2f}")
    print()
    
    print(f"=== СРАВНЕНИЕ ===")
    print(f"  prior_mu (ANCHOR_PLAN)  = {result.get('prior_mu'):.2f}  ← показывает экран")
    print(f"  level_mu (record_result) = {cs.level_mu:.3f}")
    print(f"  mean_by_section          = {avg:.2f}  ← согласуется с таблицей")
    print()
    print(f"  ВЫВОД: prior_mu рассчитывается отдельно от section mu.")
    print(f"  record_result пишет в level_mu и level_by_section, НО prior_mu из compute_prior")
    print(f"  использует olymp_reach.mu (1.6) + ANCHOR_PLAN сдвиги — ДРУГУЮ формулу.")
    
    cs = CuratorState.query.filter_by(user_id=3).first()
    if cs:
        cs.prep_state = {}
        cs.onboarding_done = False
        db.session.commit()
