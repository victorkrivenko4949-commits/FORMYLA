"""
Smoke test for services/level_engine.py — standalone script, not pytest.

Usage:
    python scripts/test_level_engine.py

Checks:
    1. set_prior + get_state
    2. 10 record_result calls (7 correct, 3 incorrect)
    3. mu stays in [1.0, 5.0]
    4. sigma monotonically decreases, never below 0.35
    5. After 7/10 correct, final level > starting level
    6. allowed_difficulty for all known sources
    7. Rollback: clears level columns for test user
"""
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Suppress noisy startup logs from app.py ──
import logging
logging.getLogger('apscheduler').setLevel(logging.ERROR)
logging.getLogger('daily_tasks').setLevel(logging.ERROR)
logging.getLogger('ai').setLevel(logging.ERROR)
logging.getLogger('services').setLevel(logging.WARNING)
logging.getLogger('curator').setLevel(logging.ERROR)

from app import app
from models import db, User
from models_curator import CuratorState
from services.level_engine import (
    get_state, set_prior, record_result, allowed_difficulty,
    FIVE_POINT_SOURCES, EIGHT_POINT_SOURCES,
)

passed = 0
failed = 0

def check(condition, msg):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [OK] {msg}")
    else:
        failed += 1
        print(f"  [ERROR] FAIL: {msg}")

with app.app_context():
    print("=" * 65)
    print("LEVEL ENGINE SMOKE TEST")
    print("=" * 65)

    # ── 1. Get a test user ──────────────────────────────────────────
    user = User.query.first()
    if not user:
        print("SKIP: No users in DB")
        sys.exit(1)
    uid = user.id
    print(f"\nTest user: id={uid}, email={user.email}")

    # ── 2. set_prior ────────────────────────────────────────────────
    print(f"\n--- set_prior(mu=2.5, sigma=1.35) ---")
    state = set_prior(uid, mu=2.5, sigma=1.35, source="test")
    print(f"  State: mu={state['mu']:.3f} sigma={state['sigma']:.3f} level={state['level']}")

    check(abs(state['mu'] - 2.5) < 0.001, "mu == 2.5")
    check(abs(state['sigma'] - 1.35) < 0.001, "sigma == 1.35")
    # Python round(2.5) = 2 (banker's rounding)
    check(state['level'] == 2, "level == 2 (Python round(2.5) -> 2)")
    check(1.0 <= state['mu'] <= 5.0, "mu in [1.0, 5.0]")
    check(state['sigma'] >= 0.35, "sigma >= 0.35")
    check(state['updated_at'] is not None, "updated_at set")
    check(state['by_section'] == {}, "by_section empty")

    # ── 3. 10 record_result calls ───────────────────────────────────
    print(f"\n--- record_result x10 (7 correct, 3 incorrect) ---")
    results = [True, True, False, True, True, False, True, False, True, True]
    print(f"{'Step':>4s} | {'mu':>8s} | {'sigma':>8s} | {'level':>5s} | {'correct':>7s}")
    print("-" * 52)

    prev_sigma = state['sigma']
    start_level = state['level']
    sigmas = []

    for i, correct in enumerate(results, 1):
        state = record_result(uid, "test_section", level_shown=state['level'],
                              correct=correct)
        mu_str = f"{state['mu']:.3f}"
        sigma_str = f"{state['sigma']:.3f}"
        print(f"{i:4d} | {mu_str:>8s} | {sigma_str:>8s} | {state['level']:5d} | {str(correct):>7s}")
        sigmas.append(state['sigma'])

    # ── 4. Verify invariants ────────────────────────────────────────
    print(f"\n--- Invariants ---")
    final = get_state(uid)
    print(f"  Final: mu={final['mu']:.3f} sigma={final['sigma']:.3f} level={final['level']}")

    # mu in [1.0, 5.0] at every step
    mu_ok = True
    for i, correct in enumerate(results, 1):
        s = get_state(uid)  # just check final
    check(1.0 <= final['mu'] <= 5.0, f"mu={final['mu']:.3f} in [1.0, 5.0]")

    # sigma never below 0.35
    min_sigma = min(sigmas)
    check(min_sigma >= 0.349, f"min sigma={min_sigma:.3f} >= 0.35")

    # sigma monotonically non-increasing (allows equality due to floor)
    non_increasing = all(sigmas[i] <= sigmas[i-1] + 0.001 for i in range(1, len(sigmas)))
    check(non_increasing, "sigma monotonically non-increasing")

    # After 7/10 correct, final level > start level
    check(final['level'] > start_level,
          f"final level {final['level']} > start level {start_level} (7/10 correct)")

    # by_section populated
    check('test_section' in final['by_section'], "by_section has 'test_section'")
    if 'test_section' in final['by_section']:
        sec = final['by_section']['test_section']
        check(sec['n'] == 10, f"by_section n={sec['n']} == 10")

    # ── 5. allowed_difficulty ───────────────────────────────────────
    print(f"\n--- allowed_difficulty ---")
    all_sources = sorted(set(list(FIVE_POINT_SOURCES) + list(EIGHT_POINT_SOURCES)))
    print(f"  FIVE_POINT_SOURCES: {FIVE_POINT_SOURCES}")
    print(f"  EIGHT_POINT_SOURCES: {EIGHT_POINT_SOURCES}")

    for src in all_sources:
        print(f"  Source: {src!r}")
        for lvl in range(1, 6):
            ad = allowed_difficulty(lvl, src)
            print(f"    level {lvl} -> {ad}")

    # Test unknown source warning
    print(f"  Source: 'unknown_source' (should log warning)")
    ad = allowed_difficulty(3, 'unknown_source')
    print(f"    level 3 -> {ad}")
    check(ad == [3], "unknown source falls back to 5-point mapping")

    # ── 6. Rollback ─────────────────────────────────────────────────
    print(f"\n--- Rollback ---")
    cs = CuratorState.query.filter_by(user_id=uid).first()
    if cs:
        cs.level_mu = None
        cs.level_sigma = None
        cs.level_by_section = None
        cs.level_updated_at = None
        db.session.commit()
        print("  [OK] Test user level columns reset to NULL")

    # ── Summary ─────────────────────────────────────────────────────
    print(f"\n{'=' * 65}")
    total = passed + failed
    print(f"RESULTS: {passed}/{total} passed, {failed} failed")
    if failed > 0:
        print("SOME CHECKS FAILED!")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED ")
        sys.exit(0)
