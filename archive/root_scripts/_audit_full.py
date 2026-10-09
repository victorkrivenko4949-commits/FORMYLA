# -*- coding: utf-8 -*-
import sys, os, json, io
sys.path.insert(0, os.path.dirname(__file__))
from app import app, db
from models_curator import CuratorState

out_lines = []

with app.app_context():
    cs = CuratorState.query.filter_by(user_id=1).first()
    ps = cs.prep_state if isinstance(cs.prep_state, dict) else json.loads(cs.prep_state)
    out_lines.append(f'user_id=1: ALL_KEYS={sorted(ps.keys())}')
    for k in sorted(ps.keys()):
        v = ps[k]
        if isinstance(v, dict):
            out_lines.append(f'  {k}: {len(v)} subkeys = {sorted(v.keys())}')
            for sk in sorted(v.keys()):
                sv = repr(v[sk])
                out_lines.append(f'    {sk}: {sv[:200]}')
        else:
            out_lines.append(f'  {k}: {repr(v)[:200]}')
    out_lines.append(f'  onboarding_done={cs.onboarding_done}')

    out_lines.append('')
    rows = CuratorState.query.filter(CuratorState.prep_state != None).all()
    for cs2 in rows:
        ps2 = cs2.prep_state if isinstance(cs2.prep_state, dict) else json.loads(cs2.prep_state)
        if isinstance(ps2, dict) and 'onboarding' in ps2:
            ob = ps2['onboarding']
            out_lines.append(f'user_id={cs2.user_id}: ob_keys={sorted(ob.keys())} daily_tasks={ob.get("daily_tasks")} route_ceiling={ob.get("route_ceiling")} grade={ob.get("grade")}')

with open(os.path.join(os.path.dirname(__file__), '_audit_full.txt'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(out_lines))
print('done')
