# -*- coding: utf-8 -*-
"""
READ-ONLY script: show student state for debugging.
Usage:
    python scripts/show_student_state.py <email>

Prints:
  - user_id, класс (grade)
  - curator_state: onboarding_done, level_mu, level_sigma, level_updated_at
  - level_by_section — table: section / n / mu / sigma
  - prep_state['onboarding'] целиком
  - prep_state['test_queue'] целиком
  - prep_state['last_test'] целиком

No DB writes. No production DB connections.
"""
import json
import sys

if len(sys.argv) < 2:
    print("Usage: python scripts/show_student_state.py <email>")
    sys.exit(1)

email = sys.argv[1].strip()

# Use the same DB as the app (relative to project root)
import os
import sys
_proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)
os.chdir(_proj_root)

from app import app, db
from models import User
from models_curator import CuratorState

with app.app_context():
    user = User.query.filter_by(email=email).first()
    if not user:
        print(f"ERROR: User with email '{email}' not found.")
        sys.exit(1)

    print("=" * 70)
    print(f"user_id  : {user.id}")
    print(f"email    : {user.email}")
    print(f"name     : {user.name or '(not set)'}")
    print(f"класс    : {user.preferred_grade or '(not set)'}")
    print("=" * 70)

    cs = CuratorState.query.filter_by(user_id=user.id).first()
    if not cs:
        print("CuratorState: NOT FOUND (no row for this user)")
        sys.exit(0)

    # --- curator_state core fields ---
    print()
    print("── curator_state ──────────────────────────────────────────────")
    print(f"  onboarding_done   : {cs.onboarding_done}")
    print(f"  level_mu          : {cs.level_mu}")
    print(f"  level_sigma       : {cs.level_sigma}")
    print(f"  level_updated_at  : {cs.level_updated_at or '(null)'}")
    if cs.grade:
        print(f"  grade (curator)   : {cs.grade}")

    # --- level_by_section ---
    print()
    print("── level_by_section ──────────────────────────────────────────")
    lbs_raw = cs.level_by_section
    if not lbs_raw:
        print("  (empty)")
    else:
        try:
            if isinstance(lbs_raw, str):
                lbs = json.loads(lbs_raw)
            else:
                lbs = lbs_raw  # already a dict

            if isinstance(lbs, dict):
                # Try common shapes
                if any(isinstance(v, dict) for v in lbs.values()):
                    # shape: {section: {n: X, mu: Y, sigma: Z}}
                    print(f"  {'section':<30s} {'n':>6s}  {'mu':>8s}  {'sigma':>8s}")
                    print(f"  {'─'*30} {'─'*6}  {'─'*8}  {'─'*8}")
                    for sec, data in sorted(lbs.items()):
                        if isinstance(data, dict):
                            n = data.get('n', '?')
                            mu = data.get('mu', '?')
                            sigma = data.get('sigma', '?')
                            print(f"  {sec:<30s} {str(n):>6s}  {str(mu):>8s}  {str(sigma):>8s}")
                        else:
                            print(f"  {sec:<30s} {str(data):>6s}")
                else:
                    # flat: {section: value}
                    for sec, val in sorted(lbs.items()):
                        print(f"  {sec:<30s} {str(val):>6s}")
            else:
                print(f"  (unexpected type: {type(lbs).__name__})")
                print(f"  raw: {lbs_raw}")
        except json.JSONDecodeError:
            print(f"  (invalid JSON, raw): {lbs_raw}")
        except Exception as e:
            print(f"  (parse error: {e})")
            print(f"  raw: {lbs_raw}")

    # --- prep_state ---
    print()
    print("── prep_state ────────────────────────────────────────────────")
    ps = cs.prep_state
    if not ps:
        print("  (empty)")
    else:
        if isinstance(ps, str):
            try:
                ps = json.loads(ps)
            except json.JSONDecodeError:
                print(f"  (invalid JSON, raw): {ps}")
                ps = None

        if isinstance(ps, dict):
            print()
            print("  [onboarding]:")
            onb = ps.get('onboarding')
            if onb is None:
                print("    (null / not set)")
            else:
                print(f"    {json.dumps(onb, indent=4, ensure_ascii=False, default=str)}")

            print()
            print("  [test_queue]:")
            tq = ps.get('test_queue')
            if tq is None:
                print("    (null / not set)")
            elif isinstance(tq, list):
                print(f"    length = {len(tq)}")
                for i, item in enumerate(tq):
                    print(f"    [{i}] {json.dumps(item, ensure_ascii=False, default=str)}")
            else:
                print(f"    {json.dumps(tq, indent=4, ensure_ascii=False, default=str)}")

            print()
            print("  [last_test]:")
            lt = ps.get('last_test')
            if lt is None:
                print("    (null / not set)")
            else:
                print(f"    {json.dumps(lt, indent=4, ensure_ascii=False, default=str)}")
        else:
            print(f"  (unexpected prep_state type: {type(ps).__name__})")
            print(f"  raw: {ps}")

    print()
    print("=" * 70)
    print("Done (read-only, no modifications made).")
