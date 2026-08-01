# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app import app, db
from models_curator import CuratorState
import json

with app.app_context():
    rows = CuratorState.query.filter(CuratorState.prep_state != None).limit(20).all()
    print(f'Total rows with non-null prep_state: {len(rows)}')
    for cs in rows:
        ps = cs.prep_state
        if isinstance(ps, str):
            ps = json.loads(ps)
        keys = list(ps.keys()) if isinstance(ps, dict) else ['NOT_A_DICT', type(ps).__name__]
        print(f'user_id={cs.user_id}: keys={keys}')
        for k in keys:
            v = ps[k]
            if isinstance(v, dict):
                print(f'  {k}: subkeys={list(v.keys())}')
                for sk in sorted(v.keys()):
                    sv = str(v[sk])
                    print(f'    {sk}: {sv[:120]}')
            else:
                print(f'  {k}: {str(v)[:120]}')
        print()
