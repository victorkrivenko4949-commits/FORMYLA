# -*- coding: utf-8 -*-
"""D1-D4 diagnostic — writes results to _d1d4.txt"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models_curator import CuratorState
from models import User

out = []
def p(s=""): out.append(s); print(s)

TARGET = 'victor.krivenko.4949@gmail.com'

with app.app_context():
    u = User.query.filter_by(email=TARGET).first()
    uid = u.id if u else None

    if not u:
        p(f"USER NOT FOUND: {TARGET}")
    else:
        # ============== D1 ==============
        cs = CuratorState.query.filter_by(user_id=uid).first()
        p("=== D1: CuratorState BEFORE ===")
        if cs:
            p(f"onboarding_done={cs.onboarding_done}")
            ps = cs.prep_state
            if isinstance(ps, str):
                try: ps = json.loads(ps)
                except: pass
            p(f"prep_state type={type(ps).__name__}")
            if isinstance(ps, dict):
                p(f"prep_state keys={list(ps.keys())}")
                onboard = ps.get('onboarding', {})
                if onboard:
                    p(f"  onboarding.completed_at={onboard.get('completed_at','N/A')}")
                mc = ps.get('monthly_cycle', {})
                if mc:
                    p(f"  monthly_cycle themes={mc.get('themes','N/A')}")
                    p(f"  monthly_cycle day_index={mc.get('day_index','N/A')}")
            else:
                p(f"prep_state={ps}")
            p(f"level_by_section={cs.level_by_section}")
            p(f"level_mu={cs.level_mu}  level_sigma={cs.level_sigma}")
            p(f"probe_json len={len(cs.probe_json) if cs.probe_json else 0}")
        else:
            p("NO CuratorState")

with open('_d1d4.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
p("DONE")
