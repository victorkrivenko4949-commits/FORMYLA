# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from app import app, db
from models_curator import CuratorState

out = []
with app.app_context():
    rows = CuratorState.query.filter(CuratorState.prep_state != None).all()
    out.append(f'Total curator_state rows: {len(rows)}')

    has_onb = has_q = has_both = has_mc = 0
    for cs in rows:
        ps = cs.prep_state if isinstance(cs.prep_state, dict) else json.loads(cs.prep_state)
        if not isinstance(ps, dict): continue
        if 'onboarding' in ps: has_onb += 1
        if 'questionnaire' in ps: has_q += 1
        if 'onboarding' in ps and 'questionnaire' in ps: has_both += 1
        if 'monthly_cycle' in ps: has_mc += 1

    out.append(f'HAS onboarding:    {has_onb}')
    out.append(f'HAS questionnaire: {has_q}')
    out.append(f'HAS BOTH:          {has_both}')
    out.append(f'HAS monthly_cycle: {has_mc}')

    all_keys = set()
    for cs in rows:
        ps = cs.prep_state if isinstance(cs.prep_state, dict) else json.loads(cs.prep_state)
        if isinstance(ps, dict): all_keys.update(ps.keys())
    out.append(f'ALL keys ever used: {sorted(all_keys)}')

    # Show detailed prep_state for first user with onboarding or questionnaire
    for cs in rows:
        ps = cs.prep_state if isinstance(cs.prep_state, dict) else json.loads(cs.prep_state)
        if isinstance(ps, dict) and ('onboarding' in ps or 'questionnaire' in ps):
            out.append(f'\n=== user_id={cs.user_id} ===')
            for k in ps:
                v = ps[k]
                if isinstance(v, dict):
                    out.append(f'  {k}:')
                    for sk in sorted(v.keys()):
                        out.append(f'    {sk}: {str(v[sk])[:200]}')
                else:
                    out.append(f'  {k}: {str(v)[:200]}')
            break

with open(os.path.join(os.path.dirname(__file__), '_prep_state_keys.txt'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print('done')
