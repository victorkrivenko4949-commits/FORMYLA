# -*- coding: utf-8 -*-
"""Acceptance test for reset verification."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ['ENABLE_SCHEDULER'] = '0'

from app import app, db
app.config['TESTING'] = True
app.config['SERVER_NAME'] = 'localhost'
app.config['WTF_CSRF_ENABLED'] = False
app.config['SECRET_KEY'] = 'test-accept-reset'

EMAIL = 'victor.krivenko.4949@gmail.com'

with app.test_client() as client:
    with app.app_context():
        from models import User
        from models_curator import CuratorState
        from daily_tasks.models import DailyTaskSet, DailyTaskItem
        from services.anchors import pick_anchors, CANONICAL_SECTIONS_ORDER
        from services.level_engine import get_state

        # ─── Login ──────────────────────────────────────────────
        user = User.query.filter_by(email=EMAIL).first()
        assert user, "User NOT FOUND"
        user_id = user.id
        grade = getattr(user, 'preferred_grade', None) or getattr(user, 'class_level', None)

        # Login via test client
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
            sess['_fresh'] = True

        # ═══════════════════════════════════════
        # 1) DB DUMP
        # ═══════════════════════════════════════
        print("=" * 60)
        print("1) DB DUMP for user_id=%s email=%s" % (user_id, EMAIL))
        print("=" * 60)

        cs = CuratorState.query.filter_by(user_id=user_id).first()
        print("onboarding_done = %s" % (cs.onboarding_done if cs else 'NOT FOUND'))
        print("prep_state keys = %s" % (list(cs.prep_state.keys()) if cs and cs.prep_state else '{}'))

        state = get_state(user_id)
        print("level_engine: mu=%.4f sigma=%.4f level=%d" % (state['mu'], state['sigma'], state['level']))
        print("level_engine by_section = %s" % json.dumps(state['by_section'], ensure_ascii=False))
        print("level_mu (DB) = %s" % (cs.level_mu if cs else 'N/A'))
        print("level_sigma (DB) = %s" % (cs.level_sigma if cs else 'N/A'))
        print("level_by_section (DB) = %s" % (cs.level_by_section if cs else 'N/A'))

        # Anchor answers count
        from models import AdaptiveTestResult
        atr_all = AdaptiveTestResult.query.filter_by(user_id=user_id).all()
        print("AdaptiveTestResult count = %d" % len(atr_all))

        # Daily tasks
        sets = DailyTaskSet.query.filter_by(user_id=user_id).all()
        item_count = sum(
            DailyTaskItem.query.filter_by(daily_set_id=s.id).count()
            for s in sets
        )
        print("daily_task_sets = %d, daily_task_items = %d" % (len(sets), item_count))

        # Cycle day
        prep_state = cs.prep_state if cs and cs.prep_state else {}
        monthly = prep_state.get('monthly_cycle', {}) if isinstance(prep_state, dict) else {}
        print("monthly_cycle day = %s" % monthly.get('day', 'N/A'))

        # ═══════════════════════════════════════
        # 2) /prep/onboarding — STATUS and LEN
        # ═══════════════════════════════════════
        print("\n" + "=" * 60)
        print("2) GET /prep/onboarding")
        print("=" * 60)
        resp = client.get('/prep/onboarding')
        print("STATUS = %d" % resp.status_code)
        html = resp.data.decode('utf-8')
        print("LEN = %d bytes" % len(html))

        # ═══════════════════════════════════════
        # 3) First anchor task from pick_anchors
        # ═══════════════════════════════════════
        print("\n" + "=" * 60)
        print("3) First anchor task (pick_anchors)")
        print("=" * 60)
        print("User grade = %s" % grade)

        if grade:
            anchors, meta = pick_anchors(grade)
            if anchors:
                first = anchors[0]
                print("anchor_uid = %s" % first['anchor_uid'])
                print("section    = %s" % first['section'])
                print("level      = %s" % first['level'])
                print("grade      = %s" % first['grade'])
            else:
                print("NO ANCHORS FOUND for grade %s" % grade)
                print("meta: %s" % json.dumps(meta, ensure_ascii=False))
        else:
            print("No grade set! Cannot pick anchors.")

        # ═══════════════════════════════════════
        # 4) /daily_tasks — STATUS and blocking
        # ═══════════════════════════════════════
        print("\n" + "=" * 60)
        print("4) GET /daily_tasks/")
        print("=" * 60)
        resp2 = client.get('/daily_tasks/', follow_redirects=True)
        print("STATUS = %d" % resp2.status_code)
        html2 = resp2.data.decode('utf-8')
        print("LEN = %d bytes" % len(html2))
        html2_lower = html2.lower()

        blocking_keywords = [
            ('заблокирован', 'tasks blocked message'),
            ('пройди анкету', 'onboarding required message'),
            ('сначала пройдите', 'onboarding required message'),
            ('сначала пройди', 'onboarding required message'),
            ('prep/onboarding', 'onboarding redirect'),
        ]
        found = False
        for kw, desc in blocking_keywords:
            if kw in html2_lower:
                print("TEXT: '%s' found — %s" % (kw, desc))
                found = True
                break
        
        if not found:
            # Check for task content
            if 'задач' in html2_lower:
                idx = html2_lower.find('задач')
                snippet = html2[max(0, idx-80):idx+200]
                print("TEXT snippet: %s" % snippet[:300])
            else:
                print("TEXT: no blocking or task keywords found.")
                print("HTML preview (first 500 chars):")
                print(html2[:500])

        # ═══════════════════════════════════════
        # Summary
        # ═══════════════════════════════════════
        print("\n" + "=" * 60)
        print("EXPECTED vs ACTUAL")
        print("=" * 60)

        checks = []
        checks.append(("onboarding_done=False (or 0)", cs.onboarding_done == False if cs else False))
        checks.append(("AdaptiveTestResult count=0", len(atr_all) == 0))
        checks.append(("mu=3.0", abs(state['mu'] - 3.0) < 0.01))
        checks.append(("sigma=1.5", abs(state['sigma'] - 1.5) < 0.01))
        checks.append(("by_section empty", len(state['by_section']) == 0))
        checks.append(("daily_task_sets=0", len(sets) == 0))
        checks.append(("daily_task_items=0", item_count == 0))
        checks.append(("onboarding page STATUS=200", resp.status_code == 200))

        if grade and anchors:
            expected_uid = "A_G%d_ALG" % grade
            checks.append(("first anchor UID=%s section=algebra" % expected_uid,
                          first['anchor_uid'] == expected_uid and first['section'] == 'algebra'))
        checks.append(("/daily_tasks STATUS 200", resp2.status_code == 200))

        for desc, ok in checks:
            print("[%s] %s" % ("PASS" if ok else "FAIL", desc))
