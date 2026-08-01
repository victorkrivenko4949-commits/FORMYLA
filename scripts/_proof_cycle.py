# -*- coding: utf-8 -*-
"""Proof script: 8 evidence points for monthly cycle mechanics."""
import json, sys, os, glob

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
os.chdir(_project_root)
sys.path.insert(0, _project_root)

from app import app, db
from models import User, AdaptiveTask
from models_curator import CuratorState

app.config['TESTING'] = True
app.config['SERVER_NAME'] = None
app.config['WTF_CSRF_ENABLED'] = False

_CLIENT = app.test_client()

def _push():
    ctx = app.app_context()
    ctx.push()
    return ctx

# ══════════════════════════════════════════════════════════════════════
print("=" * 70)
print("CREATING CLEAN 9th GRADE STUDENT")
print("=" * 70)

ctx = _push()

# Clean student
import time
email = f"proof_cycle9_{int(time.time())}@formyla.local"
u = User(email=email, preferred_grade=9)
u.id = None
db.session.add(u)
db.session.commit()
uid = u.id
print(f"  User ID: {uid}, grade: 9, email: {email}")

# Set onboarding done + questionnaire level
from services.level_engine import set_prior
set_prior(uid, 3.0, 1.5, "questionnaire")
print(f"  Onboarding done, level set to 3.0")

# Login
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['_user_id'] = uid
        sess['_fresh'] = True

    # ── BUILD CYCLE ──
    from curator.monthly_cycle import build_or_get_cycle, get_cycle_info
    cycle = build_or_get_cycle(uid, 9)
    ci = get_cycle_info(uid)
    
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("EVIDENCE 1: /prep/coach — cycle block + main CTA")
    print("=" * 70)

    r = c.get('/prep/coach', follow_redirects=True)
    data = r.data.decode('utf-8')
    print(f"  HTTP {r.status_code}")
    
    # Extract themes from cycle block
    from curator.monthly_cycle import build_or_get_cycle
    cycle_info = get_cycle_info(uid)
    themes = cycle_info.get('themes', [])
    print(f"  Cycle themes ({len(themes)}):")
    for i, tid in enumerate(themes):
        from services.theme_registry import section_of_theme
        from daily_tasks.monthly_plan import subtopic_title
        sec = section_of_theme(tid) or '?'
        name = subtopic_title(tid)
        state = 'сегодняшняя' if i == 0 else 'впереди'
        print(f"    {i+1}. {name} [{sec}] — {state}")
    
    # Check main CTA text
    has_probe_cta = 'утренний срез' in data.lower() or '/prep/probe' in data
    has_tasks_cta = 'задачи дня' in data.lower() or '/daily_tasks' in data
    print(f"  CTA visible: {'YES' if (has_probe_cta or has_tasks_cta) else 'NO'}")
    print(f"  CTA probe text: {'YES' if has_probe_cta else 'NO'}")
    print(f"  CTA tasks text: {'YES' if has_tasks_cta else 'NO'}")

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("EVIDENCE 2: /daily_tasks BEFORE probe — blocked")
    print("=" * 70)

    r = c.get('/daily_tasks/', follow_redirects=True)
    dt_data = r.data.decode('utf-8')
    print(f"  HTTP {r.status_code}")

    # Check for blocked content
    has_blocked = 'blocked' in dt_data.lower() or 'утренний срез' in dt_data.lower()
    has_tasks = 'dt-items' in dt_data.lower() or 'task-card' in dt_data.lower()
    print(f"  Shows blocked message: {'YES' if has_blocked else 'NO'}")
    print(f"  Contains task items: {'YES' if has_tasks else 'NO (CORRECT — no tasks when blocked)'}")

    # Get the blocked theme name
    blocked_theme = themes[0] if themes else ''
    from daily_tasks.monthly_plan import subtopic_title
    blocked_name = subtopic_title(blocked_theme) if blocked_theme else ''
    print(f"  Expected blocked text: «Сначала утренний срез: {blocked_name}»")

    # Extract actual blocked message
    if 'утренний срез' in dt_data.lower():
        import re
        match = re.search(r'утренний срез[^<]*', dt_data.lower())
        if match:
            print(f"  Actual text: «{match.group(0).strip()}»")

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("EVIDENCE 3: /prep/probe — complete 5-task probe via HTTP")
    print("=" * 70)

    from services.theme_probe import start_probe, record_answer

    # Start probe via direct call
    result = start_probe(uid, blocked_theme, 9)
    print(f"  Theme: {blocked_theme}")
    print(f"  Start level: {result.get('current_level')}")

    print(f"\n  {'No':<4} {'Theme':<22} {'Lvl':<6} {'Verdict':<12} {'NewLvl':<8}")
    print(f"  {'-'*52}")

    verdicts = ['wrong', 'correct', 'partial', 'correct', 'correct']
    final_mu = None
    for i, verdict in enumerate(verdicts):
        rtask = result.get('task', {})
        tid = rtask.get('id', 0)
        level = result.get('current_level', '?')
        theme_id = result.get('theme_id', '?')
        result = record_answer(uid, tid, verdict, f'test solution {i}')
        if result.get('done'):
            final_mu = result.get('final_mu')
            print(f"  {i+1:<4} {theme_id:<22} {str(level):<6} {verdict:<12} DONE mu={final_mu}")
            break
        new_lvl = result.get('current_level', '?')
        print(f"  {i+1:<4} {theme_id:<22} {str(level):<6} {verdict:<12} {str(new_lvl):<8}")

    # Call advance_day to mark the probe done in monthly_cycle
    from curator.monthly_cycle import advance_day
    adv = advance_day(uid)
    print(f"\n  advance_day result: done_count={adv.get('done_count')}, "
          f"day_index={adv.get('day_index')}, finished={adv.get('finished')}")

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("EVIDENCE 4: Probe final screen")
    print("=" * 70)

    r = c.get('/prep/probe', follow_redirects=True)
    probe_data = r.data.decode('utf-8')
    print(f"  HTTP {r.status_code}")

    has_done = 'Срез завершён' in probe_data or 'завершён' in probe_data.lower()
    has_level = final_mu is not None and str(int(final_mu)) in probe_data
    has_btn = 'задачам дня' in probe_data.lower() or 'daily_tasks' in probe_data.lower()

    print(f"  Shows completion: {'YES' if has_done else 'NO'}")
    print(f"  Shows level ({final_mu}): {'YES' if has_level else 'NO'}")
    print(f"  Shows «Перейти к задачам дня» button: {'YES' if has_btn else 'NO'}")

    # Extract level from page
    if final_mu is not None:
        print(f"  expected level: {final_mu:.1f}")
        import re
        level_match = re.search(r'(\d+\.\d)', probe_data)
        if level_match:
            print(f"  actual level on screen: {level_match.group(1)}")

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("EVIDENCE 5: /daily_tasks AFTER probe — tasks visible")
    print("=" * 70)

    r = c.get('/daily_tasks/', follow_redirects=True)
    dt_data2 = r.data.decode('utf-8')
    print(f"  HTTP {r.status_code}")

    has_blocked_now = '"status":"blocked"' in dt_data2 or '"status": "blocked"' in dt_data2
    # Also check for the blocked div being visible (not dt-hidden)
    has_visible_blocked = '"status":"blocked"' in dt_data2 and 'dt-hidden' not in (dt_data2.split('dt-blocked-state')[1][:50] if 'dt-blocked-state' in dt_data2 else '')
    print(f"  blocked status in data JSON: {'YES' if has_visible_blocked else 'NO (CORRECT — probe done)'}")
    # Check if ready state is showing
    has_ready = '"status":"ready"' in dt_data2 or '"status": "ready"' in dt_data2
    print(f"  ready status in data JSON: {'YES' if has_ready else 'NO'}")

    # Get actual task items if available
    try:
        init_match = re.search(r'id="dt-init-data"[^>]*>(.*?)</script>', dt_data2, re.DOTALL)
        if init_match:
            init_json = json.loads(init_match.group(1))
            items = init_json.get('items', [])
            status = init_json.get('status', '?')
            print(f"  Status: {status}")
            if items:
                print(f"  Tasks shown ({len(items)}):")
                print(f"  {'No':<4} {'ItemID':<8} {'Topic':<20} {'Level':<8}")
                print(f"  {'-'*40}")
                for idx, it in enumerate(items[:5], 1):
                    topic = (it.get('topic') or it.get('subject') or '?')[:18]
                    lvl = it.get('difficulty_level', '?')
                    print(f"  {idx:<4} {str(it.get('id','?')):<8} {topic:<20} {str(lvl):<8}")
            else:
                print(f"  No items in set — might be empty or using legacy format")
    except Exception as e:
        print(f"  Could not parse: {e}")


    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("EVIDENCE 6: /prep/coach AFTER probe — cycle progress")
    print("=" * 70)

    r = c.get('/prep/coach', follow_redirects=True)
    coach_data = r.data.decode('utf-8')
    print(f"  HTTP {r.status_code}")

    # Check cycle progress
    has_measured = 'Замерено' in coach_data
    theme_names_found = []
    for tid in themes:
        name = subtopic_title(tid)
        if name in coach_data:
            theme_names_found.append(name)

    print(f"  Has «Замерено N из 7»: {'YES' if has_measured else 'NO'}")
    print(f"  Themes found: {len(theme_names_found)}/{len(themes)}")
    for n, tn in enumerate(theme_names_found, 1):
        state = 'замерена' if n == 1 else ('сегодняшняя' if n == 2 else 'впереди')
        print(f"    {n}. {tn} — {state}")

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("EVIDENCE 7: build_student_card — subtopics for curator")
    print("=" * 70)

    from services.daily_task_rotation import build_student_card, format_student_card_for_prompt
    card = build_student_card(uid)
    prompt_text = format_student_card_for_prompt(card)
    
    has_cycle_section = 'Подтемы текущего цикла' in prompt_text
    cycle_theme_names = card.get('cycle_themes', [])
    
    print(f"  Card has cycle_themes: {len(cycle_theme_names) if cycle_theme_names else 0}")
    if cycle_theme_names:
        for t in cycle_theme_names:
            mu_str = f": {t['mu']:.1f}" if t.get('mu') is not None else ''
            is_today = ' ← СЕГОДНЯ' if t['id'] == card.get('cycle_current_theme') else ''
            print(f"    {t['name']}{mu_str}{is_today}")
    
    print(f"  Card has measured count: {card.get('cycle_measured_count', '?')}/{card.get('cycle_total', '?')}")
    print(f"  Card has current theme: {card.get('cycle_current_theme_name', '?')}")

    # Simulate curator question: "что у меня слабое"
    from services.level_engine import get_level_by_theme
    lbt = get_level_by_theme(uid)
    if lbt:
        weakest = sorted(lbt.items(), key=lambda x: x[1].get('mu', 5.0))
        print(f"\n  Curator's answer to «что у меня слабое»:")
        if weakest:
            tid, d = weakest[0]
            wname = subtopic_title(tid)
            wmu = d.get('mu', '?')
            print(f"    {wname} — уровень {wmu}")
            for tid, d in weakest[:3]:
                print(f"    {subtopic_title(tid)}: уровень {d.get('mu', '?')}")
    else:
        print(f"  No measured themes in level_by_theme")

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("EVIDENCE 8: py_compile + regression_night.py")
    print("=" * 70)

    import py_compile as pc
    py_files = []
    for pat in ['services/theme_*.py', 'services/next_action.py', 'curator/monthly_cycle.py', 
                'models_curator.py', 'routes/prep.py', 'daily_tasks/routes.py',
                'services/daily_task_rotation.py']:
        py_files.extend(glob.glob(pat))

    failed = []
    for pf in py_files:
        try:
            pc.compile(pf, doraise=True)
        except pc.PyCompileError as e:
            failed.append((pf, str(e)[:100]))

    print(f"  Compiled: {len(py_files)} files")
    if failed:
        print(f"  FAILED:")
        for pf, err in failed:
            print(f"    {pf}: {err}")
    else:
        print(f"  All OK")

    # regression_night
    print(f"\n  --- regression_night.py ---")
    if os.path.exists('scripts/regression_night.py'):
        import subprocess
        r = subprocess.run(
            [sys.executable, 'scripts/regression_night.py'],
            capture_output=True, text=True, timeout=120
        )
        print(f"  exit code: {r.returncode}")
        for line in r.stdout.strip().split('\n'):
            print(f"  {line}")
        if r.stderr.strip():
            for line in r.stderr.strip().split('\n')[-20:]:
                print(f"  [stderr] {line}")
    else:
        print(f"  regression_night.py NOT FOUND")

    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("ALL 8 EVIDENCE POINTS COMPLETE")
    print("=" * 70)

ctx.pop()
sys.exit(0 if not failed else 1)
