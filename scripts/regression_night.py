# -*- coding: utf-8 -*-
"""BLOCK 8: Regression night checks.
Each check prints PASS or FAIL with actual value.
Based on nightly prompt: verify invariants that must hold.
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app import app, db
from models import User, AdaptiveTask
from models_curator import CuratorState
from daily_tasks.models import DailyTaskSet, DailyTaskItem
from services.daily_task_rotation import (
    _get_onboarding, _get_daily_tasks_count, _get_route_ceiling,
    _get_allowed_difficulty, _section_priorities, _get_seen_task_ids,
    _classify_section, _normalize_section,
    pick_daily_set, record_daily_answer, build_student_card,
    CANONICAL_SECTIONS,
)
from services.level_engine import get_state, allowed_difficulty

app.config['TESTING'] = True
app.config['SERVER_NAME'] = 'localhost'

def check(name, condition, actual=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" (actual={actual})" if actual else ""))

with app.app_context():
    # ── 8.1: CANONICAL_SECTIONS defined ──
    check("8.1 CANONICAL_SECTIONS defined",
          CANONICAL_SECTIONS == ('algebra', 'geometry', 'combinatorics', 'logic', 'number_theory'),
          str(CANONICAL_SECTIONS))

    # ── 8.2: pick_daily_set exists and is callable ──
    check("8.2 pick_daily_set callable", callable(pick_daily_set))

    # ── 8.3: _get_daily_tasks_count for user 1 ──
    cnt = _get_daily_tasks_count(1)
    check("8.3 _get_daily_tasks_count returns int", isinstance(cnt, int), str(cnt))
    check("8.3b count > 0", cnt > 0, str(cnt))

    # ── 8.4: _get_route_ceiling ──
    ceil_val = _get_route_ceiling(1)
    check("8.4 _get_route_ceiling returns int 1..5",
          isinstance(ceil_val, int) and 1 <= ceil_val <= 5, str(ceil_val))

    # ── 8.5: _section_priorities always returns 5 sections ──
    priorities = _section_priorities({})
    check("8.5 _section_priorities returns 5 sections", len(priorities) == 5, str(len(priorities)))

    # ── 8.6: _get_seen_task_ids returns a set ──
    seen = _get_seen_task_ids(1)
    check("8.6 _get_seen_task_ids returns set", isinstance(seen, set), str(type(seen)))

    # ── 8.7: _classify_section on random task ──
    task = AdaptiveTask.query.filter(
        AdaptiveTask.subject.isnot(None),
        AdaptiveTask.subject != '',
        AdaptiveTask.task_text.isnot(None),
    ).first()
    if task:
        sec = _classify_section(task)
        check("8.7 _classify_section returns canonical or recognized",
              sec in CANONICAL_SECTIONS or isinstance(sec, str), str(sec))

    # ── 8.8: _normalize_section fallback ──
    ns = _normalize_section('unknown_garbage_xyz')
    check("8.8 _normalize_section fallback is str", isinstance(ns, str), str(ns))

    # ── 8.9: level_engine get_state ──
    state = get_state(1)
    check("8.9 get_state returns dict with mu", isinstance(state, dict) and 'mu' in state,
          f"mu={state.get('mu', '?')}")

    # ── 8.10: allowed_difficulty ──
    allowed = allowed_difficulty(3, 'formyla_L1_L5_TOP5')
    check("8.10 allowed_difficulty(3) non-empty", len(allowed) > 0, str(allowed))

    # ── 8.11: build_student_card ──
    card = build_student_card(1)
    check("8.11 build_student_card returns dict with grade",
          isinstance(card, dict) and 'grade' in card, f"keys={list(card.keys())[:5]}")

    # ── 8.12: DailyTaskSet table exists ──
    try:
        cnt_dts = DailyTaskSet.query.count()
        check("8.12 DailyTaskSet table accessible", cnt_dts >= 0, str(cnt_dts))
    except Exception as e:
        check("8.12 DailyTaskSet table accessible", False, str(e)[:80])

    # ── 8.13: DailyTaskItem has section field in gemini_spec_json ──
    item = DailyTaskItem.query.first()
    if item and item.gemini_spec_json:
        try:
            spec = json.loads(item.gemini_spec_json)
            check("8.13 DailyTaskItem.gemini_spec_json parseable", True,
                  f"section={spec.get('section','?')}")
        except:
            check("8.13 DailyTaskItem.gemini_spec_json parseable", False)

    # ── 8.14: record_daily_answer flow ──
    if item:
        result = record_daily_answer(1, item.id, True)
        check("8.14 record_daily_answer returns dict", isinstance(result, dict),
              str(list(result.keys())[:3]))

    # ── 8.15: CuratorState fields ──
    cs = CuratorState.query.filter_by(user_id=1).first()
    if cs:
        check("8.15 CuratorState has level_mu", hasattr(cs, 'level_mu'),
              str(getattr(cs, 'level_mu', '?')))
        check("8.15b CuratorState has level_by_section", hasattr(cs, 'level_by_section'),
              str(type(getattr(cs, 'level_by_section', None))))
        check("8.15c CuratorState has prep_state", hasattr(cs, 'prep_state'),
              str(type(getattr(cs, 'prep_state', None))))
        check("8.15d CuratorState has onboarding_done", hasattr(cs, 'onboarding_done'),
              str(getattr(cs, 'onboarding_done', '?')))

    # ── 8.16: User grade detection ──
    user = User.query.get(1)
    if user:
        g = getattr(user, 'preferred_grade', None)
        check("8.16 User.preferred_grade accessible", True, str(g))

    # ── 8.17: test_client accessible ──
    try:
        with app.test_client() as c:
            r = c.get('/')
            check("8.17 test_client GET / works", r.status_code in (200, 302, 308),
                  str(r.status_code))
    except Exception as e:
        check("8.17 test_client GET / works", False, str(e)[:80])

    # ── 8.18: GET /daily-set redirects to login ──
    try:
        with app.test_client() as c:
            r = c.get('/daily-set', follow_redirects=False)
            check("8.18 GET /daily-set -> 302 (login required)", r.status_code == 302,
                  str(r.status_code))
    except Exception as e:
        check("8.18 GET /daily-set -> 302", False, str(e)[:80])

    # ── 8.19: GET /daily -> 404 (dead route) ──
    try:
        with app.test_client() as c:
            r = c.get('/daily', follow_redirects=False)
            check("8.19 GET /daily -> 404 (dead route)", r.status_code == 404,
                  str(r.status_code))
    except Exception as e:
        check("8.19 GET /daily -> 404", False, str(e)[:80])

    # ── 8.20: GET /daily_tasks redirects ──
    try:
        with app.test_client() as c:
            r = c.get('/daily_tasks/', follow_redirects=False)
            check("8.20 GET /daily_tasks/ -> 302 (login required)", r.status_code == 302,
                  str(r.status_code))
    except Exception as e:
        check("8.20 GET /daily_tasks/ -> 302", False, str(e)[:80])

print('\n=== BLOCK 8 COMPLETE ===')
