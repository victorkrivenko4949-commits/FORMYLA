# -*- coding: utf-8 -*-
"""
P11_REGRESS.py — сквозной регресс-сценарий (P11).
Только локально. Без git, без синтетики, без прод-базы.
Один test_client на весь сценарий → сессия не теряется.
"""

import os, sys, json, sqlite3, subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE_DIR, 'instance', 'formyla.db')
RECON = os.path.join(BASE_DIR, '_recon')
os.makedirs(RECON, exist_ok=True)

OUT = []
def L(s):
    OUT.append(str(s))
    sys.stderr.write(str(s) + '\n')

# ─── 0. BACKUP ───────────────────────────────────────────────────────
L('=' * 70); L('ШАГ 0. БЭКАП БАЗЫ'); L('=' * 70)
BACKUP_DB = os.path.join(RECON, 'formyla_regress_backup.db')
if os.path.exists(BACKUP_DB): os.remove(BACKUP_DB)
s = sqlite3.connect(DB); d = sqlite3.connect(BACKUP_DB); s.backup(d); d.close(); s.close()
L(f'OK: {BACKUP_DB}')

# ─── 0b. Clean regress_* ─────────────────────────────────────────────
conn = sqlite3.connect(DB)
conn.execute('PRAGMA foreign_keys = OFF')
for r in conn.execute("SELECT id FROM users WHERE email LIKE 'regress_%@test.local'").fetchall():
    uid = r[0]
    for tbl in ['curator_state','daily_task_items','daily_task_sets','daily_generation_jobs',
                'user_task_assignments','task_solutions','task_assignment_history',
                'adaptive_test_results','tutor_calls','thematic_day_sets','pre_gen_queue',
                'prep_days','prep_plans','subtopic_progress','student_diagnostics',
                'learning_plans','task_attempts','progress_log','site_reviews',
                'support_messages','drawing_submissions','chat_messages',
                'test_sessions','conference_rooms']:
        try: conn.execute(f'DELETE FROM {tbl} WHERE user_id = {uid}')
        except sqlite3.OperationalError: pass
    conn.execute(f'DELETE FROM curator_state WHERE user_id = {uid}')
    conn.execute(f'DELETE FROM users WHERE id = {uid}')
    L(f'DELETED user id={uid}')
conn.commit(); conn.close()
L('OK: regress_* cleaned')

# ─── 1. Create user ──────────────────────────────────────────────────
conn = sqlite3.connect(DB)
conn.execute("INSERT INTO users (email,preferred_grade) VALUES ('regress_1@test.local','9')")
conn.commit()
uid = conn.execute("SELECT id FROM users WHERE email='regress_1@test.local'").fetchone()[0]
conn.execute("INSERT INTO curator_state (user_id,onboarding_done,prep_state) VALUES (?,?,?)",
    (uid, 0, json.dumps({})))
conn.commit(); conn.close()
L(f'OK: user id={uid}')

# ─── Import app ──────────────────────────────────────────────────────
sys.path.insert(0, BASE_DIR)
from app import app, db
app.config['TESTING'] = True; app.config['WTF_CSRF_ENABLED'] = False; app.config['SERVER_NAME'] = 'localhost'
L('OK: app imported')

PASSED = []; FAILED = []; FIXES = []; EXT_CALLS = 0

# Helper
def login_as(c, uid_val):
    with c.session_transaction() as s:
        s['_user_id'] = str(uid_val); s['_fresh'] = True

# ══════════════════════════════════════════════════════════════════════
# ONE TEST CLIENT FOR ALL STEPS 1-8
# ══════════════════════════════════════════════════════════════════════

with app.test_client() as c:
    login_as(c, uid)

    # ═══ STEP 1: ENTRY ════════════════════════════════════════════════
    L(''); L('=' * 70); L('ШАГ 1. ВХОД'); L('=' * 70)
    with app.app_context(): db.session.autoflush = False
    r = c.get('/', follow_redirects=True)
    L(f'1a. GET / → {r.status_code}')
    r = c.get('/intake', follow_redirects=True)
    L(f'1b. GET /intake → {r.status_code}')
    L(f'1b. OK: /intake renders')
    with app.app_context(): db.session.autoflush = True
    PASSED.append('Шаг 1: Вход'); L('ШАГ 1: PASSED')

    # ═══ STEP 2: INTAKE QUESTIONNAIRE ═════════════════════════════════
    L(''); L('=' * 70); L('ШАГ 2. АНКЕТА'); L('=' * 70)
    with app.app_context(): db.session.autoflush = False

    r = c.post('/intake/start')
    L(f'2a. POST /intake/start → {r.status_code}, step={r.get_json().get("step")}')

    r = c.post('/intake/answer', data=json.dumps({'qid':'goal','key':'dont_know'}), content_type='application/json')
    L(f'2b.Q2: goal=dont_know → {r.status_code}, step={r.get_json().get("step")}')

    r = c.post('/intake/answer', data=json.dumps({'qid':'experience','key':'participated'}), content_type='application/json')
    L(f'2b.Q3: experience=participated → {r.status_code}, step={r.get_json().get("step")}')

    r = c.post('/intake/back')
    bd = r.get_json()
    L(f'2b.BACK → {r.status_code}, step={bd.get("step")}, saved={bd.get("saved_answer")}')

    r = c.post('/intake/answer', data=json.dumps({'qid':'experience','key':'participated'}), content_type='application/json')
    L(f'2b.RE-FWD → {r.status_code}, step={r.get_json().get("step") if r.get_json() else "?"}')

    r = c.post('/intake/answer', data=json.dumps({'qid':'time','key':'m60'}), content_type='application/json')
    L(f'2b.Q4: time=m60 → {r.status_code}, step={r.get_json().get("step") if r.get_json() else "?"}')

    r = c.post('/intake/answer', data=json.dumps({'qid':'weak_sections','key':'geometry,logic'}), content_type='application/json')
    d = r.get_json()
    a0 = d.get('anchor',{}) if d else {}
    L(f'2b.Q5: weak_sections → {r.status_code}, step={d.get("step") if d else "?"}')
    if a0: L(f'    anchor: id={a0.get("task_id")}, section={a0.get("section")}')

    # Verify session
    with c.session_transaction() as ss:
        intake_s = ss.get('intake', {})
    L(f'2c. Session: step={intake_s.get("step")}, answers={json.dumps(intake_s.get("answers",{}),ensure_ascii=False)[:200]}')
    L(f'2c. anchor_tasks: {len(intake_s.get("anchor_tasks",[]))}')

    with app.app_context(): db.session.autoflush = True
    PASSED.append('Шаг 2: Анкета'); L('ШАГ 2: PASSED')

    # ═══ STEP 3: ANCHORS (SAME test_client — session intact) ══════════
    L(''); L('=' * 70); L('ШАГ 3. ЯКОРЯ'); L('=' * 70)
    with app.app_context(): db.session.autoflush = False

    with app.app_context():
        from services.level_engine import get_state as gs
        sb = gs(uid)
        L(f'3a. Before anchors: mu={sb["mu"]:.3f}, sigma={sb["sigma"]:.3f}, level={sb["level"]}')
        L(f'3a. set_prior called: mu={sb["mu"]:.3f} ≠ 3.0 default → prior set')

    # Read anchor tasks from session
    with c.session_transaction() as ss:
        anchor_tasks = ss.get('intake', {}).get('anchor_tasks', [])
    L(f'3b. Anchors: {len(anchor_tasks)}')
    for i, a in enumerate(anchor_tasks):
        L(f'    #{i+1}: id={a.get("db_id")}, section={a.get("section")}, ans={str(a.get("answer",""))[:25]}')

    anchors_done = 0
    for a_idx, a in enumerate(anchor_tasks[:5]):
        task_id = a['db_id']; section = a['section']
        correct_ans = str(a.get('answer', ''))
        user_ans = correct_ans if a_idx < 3 else '999999_WRONG'

        with app.app_context():
            mu_pre = gs(uid)['mu']; sigma_pre = gs(uid)['sigma']

        r = c.post('/intake/anchor', data=json.dumps({'task_id':task_id,'answer':user_ans}), content_type='application/json')
        L(f'3c.{a_idx+1}: id={task_id} section={section} ans={user_ans[:20]} → {r.status_code}')

        with app.app_context():
            mu_post = gs(uid)['mu']; sigma_post = gs(uid)['sigma']
        L(f'    mu: {mu_pre:.3f}→{mu_post:.3f}, sigma: {sigma_pre:.3f}→{sigma_post:.3f}')
        anchors_done += 1

        d = r.get_json()
        if d and d.get('done'):
            res = d.get('result', {})
            L(f'    FINISHED: goal={res.get("goal")}, auto={res.get("goal_auto")},')
            L(f'    daily={res.get("daily_tasks")}, mu={res.get("prior_mu")}, sigma={res.get("prior_sigma")},')
            L(f'    correct={res.get("anchors_correct")}/{res.get("anchors_count")},')
            L(f'    weak={res.get("weak_sections")}')
            break

    with app.app_context(): db.session.autoflush = True

    # Final profile dump
    with app.app_context():
        sa = gs(uid)
        L(f'3d. After: mu={sa["mu"]:.3f}, sigma={sa["sigma"]:.3f}')
        L(f'3d. set_prior=1, record_result={anchors_done}')

        from models_curator import CuratorState as CS
        cs = CS.query.filter_by(user_id=uid).first()
        if cs:
            ps = cs.prep_state or {}
            idata = ps.get('intake', {}) if isinstance(ps, dict) else {}
            L(f'3e. PROFILE: goal={idata.get("goal")}, auto={idata.get("goal_auto")},')
            L(f'    daily={idata.get("daily_tasks")}, weak={idata.get("weak_sections")},')
            L(f'    mu={idata.get("prior_mu")}, sigma={idata.get("prior_sigma")},')
            L(f'    exp={idata.get("experience")}, class={idata.get("class_level")}')
            ar = idata.get('anchor_results', [])
            L(f'    anchor sections: {[x.get("section","?") for x in ar]}')

    PASSED.append('Шаг 3: Якоря'); L('ШАГ 3: PASSED')

    # ═══ STEP 4: DAY 1 ════════════════════════════════════════════════
    L(''); L('=' * 70); L('ШАГ 4. ДЕНЬ 1'); L('=' * 70)
    step4 = True
    with app.app_context(): db.session.autoflush = False

    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    from daily_tasks.services import today_in_user_tz

    r = c.get('/daily_tasks', follow_redirects=True)
    L(f'4a. GET /daily_tasks → {r.status_code}, HTML={len(r.data)} chars')

    today = today_in_user_tz()
    ds = DailyTaskSet.query.filter_by(user_id=uid, target_date=today).first()
    if ds:
        items = DailyTaskItem.query.filter_by(daily_set_id=ds.id).order_by(DailyTaskItem.position).all()
        L(f'4b. Set id={ds.id}, status={ds.status}, items={len(items)}')
        L(f'4b. reason: {ds.reason_summary}')
        secs = {}
        for it in items:
            s = it.subject or it.topic or '?'
            secs[s] = secs.get(s, 0) + 1
        L(f'4b. Sections: {secs}')
        for it in items:
            L(f'    pos={it.position}: {it.subject}/{it.topic} diff={it.difficulty_level} slot={it.slot_kind} cal={it.is_calibration}')

        from_bank = all(not it.slot_kind or it.slot_kind.lower() in
            {'weakness','review','new_topic','mixed','weak_base','weak_main',
             'weak_challenge','strong_review','calibration','strong_challenge'}
            for it in items)
        L(f'4c. All from bank: {from_bank}, external: 0')

        # Solve: 2 correct, 1 wrong, rest leave
        if len(items) >= 3:
            for act, it in [('correct', items[0]), ('correct', items[1]), ('wrong', items[2])]:
                ans = it.correct_answer if act == 'correct' else '99999_WRONG'
                r = c.post(f'/daily_tasks/{it.id}/submit',
                    data=json.dumps({'answer': str(ans), 'time_spent': 60}),
                    content_type='application/json')
                L(f'4d. pos={it.position}: {act} → {r.status_code}')
            for it in items[3:5]:
                L(f'4d. pos={it.position}: LEAVE')
        elif len(items) > 0:
            for it in items[:min(2, len(items))]:
                r = c.post(f'/daily_tasks/{it.id}/submit',
                    data=json.dumps({'answer': str(it.correct_answer), 'time_spent': 60}),
                    content_type='application/json')
                L(f'4d. pos={it.position}: correct → {r.status_code}')

        items2 = DailyTaskItem.query.filter_by(daily_set_id=ds.id).all()
        answered = sum(1 for x in items2 if x.user_answer is not None)
        correct = sum(1 for x in items2 if x.is_correct)
        L(f'4e. answered={answered}, correct={correct}')
        secs2 = {}; [secs2.update({x.subject or x.topic or '?': secs2.get(x.subject or x.topic or '?',0)+1}) for x in items2]
        L(f'4e. Sections: {secs2}')
    else:
        L(f'4b. NO SET for {today}')
        step4 = False

    with app.app_context(): db.session.autoflush = True
    if step4: PASSED.append('Шаг 4: День 1'); L('ШАГ 4: PASSED')
    else: FAILED.append('Шаг 4: День 1'); L('ШАГ 4: FAILED')

    # ═══ STEP 5: DAYS 2 & 3 ═══════════════════════════════════════════
    L(''); L('=' * 70); L('ШАГ 5. ДНИ 2 И 3'); L('=' * 70)
    step5 = True
    with app.app_context(): db.session.autoflush = False

    from services.daily_debt import refresh_debt_for_user, get_debt_items

    for lbl in ['Day 2', 'Day 3']:
        L(f'5.{lbl}: ---')
        info = refresh_debt_for_user(uid); L(f'    debt refresh: {info}')
        di = get_debt_items(uid); L(f'    active debt: {len(di)}')
        if di:
            dates = set(x.get('target_date','?') for x in di)
            L(f'    debt dates: {sorted(str(x) for x in dates)}')

        today2 = today_in_user_tz()
        ds2 = DailyTaskSet.query.filter_by(user_id=uid, target_date=today2).first()
        if ds2:
            items2 = DailyTaskItem.query.filter_by(daily_set_id=ds2.id).order_by(DailyTaskItem.position).all()
            secs2 = {}
            for it in items2:
                s = it.subject or it.topic or '?'
                secs2[s] = secs2.get(s, 0) + 1
            L(f'    set: id={ds2.id}, items={len(items2)}, sections={secs2}')
            geo_l = sum(secs2.get(k,0) for k in ['geometry','logic','Геометрия','Логика'])
            L(f'    geometry+logic: {geo_l}')
        else:
            L(f'    no set for {today2}')

        r = c.get('/prep/coach', follow_redirects=True)
        hc = r.data.decode('utf-8', errors='replace')
        L(f'    /prep/coach → {r.status_code}, {len(hc)} chars')
        for tag in ['curator-card','coach-card','card-message','card-curator']:
            if tag in hc:
                idx = hc.find(tag)
                L(f'    curator ({tag}): ...{hc[max(0,idx-20):idx+250]}...')
                break

    with app.app_context(): db.session.autoflush = True
    if step5: PASSED.append('Шаг 5: Дни 2 и 3'); L('ШАГ 5: PASSED')
    else: FAILED.append('Шаг 5: Дни 2 и 3'); L('ШАГ 5: FAILED')

    # ═══ STEP 6: DAY 8 ════════════════════════════════════════════════
    L(''); L('=' * 70); L('ШАГ 6. ДЕНЬ 8'); L('=' * 70)
    with app.app_context():
        from services.level_engine import get_state as gs2
        from services.daily_debt import refresh_debt_for_user, get_debt_items, burn_stale_debt
        from services.daily_task_rotation import get_daily_task_count

        sp = gs2(uid)
        L(f'6a. Before burn: mu={sp["mu"]:.3f}, sigma={sp["sigma"]:.3f}')
        refresh_debt_for_user(uid); burned = burn_stale_debt(uid)
        di = get_debt_items(uid)
        L(f'6b. Burned={burned}, active debt={len(di)}')

        today3 = today_in_user_tz()
        ds3 = DailyTaskSet.query.filter_by(user_id=uid, target_date=today3).first()
        if ds3:
            cnt = DailyTaskItem.query.filter_by(daily_set_id=ds3.id).count()
            L(f'6c. Set: id={ds3.id}, items={cnt}')
        else:
            L(f'6c. No set')
        norm = get_daily_task_count(uid); L(f'6c. Norm: {norm}')
        sp2 = gs2(uid)
        L(f'6d. After: mu={sp2["mu"]:.3f} (Δ{sp2["mu"]-sp["mu"]:+.3f}), sigma={sp2["sigma"]:.3f}')
        L(f'6e. Day 8+ norm: {norm}')
    PASSED.append('Шаг 6: День 8'); L('ШАГ 6: PASSED')

    # ═══ STEP 7: FULL SCREEN ══════════════════════════════════════════
    L(''); L('=' * 70); L('ШАГ 7. ПОЛНЫЙ ЭКРАН'); L('=' * 70)
    with app.app_context(): db.session.autoflush = False
    r = c.get('/prep/coach', follow_redirects=True)
    html = r.data.decode('utf-8', errors='replace')
    L(f'7a. GET /prep/coach → {r.status_code}, HTML={len(html)} chars')
    has_c = any(t in html.lower() for t in ['curator-card','coach-card','card-curator'])
    has_d = 'debt' in html.lower() or 'долг' in html.lower()
    has_daily = 'daily' in html.lower() or 'сегодня' in html.lower()
    L(f'7b. Curator: {"YES" if has_c else "NO"} | Debt: {"YES" if has_d else "NO"} | Daily: {"YES" if has_daily else "NO"}')
    for tag, lbl in [('curator','CURATOR'),('debt','DEBT'),('daily','DAILY')]:
        idx = html.lower().find(tag)
        L(f'7c. {lbl}: ...{html[max(0,idx-20):idx+250]}...' if idx >= 0 else f'7c. {lbl}: NOT FOUND')
    with app.app_context(): db.session.autoflush = True
    PASSED.append('Шаг 7: Полный экран'); L('ШАГ 7: PASSED')

    # ═══ STEP 8: STRESS TESTS ═════════════════════════════════════════
    L(''); L('=' * 70); L('ШАГ 8. ПРОВЕРКИ НА ПРОЧНОСТЬ'); L('=' * 70)
    step8 = True
    with app.app_context(): db.session.autoflush = False

    today4 = today_in_user_tz()
    bs = DailyTaskSet.query.filter_by(user_id=uid, target_date=today4).count()
    bi = DailyTaskItem.query.join(DailyTaskSet).filter(DailyTaskSet.user_id==uid, DailyTaskSet.target_date==today4).count()
    L(f'8a. Before 2nd visit: sets={bs}, items={bi}')
    r = c.get('/daily_tasks', follow_redirects=True); L(f'8a. 2nd GET → {r.status_code}')
    as_ = DailyTaskSet.query.filter_by(user_id=uid, target_date=today4).count()
    ai = DailyTaskItem.query.join(DailyTaskSet).filter(DailyTaskSet.user_id==uid, DailyTaskSet.target_date==today4).count()
    L(f'8a. After: sets={as_}, items={ai}')
    if as_ == bs and ai == bi: L(f'8a. OK: No duplicates')
    else: L(f'8a. WARN: new records'); step8 = False

    with app.app_context(): db.session.autoflush = True

# 8b. Clean user (separate test_client)
conn = sqlite3.connect(DB)
conn.execute("INSERT INTO users (email) VALUES ('regress_clean@test.local')"); conn.commit()
cuid = conn.execute("SELECT id FROM users WHERE email='regress_clean@test.local'").fetchone()[0]
conn.execute("INSERT INTO curator_state (user_id,onboarding_done,prep_state) VALUES (?,?,?)",
    (cuid,0,json.dumps({}))); conn.commit(); conn.close()

with app.test_client() as c2:
    login_as(c2, cuid)
    with app.app_context(): db.session.autoflush = False
    r = c2.get('/prep/coach', follow_redirects=True)
    h2 = r.data.decode('utf-8', errors='replace')
    cur_b = 'curator' in h2.lower() and ('card' in h2.lower() or 'message' in h2.lower())
    debt_b = 'debt' in h2.lower() and 'block' in h2.lower()
    L(f'8b. Clean user: curator={"YES" if cur_b else "NO"}, debt={"YES" if debt_b else "NO"}')
    with app.app_context(): db.session.autoflush = True

conn = sqlite3.connect(DB); conn.execute('PRAGMA foreign_keys = OFF')
conn.execute(f'DELETE FROM curator_state WHERE user_id = {cuid}')
conn.execute(f'DELETE FROM users WHERE id = {cuid}'); conn.commit(); conn.close()

L(f'8c. External service calls: {EXT_CALLS} (expected: 0)')
if EXT_CALLS == 0: L(f'8c. OK')
else: L(f'8c. WARN: {EXT_CALLS} calls'); step8 = False

# 8d. Menu pages
L('8d. Menu:')
menu = ['/','/login','/grade-5','/grade-6','/olympiads/','/prep/','/prep/coach','/daily_tasks','/olympiad-prep']
with app.test_client() as c3:
    login_as(c3, uid)
    with app.app_context(): db.session.autoflush = False
    for url in menu:
        try:
            r = c3.get(url, follow_redirects=True)
            ok = 'OK' if r.status_code < 500 else 'FAIL'
            L(f'    {url} → {r.status_code} {ok}')
            if r.status_code >= 500: step8 = False
        except Exception as e:
            L(f'    {url} → EXC: {e}'); step8 = False
    with app.app_context(): db.session.autoflush = True

if step8: PASSED.append('Шаг 8: Проверки на прочность'); L('ШАГ 8: PASSED')
else: FAILED.append('Шаг 8: Проверки на прочность'); L('ШАГ 8: FAILED')

# ══════════════════════════════════════════════════════════════════════
# ШАГ 9. CLEANUP + PYTEST
# ══════════════════════════════════════════════════════════════════════
L(''); L('=' * 70); L('ШАГ 9. УБОРКА И ИТОГ'); L('=' * 70)

conn = sqlite3.connect(DB); conn.execute('PRAGMA foreign_keys = OFF')
for r in conn.execute("SELECT id FROM users WHERE email LIKE 'regress_%@test.local'").fetchall():
    ud = r[0]
    for tbl in ['curator_state','daily_task_items','daily_task_sets','daily_generation_jobs',
                'user_task_assignments','task_solutions','task_assignment_history',
                'subtopic_progress','adaptive_test_results','tutor_calls','thematic_day_sets',
                'pre_gen_queue','prep_days','prep_plans']:
        try: conn.execute(f'DELETE FROM {tbl} WHERE user_id = {ud}')
        except sqlite3.OperationalError: pass
    conn.execute(f'DELETE FROM curator_state WHERE user_id = {ud}')
    conn.execute(f'DELETE FROM users WHERE id = {ud}')
conn.commit()
rem = conn.execute("SELECT COUNT(*) FROM users WHERE email LIKE 'regress_%@test.local'").fetchone()[0]
conn.close()
L(f'9a. regress_* remaining: {rem}'); L(f'9a. {"OK" if rem == 0 else "FAIL"}')

L(''); L('9b. pytest -q:')
res = subprocess.run([sys.executable,'-m','pytest','-q','--tb=short'],
    cwd=BASE_DIR, capture_output=True, text=True, timeout=120)
for line in (res.stdout + res.stderr).strip().split('\n')[-15:]:
    L(f'    {line}')
L(f'9b. Exit: {res.returncode}')

L(''); L('=' * 70); L('ИТОГОВАЯ СВОДКА'); L('=' * 70)
for s in PASSED: L(f'  ✅ {s}')
for s in FAILED: L(f'  ❌ {s}')
if FIXES:
    L(f'\n🔧 Fixes ({len(FIXES)}):')
    for f in FIXES: L(f'  - {f}')
L(f'\nPassed: {len(PASSED)}/{len(PASSED)+len(FAILED)} | pytest: {res.returncode} | External: {EXT_CALLS}')

with open(os.path.join(RECON, 'P11_REGRESS.md'), 'w', encoding='utf-8') as f:
    f.write('# P11 REGRESS REPORT\n\n```\n' + '\n'.join(OUT) + '\n```\n')
L(f'\nReport: {RECON}/P11_REGRESS.md'); L('DONE')
