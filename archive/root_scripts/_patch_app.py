#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Patch app.py in-place with all olympiad-test wiring changes."""
import sys, os

APPPATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.py')

with open(APPPATH, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find key line numbers
import_start = None
route_start = None

for i, ln in enumerate(lines):
    if ln.startswith('from services.level_engine import'):
        import_start = i
    if ln.startswith('@app.route("/olympiad-test/start"'):
        route_start = i

print(f"import_start={import_start}, route_start={route_start}")

# ── 1. Add import if not present ────────────────────────────────
if import_start is None:
    # Find the import line after 'from simple_prefetch'
    for i, ln in enumerate(lines):
        if 'from simple_prefetch import' in ln:
            lines.insert(i + 2, 'from services.level_engine import record_result, get_state\n')
            print(f"Added level_engine import after line {i+1}")
            break

# Reload
content = ''.join(lines)

# ── 2. Find the olympiad_test_run function ───────────────────────
marker = '@app.route("/olympiad-test/start", methods=[\'GET\', \'POST\'])\ndef olympiad_test_run():\n'
idx = content.find(marker)
if idx == -1:
    print("ERROR: Cannot find olympiad_test_run route")
    sys.exit(1)

# Find the end of this function (before next \n\n@app or next def)
# We'll use a simpler approach: find the closing of this function
# by looking for the next function/route marker after our start

# Find position in the original lines
for i, ln in enumerate(lines):
    if ln.startswith('@app.route("/olympiad-test/start"'):
        route_start = i
        break

if route_start is None:
    print("ERROR: Cannot find route start in lines")
    sys.exit(1)

lines_before_route = content[:content.find(marker)]
# Find function end: next line that starts with @app.route( or def that's not indented
# after the function body begins

# Let me find the end by looking for "\n\n@app" or "\n\n#" after the route
# The current end should be before " NOTE: /practice/generate route removed"

rest = content[content.find(marker):]
# Find the closing of the function by looking for the note that follows
note_marker = '\n\n# NOTE: /practice/generate route removed'
note_idx = rest.find(note_marker)
if note_idx == -1:
    print("ERROR: Cannot find function end marker")
    sys.exit(1)

func_body = rest[:note_idx]
remaining = rest[note_idx:]

print(f"Function body length: {len(func_body)}")

# Now we need to replace the entire function. Let's build the new version.
# But first, let's check if it's already patched.
if 'olyad_task_queue' in func_body:
    print("Already patched!")
else:
    print("Needs patching - replacing function body")

# Instead, let's write the whole patched file with string substitution.
# Read the file fresh.
with open(APPPATH, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the old function body
old_func_start = content.find("""@app.route("/olympiad-test/start", methods=['GET', 'POST'])
def olympiad_test_run():
    \"\"\"Main test page: fixed-level, 5 tasks, no adaptive difficulty change.\"\"\"""")
if old_func_start == -1:
    print("ERROR: Could not find old function signature")
    sys.exit(1)

# Find end (next non-indented line after the function)
end_marker = "\n\n# NOTE: /practice/generate route removed together with the"
end_idx = content.find(end_marker, old_func_start)
if end_idx == -1:
    print("ERROR: Could not find function end")
    sys.exit(1)

old_func = content[old_func_start:end_idx]
print(f"Old function length: {len(old_func)} chars")

new_func = '''@app.route("/olympiad-test/start", methods=['GET', 'POST'])
def olympiad_test_run():
    """Main test page: configurable length/level/scope from session."""
    from services.olympiad_adaptive import (
        get_task, get_task_by_section,
        _normalize_answer, _check_solution_quality,
        pick_all_sections_tasks, _all_tasks,
    )
    import random, logging
    _ol_log = logging.getLogger(__name__)

    scope = session.get('olyad_scope', None)
    total_len = int(session.get('olyad_length', 5))
    level_hint = int(session.get('olyad_level_hint', 2))

    # ── GET: show task ───────────────────────────────────────────
    if request.method == 'GET':
        # Fresh start?
        if 'olyad_uid' not in session or request.args.get('grade'):
            try:
                grade = int(request.args.get('grade', ''))
            except (ValueError, TypeError):
                return redirect('/olympiad-test')
            if grade not in range(5, 12):
                return redirect('/olympiad-test')

            if scope == 'all_sections':
                try:
                    from services.level_engine import get_state
                    st = get_state(current_user.id) if current_user.is_authenticated else {}
                except Exception:
                    st = {}
                by_sec = st.get('by_section', {}) if st else {}
                picked = pick_all_sections_tasks(grade, total_len, by_sec, level_hint)
                queue = picked.get('tasks', [])
                session['olyad_task_queue'] = queue
                session['olyad_queue_pos'] = 0
                session['olyad_uid'] = '1'
                session['olyad_grade'] = grade
                session['olyad_theme'] = 'all_sections'
                session['olyad_level'] = level_hint
                session['olyad_task_num'] = 0
                session['olyad_shown'] = []
                session['olyad_results'] = []
                session['olyad_total'] = len(queue)
                if not queue:
                    flash('Нет задач для выбранного класса', 'error')
                    return redirect('/olympiad-test')
            else:
                theme = request.args.get('theme', '').strip()
                level = int(request.args.get('level', str(level_hint)))
                if not theme or level not in range(1, 6):
                    return redirect('/olympiad-test')
                session['olyad_uid'] = '1'
                session['olyad_grade'] = grade
                session['olyad_theme'] = theme
                session['olyad_level'] = level
                session['olyad_task_num'] = 0
                session['olyad_shown'] = []
                session['olyad_results'] = []
                session['olyad_task_queue'] = []
                session['olyad_total'] = total_len

        grade = session['olyad_grade']
        theme = session['olyad_theme']
        level = session['olyad_level']

        if scope == 'all_sections':
            queue = session.get('olyad_task_queue', [])
            pos = session.get('olyad_queue_pos', 0)
            if pos >= len(queue):
                task = None
            else:
                task = queue[pos]
                session['olyad_current_task'] = task['task_uid']
                session['olyad_level'] = task.get('level', level_hint)
                session['olyad_current_section'] = (task.get('section') or '').strip()
                shown = set(session.get('olyad_shown', []))
                shown.add(task['task_uid'])
                session['olyad_shown'] = list(shown)
                session['olyad_queue_pos'] = pos + 1
                session.modified = True
        else:
            shown = set(session.get('olyad_shown', []))
            task = get_task(grade, theme, level, shown)
            if task:
                session['olyad_shown'] = list(shown) + [task['task_uid']]
                session['olyad_current_task'] = task['task_uid']
                session['olyad_current_section'] = (task.get('section') or '').strip()
                session.modified = True

        if not task:
            flash('Задачи закончились', 'error')
            return redirect('/olympiad-test')

        tnum = session.get('olyad_task_num', 0) + 1
        display_level = task.get('level', level)
        display_theme = task.get('theme', '') if scope == 'all_sections' else theme
        return render_template('olympiad_test_run.html',
                               task=task, grade=grade, theme=display_theme,
                               level=display_level, task_count=tnum, feedback=None, result=None,
                               total=session.get('olyad_total', total_len))

    # ── POST: process answer ─────────────────────────────────────
    user_answer = (request.form.get('answer') or '').strip()
    user_solution = (request.form.get('solution') or '').strip()
    task_uid = session.get('olyad_current_task', '')

    # Find the task
    import json
    task_data = None
    with open('FORMYLA_L1_L5_TOP5.jsonl', encoding='utf-8') as f:
        for line in f:
            if line.strip() and json.loads(line).get('task_uid') == task_uid:
                task_data = json.loads(line)
                break
    # Fallback: search in memory
    if not task_data:
        for t in _all_tasks:
            if t.get('task_uid') == task_uid:
                task_data = t
                break

    if not task_data:
        flash('Ошибка: задача не найдена', 'error')
        return redirect('/olympiad-test')

    correct = (task_data.get('answer') or '').strip()
    ref_sol = (task_data.get('solution') or '').strip()
    statement = (task_data.get('statement') or '').strip()
    level = task_data.get('level', session.get('olyad_level', level_hint))

    is_correct = _normalize_answer(user_answer) == _normalize_answer(correct)

    # Simple scoring: correct=+1, wrong=-1
    ball = 1 if is_correct else -1

    # ── Step 4: Call level_engine.record_result ───────────────────
    task_section = session.get('olyad_current_section', (task_data.get('section') or '').strip())
    if current_user.is_authenticated and task_section:
        try:
            record_result(
                current_user.id,
                task_section,
                int(level),
                is_correct,
            )
        except Exception as _le_err:
            _ol_log.warning(
                "record_result failed user=%s section=%s level=%s err=%s",
                current_user.id, task_section, level, _le_err
            )

    results = session.get('olyad_results', [])
    results.append({
        'level': level,
        'ball': ball,
        'task_uid': task_uid,
        'user_answer': user_answer,
        'correct_answer': correct,
        'solution': ref_sol,
        'statement': statement,
        'is_correct': is_correct,
    })
    session['olyad_results'] = results
    session['olyad_task_num'] = len(results)
    session.modified = True

    task_num = len(results)
    grade = session['olyad_grade']
    theme = session['olyad_theme']

    # Results if total_len tasks done
    result = None
    if task_num >= total_len:
        correct_count = sum(1 for r in results if r['is_correct'])
        partial_count = sum(1 for r in results if not r['is_correct'] and r.get('ball', 0) == 0)
        wrong_count = task_num - correct_count - partial_count

        # ── Step 5: Update prep_state ─────────────────────────────
        if current_user.is_authenticated:
            try:
                from models_curator import CuratorState
                cs = CuratorState.query.filter_by(user_id=current_user.id).first()
                if cs and isinstance(getattr(cs, 'prep_state', None), dict):
                    from datetime import datetime as _dt
                    now_iso = _dt.utcnow().isoformat()
                    mu_before = None
                    mu_after = None
                    try:
                        st = get_state(current_user.id)
                        mu_after = st.get('mu')
                    except Exception:
                        pass
                    ps = dict(cs.prep_state)
                    if ps.get('test_queue'):
                        ps['test_queue'] = ps['test_queue'][1:]
                    ps['last_test'] = {
                        'date': now_iso,
                        'total': task_num,
                        'correct': correct_count,
                        'mu_before': mu_before,
                        'mu_after': mu_after,
                        'level_before': round(mu_before) if mu_before else None,
                        'level_after': round(mu_after) if mu_after else None,
                    }
                    cs.prep_state = ps
                    from models import db
                    db.session.commit()
            except Exception as _ps_err:
                _ol_log.warning("prep_state update failed: %s", _ps_err)

        result = {
            'results': results,
            'correct_count': correct_count,
            'partial_count': partial_count,
            'wrong_count': wrong_count,
            'grade': grade,
            'theme': theme,
            'level': level,
        }

    # Get next task for display
    if result:
        task = None
    elif scope == 'all_sections':
        queue = session.get('olyad_task_queue', [])
        pos = session.get('olyad_queue_pos', 0)
        if pos < len(queue):
            task = queue[pos]
            session['olyad_current_task'] = task['task_uid']
            session['olyad_level'] = task.get('level', level_hint)
            session['olyad_current_section'] = (task.get('section') or '').strip()
            shown = set(session.get('olyad_shown', []))
            shown.add(task['task_uid'])
            session['olyad_shown'] = list(shown)
            session['olyad_queue_pos'] = pos + 1
            session.modified = True
        else:
            task = None
    else:
        shown = set(session.get('olyad_shown', []))
        task = get_task(grade, theme, level, shown)

    feedback = {
        'is_correct': is_correct,
        'ball': ball,
        'correct_answer': correct,
        'solution': ref_sol,
    }

    display_level = task.get('level', level) if task else level
    display_theme = (task.get('theme', '') if task and scope == 'all_sections' else theme)
    return render_template('olympiad_test_run.html',
                           task=task, grade=grade, theme=display_theme,
                           level=display_level, task_count=task_num,
                           feedback=feedback, result=result,
                           total=session.get('olyad_total', total_len))
'''

# Apply the replacement
new_content = content[:old_func_start] + new_func + content[end_idx:]

with open(APPPATH, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Patch applied successfully!")
print("Verifying:")
verify = open(APPPATH, 'r', encoding='utf-8').read()
print("  level_engine:", verify.count('level_engine'))
print("  record_result:", verify.count('record_result'))
print("  olyad_task_queue:", verify.count('olyad_task_queue'))
print("  total_len:", verify.count('total_len'))
print("  prep_state:", verify.count('prep_state'))
print("  last_test:", verify.count('last_test'))
