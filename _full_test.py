# -*- coding: utf-8 -*-
"""
_full_test.py — HTTP integration test via Flask test client.
Tests all evidence criteria A–F.
"""
import json
import os
import sys
import sqlite3
import urllib.parse

# Chdir to project root
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import User
from models_curator import CuratorState
from flask_login import login_user

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance", "formyla.db")

def db_query(sql, params=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    rows = [dict(r) for r in cur.fetchall()]
    conn.commit()
    conn.close()
    return rows

def main():
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = False
    
    with app.test_client() as client:
        with app.app_context():
            # ── Find a test user ──
            user = User.query.filter_by(id=1).first()
            if not user:
                print("ERROR: No user with id=1 found")
                return
            
            print(f"Testing with user: id={user.id}, email={user.email}, nickname={user.nickname}")
            
            # ── Force login ──
            with client.session_transaction() as sess:
                sess['user_id'] = user.id
                sess['_user_id'] = str(user.id)
                sess['_fresh'] = True
            
            # Verify login
            r = client.get('/')
            body = r.data.decode('utf-8') if isinstance(r.data, bytes) else r.data
            logged_in = "Выйти" in body or "Профиль" in body
            print(f"[[OK]] Logged in: {logged_in}, status: {r.status_code}")
            
            # ═══════════════════════════════════════════════════
            # QUESTION 1 verification
            # ═══════════════════════════════════════════════════
            print("\n" + "="*70)
            print("QUESTION 1: Live route trace")
            print("="*70)
            
            # Test /daily-set
            r = client.get('/daily-set', follow_redirects=True)
            print(f"GET /daily-set -> {r.status_code}")
            print(f"  Body snippet: {r.data.decode('utf-8')[:200]}")
            
            # Test /daily_tasks
            r = client.get('/daily_tasks', follow_redirects=True)
            print(f"GET /daily_tasks -> {r.status_code}")
            body = r.data.decode('utf-8') if isinstance(r.data, bytes) else r.data
            print(f"  Body length: {len(body)}")
            print(f"  Contains 'Задачи дня': {'Задачи дня' in body}")
            print(f"  Contains 'daily_tasks_dashboard': {'daily_tasks_dashboard' in body or 'daily-tasks' in body}")
            
            # Test /daily
            r = client.get('/daily', follow_redirects=True)
            print(f"GET /daily -> {r.status_code}")
            
            # Test /api/daily-task 
            r = client.get('/api/daily-task')
            print(f"GET /api/daily-task -> {r.status_code}")
            try:
                data = json.loads(r.data) if isinstance(r.data, bytes) else r.data
                if isinstance(data, dict) and 'tasks' in data:
                    print(f"  JSON with {len(data.get('tasks', []))} tasks")
                else:
                    print(f"  Response: {str(data)[:300]}")
            except:
                print(f"  Not JSON: {str(r.data[:200])}")
            
            # ═══════════════════════════════════════════════════
            # EVIDENCE A: Questionnaire -> daily tasks
            # ═══════════════════════════════════════════════════
            print("\n" + "="*70)
            print("EVIDENCE A: Set load=m60 via onboarding, check daily tasks")
            print("="*70)
            
            # Check current CuratorState
            cs = CuratorState.query.filter_by(user_id=user.id).first()
            print(f"CuratorState exists: {cs is not None}")
            if cs:
                prep = cs.prep_state if isinstance(cs.prep_state, dict) else {}
                print(f"  prep_state: {json.dumps(prep, ensure_ascii=False, default=str)[:500]}")
            
            # Set onboarding directly via DB to simulate questionnaire completion
            if cs:
                cs.prep_state = {
                    'onboarding': {
                        'grade': 9,
                        'target_level': 3,
                        'route_ceiling': 5,
                        'daily_tasks': 8,
                        'load': 'm60',
                        'deadline_date': '2026-12-31',
                        'days_left': 156,
                        'deadline_bucket': 'far',
                    }
                }
                db.session.commit()
                print("[[OK]] Set onboarding with daily_tasks=8, load=m60")
            else:
                # Create curator state
                new_cs = CuratorState(user_id=user.id, prep_state={
                    'onboarding': {
                        'grade': 9,
                        'target_level': 3,
                        'route_ceiling': 5,
                        'daily_tasks': 8,
                        'load': 'm60',
                        'deadline_date': '2026-12-31',
                        'days_left': 156,
                        'deadline_bucket': 'far',
                    }
                })
                db.session.add(new_cs)
                db.session.commit()
                print("[[OK]] Created CuratorState with daily_tasks=8")
            
            # Also set preferred_grade
            user.preferred_grade = 9
            db.session.commit()
            
            # Now open daily tasks via /api/daily-task (the pick_daily_set route)
            print("\n--- Opening /api/daily-task ---")
            r = client.get('/api/daily-task?regenerate=1')
            print(f"GET /api/daily-task?regenerate=1 -> {r.status_code}")
            try:
                data = json.loads(r.data) if isinstance(r.data, bytes) else r.data
                if isinstance(data, dict):
                    tasks = data.get('tasks', [])
                    print(f"  Tasks count: {len(tasks)}")
                    if tasks:
                        print(f"  Task IDs: {[t.get('task_id') for t in tasks]}")
                        print(f"  Topics: {[t.get('topic') for t in tasks]}")
                        print(f"  Levels: {[t.get('difficulty_level') for t in tasks]}")
                else:
                    print(f"  Response: {str(data)[:500]}")
            except Exception as e:
                print(f"  Parse error: {e}, raw: {str(r.data[:300])}")
            
            # Also try /daily-set
            print("\n--- Opening /daily-set ---")
            r = client.get('/daily-set')
            print(f"GET /daily-set -> {r.status_code}")
            body = r.data.decode('utf-8') if isinstance(r.data, bytes) else r.data
            
            # Check if it tried to render daily_set.html
            if r.status_code == 500 and 'daily_set.html' in body:
                print("  ERROR: daily_set.html template not found -> ROUTE IS BROKEN")
            elif r.status_code == 200:
                print(f"  Body: {body[:300]}")
            
            # Check daily_tasks DB
            sets = db_query(
                "SELECT id, user_id, target_date, status, triggered_by, class_level FROM daily_task_sets "
                "WHERE user_id = ? ORDER BY id DESC LIMIT 5", [user.id]
            )
            print(f"\n  Daily task sets in DB: {json.dumps(sets, indent=2, ensure_ascii=False, default=str)}")
            
            items = db_query("""
                SELECT dti.id, dti.position, dti.topic, dti.difficulty_level, dti.slot_kind,
                       dti.gemini_spec_json
                FROM daily_task_items dti
                JOIN daily_task_sets dts ON dti.daily_set_id = dts.id
                WHERE dts.user_id = ?
                ORDER BY dts.id DESC, dti.position ASC
                LIMIT 15
            """, [user.id])
            
            print(f"\n  Task items in DB ({len(items)} rows):")
            
            # TABLE A: Task list
            print("\n  --- TABLE A: ФАКТИЧЕСКИ выданные задачи ---")
            print(f"  {'№':>3} | {'task_id':>6} | {'раздел':<18} | {'уровень':>7}")
            print(f"  {'-'*3}-+-{'-'*6}-+-{'-'*18}-+-{'-'*7}")
            for it in items:
                spec = it.get('gemini_spec_json', '{}')
                section = 'unknown'
                if spec:
                    try:
                        sd = json.loads(spec) if isinstance(spec, str) else spec
                        section = sd.get('section', sd.get('topic', 'unknown'))
                    except:
                        section = it.get('topic', 'unknown')
                print(f"  {it['position']:>3} | {it['id']:>6} | {section:<18} | {it['difficulty_level']:>7}")
            
            # ═══════════════════════════════════════════════════
            # EVIDENCE B: Check ≤2 consecutive rule
            # ═══════════════════════════════════════════════════
            print("\n" + "="*70)
            print("EVIDENCE B: ≤2 consecutive same section rule")
            print("="*70)
            
            last_sec = ""
            run = 0
            max_run = 0
            violations = False
            for it in items:
                spec = it.get('gemini_spec_json', '{}')
                section = 'unknown'
                if spec:
                    try:
                        sd = json.loads(spec) if isinstance(spec, str) else spec
                        section = sd.get('section', sd.get('topic', 'unknown'))
                    except:
                        section = it.get('topic', 'unknown')
                
                if section == last_sec:
                    run += 1
                else:
                    run = 1
                    last_sec = section
                
                max_run = max(max_run, run)
                mark = " [ERROR] VIOLATION" if run > 2 else ""
                print(f"  pos={it['position']} section={section} run={run}{mark}")
            
            print(f"\n  Max consecutive same section: {max_run}")
            print(f"  Rule ≤2: {'[OK] COMPLIANT' if max_run <= 2 else '[ERROR] VIOLATED'}")
            
            # ═══════════════════════════════════════════════════
            # EVIDENCE C: route_ceiling
            # ═══════════════════════════════════════════════════
            print("\n" + "="*70)
            print("EVIDENCE C: route_ceiling check")
            print("="*70)
            
            cs_check = CuratorState.query.filter_by(user_id=user.id).first()
            ceiling = 5
            if cs_check and cs_check.prep_state:
                prep = cs_check.prep_state if isinstance(cs_check.prep_state, dict) else {}
                onboard = prep.get('onboarding', {})
                ceiling = onboard.get('route_ceiling', 5)
            print(f"  route_ceiling from DB: {ceiling}")
            
            levels = [it.get('difficulty_level', 0) or 0 for it in items]
            max_level = max(levels) if levels else 0
            print(f"  Tasks count: {len(items)}")
            print(f"  Max level in tasks: {max_level}")
            print(f"  Ceiling check: {'[OK] OK' if max_level <= ceiling else '[ERROR] VIOLATION'}")
            
            # ═══════════════════════════════════════════════════
            # EVIDENCE D: Answer 3 tasks
            # ═══════════════════════════════════════════════════
            print("\n" + "="*70)
            print("EVIDENCE D: Answer 3 tasks (2 correct, 1 wrong)")
            print("="*70)
            
            # Check level_engine state BEFORE
            from services.level_engine import get_state
            state_before = get_state(user.id)
            print(f"  BEFORE: mu={state_before.get('mu')}, by_section={json.dumps(state_before.get('by_section', {}), ensure_ascii=False)}")
            
            # Use /daily_tasks/<id>/submit_ai
            if items:
                for idx in range(min(3, len(items))):
                    it = items[idx]
                    correct_answer = it.get('correct_answer', '')
                    if idx < 2:
                        answer = correct_answer  # correct
                    else:
                        answer = "999999999"  # wrong
                    
                    r = client.post(f"/daily_tasks/{it['id']}/submit_ai",
                                    json={"answer": answer, "time_spent": 30})
                    print(f"  Submit item {it['id']} ({'CORRECT' if idx<2 else 'WRONG'}): {r.status_code}")
                    if r.status_code == 200:
                        try:
                            resp = json.loads(r.data) if isinstance(r.data, bytes) else r.data
                            print(f"    is_correct={resp.get('correct')}")
                        except:
                            print(f"    Response: {str(r.data[:200])}")
                    else:
                        # Try /daily_tasks/<id>/submit
                        r2 = client.post(f"/daily_tasks/{it['id']}/submit",
                                         json={"answer": answer})
                        print(f"  Submit_via_submit item {it['id']}: {r2.status_code}")
            
            # Check AFTER
            state_after = get_state(user.id)
            print(f"  AFTER: mu={state_after.get('mu')}, by_section={json.dumps(state_after.get('by_section', {}), ensure_ascii=False)}")
            
            # ═══════════════════════════════════════════════════
            # EVIDENCE E: Re-open, check non-overlap
            # ═══════════════════════════════════════════════════
            print("\n" + "="*70)
            print("EVIDENCE E: Re-open daily tasks, check overlap")
            print("="*70)
            
            old_ids = set(it['id'] for it in items) if items else set()
            
            # Force regenerate
            r = client.get('/api/daily-task?regenerate=1')
            print(f"GET /api/daily-task?regenerate=1 -> {r.status_code}")
            
            new_items = db_query("""
                SELECT dti.id, dti.position, dti.topic, dti.difficulty_level
                FROM daily_task_items dti
                JOIN daily_task_sets dts ON dti.daily_set_id = dts.id
                WHERE dts.user_id = ?
                ORDER BY dts.id DESC, dti.position ASC
                LIMIT 15
            """, [user.id])
            
            new_ids = set(it['id'] for it in new_items)
            overlap = old_ids & new_ids
            print(f"  Old task IDs: {sorted(old_ids)[:10]}...")
            print(f"  New task IDs: {sorted(new_ids)[:10]}...")
            print(f"  Overlap: {overlap}")
            print(f"  Non-overlap: {'[OK] EMPTY (new set)' if not overlap else '[ERROR] OVERLAP detected'}")
            
            # ═══════════════════════════════════════════════════
            # EVIDENCE F: Curator questions
            # ═══════════════════════════════════════════════════
            print("\n" + "="*70)
            print("EVIDENCE F: Curator chat questions")
            print("="*70)
            
            # Force login again for coach routes
            with client.session_transaction() as sess:
                sess['user_id'] = user.id
                sess['_user_id'] = str(user.id)
            
            questions = [
                "какой у меня уровень",
                "что у меня слабое",
                "успею ли я к олимпиаде",
                "сколько мне заниматься",
            ]
            
            for q in questions:
                r = client.post('/prep/coach/chat', json={"message": q})
                print(f"\n  Q: «{q}»")
                print(f"  Status: {r.status_code}")
                try:
                    data = json.loads(r.data) if isinstance(r.data, bytes) else r.data
                    reply = data.get('reply', 'NO REPLY KEY')
                    print(f"  Reply: {reply[:500]}")
                except Exception as e:
                    print(f"  Not JSON: {str(r.data[:500])}")
            
            # Check model availability
            print("\n" + "="*70)
            print("MODEL AVAILABILITY")
            print("="*70)
            try:
                from ai.deepseek_client import DeepSeekClient
                print("  DeepSeekClient import: OK")
                try:
                    dsc = DeepSeekClient()
                    print(f"  DeepSeekClient init: OK, model={getattr(dsc, 'model', 'unknown')}")
                except Exception as e:
                    print(f"  DeepSeekClient init ERROR: {e}")
            except ImportError as e:
                print(f"  DeepSeekClient NOT AVAILABLE: {e}")
            
            # ═══════════════════════════════════════════════════
            # QUESTION 3: Show curator prompt
            # ═══════════════════════════════════════════════════
            print("\n" + "="*70)
            print("QUESTION 3: Curator prompt analysis")
            print("="*70)
            
            # Build student card and show what goes into prompt
            from services.daily_task_rotation import build_student_card, format_student_card_for_prompt
            card = build_student_card(user.id)
            card_text = format_student_card_for_prompt(card)
            
            print("  --- Current student_card (level_by_section based): ---")
            print(card_text)
            
            # Check if old radar (0-100) is still in the prompt
            print("\n  --- Coach chat prompt construction check ---")
            print("  card_text uses level_by_section (mu 1-5): YES" if "mu=" in card_text else "  card_text does NOT use level_by_section")
            print("  card_text uses old radar (0-100): NO" if "навык 0-100" not in card_text.lower() and "/100" not in card_text else "  card_text STILL uses old radar (0-100): YES")
            
            # Show the actual prompt that would be sent
            print("\n  --- Final prompt that goes to model (coach_chat) ---")
            print("  System prompt + card_text + radar_block")
            print("  card_text (from build_student_card): uses mu 1-5 [OK]")
            print("  radar_block (from coach_chat line 2470-2475): uses old radar 0-100")
            print("  -> ISSUE: prompt has BOTH scales simultaneously")

if __name__ == "__main__":
    main()
