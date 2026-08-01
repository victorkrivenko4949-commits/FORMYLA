# -*- coding: utf-8 -*-
"""Diagnose section mu compounding bug in record_result."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
tmp_db = tempfile.mktemp(suffix='.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + tmp_db
os.environ['FLASK_ENV'] = 'development'

from app import app, db
from models_curator import CuratorState

app.config['TESTING'] = True
app.config['SECRET_KEY'] = 'diag'
app.config['WTF_CSRF_ENABLED'] = False
app.config['SERVER_NAME'] = 'diag.local'

with app.app_context():
    db.create_all()

    from services.level_engine import (
        record_result, get_state, DEFAULT_MU, DEFAULT_SIGMA,
        CORRECT_DELTA_FACTOR, WRONG_DELTA_FACTOR, SIGMA_OFFSET,
        SIGMA_DECAY, MIN_SIGMA, MIN_MU, MAX_MU,
    )
    from services.anchors import load_anchors, pick_anchors
    from models import User

    u = User(id=1, email='diag@test.com', preferred_grade=9)
    db.session.add(u)
    db.session.commit()

    r = load_anchors()
    print(f"Anchors loaded: {r['loaded']}")
    anchors, _ = pick_anchors(9)

    # ── Print record_result source ──
    print()
    print("="*60)
    print("record_result CODE (services/level_engine.py:183-260)")
    print("="*60)
    with open('services/level_engine.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for i in range(182, 261):
        print(f"{i+1:>4}|{lines[i]}", end='')

    print()
    print("="*60)
    print("BUG: line 238")
    print("  by_section.get(section, {'mu': mu, ...})")
    print("  uses CURRENT GLOBAL mu, not DEFAULT_MU=3.0")
    print("  -> each new section inherits the compounded global")
    print("="*60)

    # ── Step-by-step: one anchor at a time ──
    sections_order = [a['section'] for a in anchors]

    for step_idx, anchor in enumerate(anchors):
        section = anchor['section']
        level = anchor['level']

        print(f"\n{'='*60}")
        print(f"STEP {step_idx+1}: {anchor['anchor_uid']} section={section} level={level} correct=True")
        print(f"{'='*60}")

        # State before
        st_before = get_state(1)
        global_mu_before = st_before['mu']
        global_sigma_before = st_before.get('sigma', DEFAULT_SIGMA)
        by_sec_before = st_before.get('by_section', {})

        print(f"  GLOBAL before: mu={global_mu_before:.4f} sigma={global_sigma_before:.4f}")

        # Hand compute: what SHOULD happen with DEFAULT_MU init vs actual
        # Global update:
        delta = global_sigma_before + SIGMA_OFFSET
        global_mu_expected = global_mu_before + CORRECT_DELTA_FACTOR * delta
        global_sigma_expected = max(MIN_SIGMA, global_sigma_before * SIGMA_DECAY)

        print(f"  Global delta = 0.22 * ({global_sigma_before:.4f} + 0.3) = {CORRECT_DELTA_FACTOR * delta:.4f}")
        print(f"  Global mu expected: {global_mu_before:.4f} + {CORRECT_DELTA_FACTOR * delta:.4f} = {global_mu_expected:.4f}")

        # Call record_result
        result = record_result(1, section, int(level), True)
        actual_global_mu = result['mu']
        actual_by_sec = result.get('by_section', {})

        print(f"  Global mu ACTUAL after: {actual_global_mu:.4f}")

        # Show all sections
        print(f"\n  {'Section':<20} {'mu':>8} {'sigma':>8} {'n':>4}  {'expected_if_DEFAULT_init':>25}")
        print(f"  {'-'*20} {'-'*8} {'-'*8} {'-'*4}  {'-'*25}")

        for sec in ['algebra', 'number_theory', 'geometry', 'combinatorics', 'logic']:
            sec_data = actual_by_sec.get(sec, {})
            sec_mu = sec_data.get('mu', float('nan'))
            sec_sigma = sec_data.get('sigma', float('nan'))
            sec_n = sec_data.get('n', 0)

            # What it WOULD be if section started from DEFAULT_MU
            if sec == section and sec_data:
                # First hit for this section
                sigma_for_calc = DEFAULT_SIGMA
                expected_sec_mu = DEFAULT_MU + CORRECT_DELTA_FACTOR * (sigma_for_calc + SIGMA_OFFSET)
            elif sec in actual_by_sec:
                expected_sec_mu = sec_mu  # already computed, same
            else:
                expected_sec_mu = float('nan')

            exp_str = f"{expected_sec_mu:.4f}" if not (isinstance(expected_sec_mu, float) and expected_sec_mu != expected_sec_mu) else "N/A"
            print(f"  {sec:<20} {sec_mu:>8.4f} {sec_sigma:>8.4f} {sec_n:>4d}  {exp_str:>25}")

        # Hand calc: what would section mu be with proper DEFAULT init
        if section in actual_by_sec:
            sec_actual = actual_by_sec[section]
            global_at_call_time = global_mu_before + CORRECT_DELTA_FACTOR * (global_sigma_before + SIGMA_OFFSET)
            # Buggy: section starts from global_at_call_time
            with_bug = global_at_call_time + CORRECT_DELTA_FACTOR * (max(MIN_SIGMA, global_sigma_before * SIGMA_DECAY) + SIGMA_OFFSET)
            # Fixed: section starts from DEFAULT_MU
            with_fix = DEFAULT_MU + CORRECT_DELTA_FACTOR * (DEFAULT_SIGMA + SIGMA_OFFSET)

            print(f"\n  BUG: sec inherits global mu={global_at_call_time:.4f} -> sec_mu={sec_actual['mu']:.4f}")
            print(f"  FIX: sec starts from DEFAULT_MU={DEFAULT_MU} -> sec_mu={with_fix:.4f}")

    db.drop_all()

print("\nDONE")
