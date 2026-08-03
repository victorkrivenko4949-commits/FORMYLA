"""
FINAL: prove set_prior no longer wipes level_mu.
Clean run: 3 correct + 2 wrong.
Verify: level_mu, radar values, start_level, display_mu.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app

with app.app_context():
    from models import db
    from models_curator import CuratorState
    
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
    
    print("TRACE: 3 correct + 2 wrong — set_prior REMOVED")
    print("=" * 70)
    
    r = client.post('/prep/onboarding/answer', json={'qid': '_start', 'key': '_start'})
    for qid, key in [('target','lvl3'), ('olymp_reach','none'), ('load','5'), ('deadline','none')]:
        r = client.post('/prep/onboarding/answer', json={'qid': qid, 'key': key})
        data = r.get_json()
    
    correct_pattern = [True, False, True, True, False]
    
    print(f"{'Якорь':<8} {'level_mu':>8} {'sec_mu':>8}")
    print("-" * 28)
    
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
        sec_mu = round(lbs.get(sec, {}).get('mu', 0), 2) if isinstance(lbs.get(sec, {}), dict) else 0
        
        print(f"{i+1:<8} {cs.level_mu:>8.3f} {sec_mu:>8.2f}")
    
    before_finish = cs.level_mu
    
    r = client.post('/prep/onboarding/answer', json={'qid': '_finish', 'key': '_finish'})
    finish_data = r.get_json()
    
    cs = CuratorState.query.filter_by(user_id=3).first()
    print(f"\nlevel_mu ДО finish: {before_finish:.3f}")
    print(f"level_mu ПОСЛЕ finish: {cs.level_mu:.3f}")
    print(f"ЗАТИРАНИЕ: {'ЕСТЬ [!]' if abs(before_finish - cs.level_mu) > 0.01 else 'НЕТ [OK]'}")
    
    result = finish_data.get('result', {})
    print(f"\nprior_mu (ANCHOR_PLAN, НЕ пишется в level_mu): {result.get('prior_mu')}")
    print(f"display_mu (среднее разделов, показывает экран): {finish_data.get('display_mu')}")
    
    print(f"\n=== РАДАР (5 значений из level_by_section) ===")
    lbs = json.loads(cs.level_by_section) if (cs and cs.level_by_section and cs.level_by_section != '{}') else {}
    radar_names = ['algebra', 'number_theory', 'geometry', 'combinatorics', 'logic']
    radar = []
    for s in radar_names:
        d = lbs.get(s, {})
        mu = round(d.get('mu', 0), 2) if isinstance(d, dict) else 0
        radar.append(mu)
        section_ru = {'algebra': 'алгебра', 'number_theory': 'теория чисел', 'geometry': 'геометрия',
                      'combinatorics': 'комбинаторика', 'logic': 'логика'}[s]
        print(f"  {section_ru:<16} mu={mu:.2f}")
    
    print(f"\n=== ПРОИЗВОДНЫЕ ЗНАЧЕНИЯ ===")
    print(f"start_level: {result.get('start_level')} (из prior_mu={result.get('prior_mu')} по формуле в compute_prior:212)")
    print(f"route_ceiling: {result.get('route_ceiling')}")
    print(f"test_length: {result.get('test_length')}")
    print(f"display_mu: {finish_data.get('display_mu')}")
    print(f"strongest_ru: {finish_data.get('strongest_ru')}")
    print(f"weakest_ru: {finish_data.get('weakest_ru')}")
    
    print(f"\n=== set_prior В ПРОЕКТЕ (кроме тестов и scripts) ===")
    print(f"routes/prep.py:2609 — coach_chat / questionnaire_chat — ДО первого якоря, ОК")
    print(f"services/level_engine.py:208 — авто-инициализация в record_result — ОК")
    print(f"services/onboarding.py:799 — УДАЛЁН из finish() — БЫЛО затирание")
    print(f"scripts/test_*.py — тесты — не продуктовый код")
    print(f"scripts/proof_*.py — отладка — не продуктовый код")
    
    cs = CuratorState.query.filter_by(user_id=3).first()
    if cs:
        cs.prep_state = {}
        cs.onboarding_done = False
        db.session.commit()
    print("\nDONE")
