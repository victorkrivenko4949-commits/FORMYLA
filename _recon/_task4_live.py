# -*- coding: utf-8 -*-
"""Task 4: Live acceptance via app.test_client() with redirects."""
import os, sys, json, re, time, logging
from datetime import date, datetime, timedelta, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.environ['FLASK_DEBUG'] = '0'
logging.basicConfig(level=logging.CRITICAL)
for n in list(logging.root.manager.loggerDict.keys()):
    logging.getLogger(n).setLevel(logging.CRITICAL)

MSK = timezone(timedelta(hours=3))
L = lambda s: print(s, flush=True)
DB = os.path.join(BASE, 'instance', 'formyla.db')

import sqlite3

def raw_exec(sql, *params):
    c = sqlite3.connect(DB); c.execute('PRAGMA foreign_keys=OFF')
    c.execute(sql, params); c.commit(); c.close()

def raw_fetch(sql, *params):
    c = sqlite3.connect(DB); r = c.execute(sql, params).fetchall(); c.close(); return r

def raw_fetch_one(sql, *params):
    c = sqlite3.connect(DB); r = c.execute(sql, params).fetchone(); c.close(); return r

# Clean old test users
def clean(pattern):
    c = sqlite3.connect(DB); c.execute('PRAGMA foreign_keys=OFF')
    rows = c.execute("SELECT id FROM users WHERE email LIKE ?", (pattern,)).fetchall()
    for (uid,) in rows:
        c.execute('DELETE FROM curator_state WHERE user_id=?', (uid,))
        for t in ['daily_task_sets','daily_task_items','daily_generation_jobs',
                  'task_assignment_history','user_task_assignments','task_solutions']:
            try: c.execute(f'DELETE FROM {t} WHERE user_id=?', (uid,))
            except: pass
        c.execute('DELETE FROM users WHERE id=?', (uid,))
    c.commit(); c.close()
    return len(rows)

L('='*70)
L('TASK 4: LIVE ACCEPTANCE via app.test_client()')
L('='*70)

clean('p7live_%@test.local')

from app import app, db
from flask_login import login_user

external_calls = {'openrouter': 0, 'deepseek': 0, 'other': 0}

# Monkey-patch to count external calls
import services.openrouter_client as orc_mod
_orig_chat = getattr(orc_mod.OpenRouterClient, 'chat_json', None)
if _orig_chat:
    async def _counting_chat(*args, **kwargs):
        external_calls['openrouter'] += 1
        return await _orig_chat(*args, **kwargs)
    orc_mod.OpenRouterClient.chat_json = _counting_chat

with app.app_context():
    from models import User
    from models_curator import CuratorState
    from daily_tasks.models import DailyTaskSet, DailyTaskItem

    # === 1) New grade 9 student, first visit ===
    L('')
    L('--- 1) NEW 9th GRADE STUDENT, FIRST VISIT ---')

    u9 = User(email='p7live_g9@test.local', name='P7Live G9', nickname='p7live_g9', preferred_grade=9)
    db.session.add(u9); db.session.flush()
    uid9 = u9.id

    prep = {'onboarding': {'completed': True, 'daily_tasks': 5, 'grade': 9,
                           'route_ceiling': 5, 'target_level': 3},
            'monthly_cycle': {'started_at': '2026-07-01T00:00:00+00:00',
                              'themes': [f'G9_T{k:02d}' for k in range(1,8)],
                              'day_index': 5, 'done_themes': [], 'finished_at': None}}
    try:
        cs9 = CuratorState(user_id=uid9, grade=9, onboarding_done=1,
                          prep_state=json.dumps(prep),
                          level_mu=3.0, level_sigma=1.5,
                          level_by_section=json.dumps(
                              {s:{'mu':2.0,'sigma':1.0,'n':5} for s in ['algebra','geometry','combinatorics','logic','number_theory']}))
        db.session.add(cs9)
    except:
        pass
    db.session.commit()

    with app.test_client() as c:
        with c.session_transaction() as s:
            s['_user_id'] = str(uid9)
            s['_fresh'] = True

        today = datetime.now(MSK).date()
        resp = c.get('/daily_tasks', follow_redirects=True)
        final_status = resp.status_code
        html = resp.data.decode('utf-8', errors='replace')

        # Count task cards
        task_cards = len(re.findall(r'daily-task-item|task-card|dt-item-card', html, re.IGNORECASE))
        if task_cards == 0:
            task_cards = len(re.findall(r'class="[^"]*card[^"]*"', html))

        # Check source
        sources = []
        for m in re.finditer(r'slot_kind[=:]\s*["\'](\w+)["\']|source[=:]\s*["\'](\w+)["\']', html):
            sources.append(m.group(1) or m.group(2))

        L(f'  FINAL STATUS: {final_status}')
        L(f'  Task cards in HTML: {task_cards}')
        L(f'  Sources found: {sources or ["NONE — empty state"]}')

        # HTML fragment
        for marker in ['task-list', 'taskList', 'daily-tasks', 'dt-empty', 'items']:
            pos = html.find(marker)
            if pos >= 0:
                fragment = html[max(0,pos-60):pos+500]
                L(f'  HTML fragment ({marker}):')
                L(f'    {fragment[:400]}')
                break

    # === 2) Repeat visit same day ===
    L('')
    L('--- 2) REPEAT VISIT SAME DAY ---')

    first_set_count = DailyTaskSet.query.filter_by(user_id=uid9, target_date=today).count()
    first_items_count = DailyTaskItem.query.filter(
        DailyTaskItem.daily_set_id.in_(
            db.session.query(DailyTaskSet.id).filter_by(user_id=uid9, target_date=today)
        )
    ).count()

    with app.test_client() as c2:
        with c2.session_transaction() as s:
            s['_user_id'] = str(uid9)
            s['_fresh'] = True
        resp2 = c2.get('/daily_tasks', follow_redirects=True)
        html2 = resp2.data.decode('utf-8', errors='replace')
        tc2 = len(re.findall(r'daily-task-item|task-card|dt-item-card', html2, re.IGNORECASE))

    second_set_count = DailyTaskSet.query.filter_by(user_id=uid9, target_date=today).count()
    second_items_count = DailyTaskItem.query.filter(
        DailyTaskItem.daily_set_id.in_(
            db.session.query(DailyTaskSet.id).filter_by(user_id=uid9, target_date=today)
        )
    ).count()

    L(f'  First visit: sets={first_set_count}, items={first_items_count}')
    L(f'  Second visit: sets={second_set_count}, items={second_items_count}')
    L(f'  Same set: {"OK" if second_set_count == first_set_count else "FAIL — new set created!"}')
    L(f'  Same cards: {tc2}')
    L(f'  New DB records: {"NONE" if second_set_count == first_set_count and second_items_count == first_items_count else f"DELTA: sets={second_set_count-first_set_count}, items={second_items_count-first_items_count}"}')

    # === 3) Grade 11, logic section (empty cell) ===
    L('')
    L('--- 3) 11th GRADE, LOGIC SECTION (EMPTY CELL) ---')

    u11 = User(email='p7live_g11@test.local', name='P7Live G11', nickname='p7live_g11', preferred_grade=11)
    db.session.add(u11); db.session.flush()
    uid11 = u11.id

    # Check how many logic tasks exist for G11
    from models import AdaptiveTask
    logic_count = AdaptiveTask.query.filter(
        AdaptiveTask.class_level == 11,
        AdaptiveTask.subject == 'logic',
        AdaptiveTask.correct_answer.isnot(None),
        AdaptiveTask.correct_answer != '',
    ).count()
    L(f'  AdaptiveTask G11 logic tasks: {logic_count}')
    L(f'  Bank coverage for G11: checking JSON files...')

    # Check bank
    from daily_tasks import task_bank as tb
    bank_available = tb.grade_is_available(11)
    if bank_available:
        probes = tb.load_bank(11)
        L(f'  Bank G11 probes: {len(probes)}')
        bank_cells = tb.available_cells(11)
        L(f'  Bank G11 available cells: {len(bank_cells)}')
    else:
        L(f'  Bank G11: NOT AVAILABLE')

    prep11 = {'onboarding': {'completed': True, 'daily_tasks': 5, 'grade': 11,
                            'route_ceiling': 5, 'target_level': 5},
             'monthly_cycle': {'started_at': '2026-07-01T00:00:00+00:00',
                               'themes': ['G11_T01'],
                               'day_index': 5, 'done_themes': [], 'finished_at': None}}
    try:
        cs11 = CuratorState(user_id=uid11, grade=11, onboarding_done=1,
                           prep_state=json.dumps(prep11),
                           level_mu=4.0, level_sigma=1.0,
                           level_by_section=json.dumps(
                               {s:{'mu':4.0,'sigma':1.0,'n':3} for s in ['algebra','geometry','combinatorics','logic','number_theory']}))
        db.session.add(cs11)
    except:
        pass
    db.session.commit()

    # Try pick_daily_set
    from services.daily_task_rotation import pick_daily_set
    try:
        result = pick_daily_set(uid11, force_regenerate=True)
        n = result.get('count', 0)
        tasks = result.get('tasks', [])
        bank_slots = sum(1 for t in tasks if t.get('section') == 'logic')
        gen_slots = n - bank_slots
        L(f'  pick_daily_set G11: {n} tasks total')
        L(f'  Bank slots (logic section): {bank_slots}')
        L(f'  Generation slots (non-logic): {gen_slots}')
    except Exception as e:
        L(f'  pick_daily_set G11 error: {e}')

    # === 4) External calls counter ===
    L('')
    L('--- 4) EXTERNAL CALLS COUNTER ---')
    L(f'  OpenRouter calls: {external_calls["openrouter"]}')
    L(f'  DeepSeek calls: {external_calls["deepseek"]}')
    L(f'  Other external: {external_calls["other"]}')
    L(f'  ZERO external calls: {"OK" if sum(external_calls.values()) == 0 else f"FAIL — {sum(external_calls.values())} calls made!"}')

    # === 5) Dump daily_task_items for G9 student ===
    L('')
    L('--- 5) DUMP daily_task_items FOR G9 STUDENT ---')

    sets = DailyTaskSet.query.filter_by(user_id=uid9, target_date=today).all()
    for s in sets:
        items = DailyTaskItem.query.filter_by(daily_set_id=s.id).order_by(DailyTaskItem.position).all()
        L(f'  DailyTaskSet #{s.id}: {len(items)} items, status={s.status}')
        for it in items:
            # Extract source from gemini_spec_json
            source = 'unknown'
            if it.gemini_spec_json:
                try:
                    spec = json.loads(it.gemini_spec_json)
                    source = spec.get('source', spec.get('slot_kind', 'unknown'))
                except:
                    pass
            L(f'    pos={it.position} id={it.id} task_id=N/A source={source} topic={it.topic} level={it.difficulty_level}')

    if not sets:
        L(f'  NO DailyTaskSet found for user {uid9} on {today}')
        L(f'  (This is expected if pick_daily_set requires additional setup)')

# Cleanup
clean('p7live_%@test.local')

# Restore original chat_json
if _orig_chat:
    orc_mod.OpenRouterClient.chat_json = _orig_chat

L('')
L('DONE')
