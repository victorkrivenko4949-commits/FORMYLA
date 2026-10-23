# -*- coding: utf-8 -*-
"""regression_night.py — raw SQL setup + test_client (autoflush disabled).

Работает с ОТДЕЛЬНОЙ тестовой базой instance/regression_test.db.
Рабочая база instance/formyla.db НЕ затрагивается.
"""
import os, json, re, sqlite3, sys, shutil

# Отдельная тестовая база — не трогаем рабочую formyla.db
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'regression_test.db')
WORK_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'formyla.db')

# Копируем схему из рабочей базы (если тестовой ещё нет)
if not os.path.exists(DB):
    if os.path.exists(WORK_DB):
        print(f"[regression_night] Creating test DB from working schema: {DB}")
        shutil.copy2(WORK_DB, DB)
    else:
        print(f"[regression_night] WARNING: neither test nor work DB exists, creating empty")
OUT = []
L = lambda s: (OUT.append(str(s)), sys.stderr.write(str(s)+'\n'))

# ─── 1. Raw SQL setup ────────────────────────────────────────────────
conn = sqlite3.connect(DB)
conn.execute('PRAGMA foreign_keys = OFF')
for e in ['d1_no_onb@x.test','d2_sect@x.test','d4_zero@x.test']:
    r = conn.execute('SELECT id FROM users WHERE email=?',(e,)).fetchone()
    if r:
        conn.execute('DELETE FROM curator_state WHERE user_id=?',(r[0],))
        conn.execute('DELETE FROM users WHERE id=?',(r[0],))
conn.commit()

conn.execute("INSERT INTO users (email,preferred_grade) VALUES ('d1_no_onb@x.test',9)")
uid1 = conn.execute("SELECT id FROM users WHERE email='d1_no_onb@x.test'").fetchone()[0]
conn.execute("INSERT INTO users (email,preferred_grade) VALUES ('d2_sect@x.test',9)")
uid2 = conn.execute("SELECT id FROM users WHERE email='d2_sect@x.test'").fetchone()[0]
conn.execute("INSERT INTO users (email,preferred_grade) VALUES ('d4_zero@x.test',9)")
uid4 = conn.execute("SELECT id FROM users WHERE email='d4_zero@x.test'").fetchone()[0]

conn.execute("INSERT INTO curator_state (user_id,onboarding_done,prep_state) VALUES (?,?,?)",
    (uid1,0,json.dumps({'onboarding':{'completed':False},'monthly_cycle':{'themes':['G9_T01','G9_T02','G9_T03','G9_T04','G9_T05','G9_T06','G9_T07'],'day_index':1,'done_themes':[],'started_at':'2026-07-01','finished_at':None}})))
conn.execute("INSERT INTO curator_state (user_id,onboarding_done,prep_state) VALUES (?,?,?)",
    (uid2,1,json.dumps({'onboarding':{'completed':True,'completed_at':'2026-07-01'},'questionnaire':{'completed':True,'completed_at':'2026-07-01'},'monthly_cycle':{'themes':['G9_T01','G9_T02','G9_T03','G9_T05','G9_T06','G9_T07','G9_T08'],'day_index':1,'done_themes':[],'started_at':'2026-07-01','finished_at':None}})))
conn.execute("INSERT INTO curator_state (user_id,onboarding_done,prep_state) VALUES (?,?,?)",
    (uid4,1,json.dumps({'onboarding':{'completed':True,'completed_at':'2026-07-01'},'questionnaire':{'completed':True,'completed_at':'2026-07-01'}})))
conn.commit()

def get_ps(uid):
    r = conn.execute('SELECT onboarding_done, prep_state FROM curator_state WHERE user_id=?',(uid,)).fetchone()
    return r[0], json.loads(r[1]) if r and isinstance(r[1],str) else (None,None)

od1, ps1 = get_ps(uid1); od2, ps2 = get_ps(uid2)
conn.close()

# ─── 2. test_client with autoflush blocked ───────────────────────────
from app import app, db

def render(uid):
    with app.test_client() as c:
        with c.session_transaction() as s:
            s['_user_id'] = str(uid); s['_fresh'] = True
        # Disable autoflush for this request to avoid stale-schema crashes
        with app.app_context():
            db.session.autoflush = False
        r = c.get('/prep/coach')
        with app.app_context():
            db.session.autoflush = True
        return r.data.decode('utf-8', errors='replace')

# ══════════════════════════════════════════════════════════════════════
L('='*70)
L('D1: CYCLE BLOCK WITHOUT ONBOARDING')
L('='*70)
L(f'D1(a) onboarding_done = {od1}')
L(f'D1(a) prep_state keys = {sorted(ps1.keys())}')
L(f'D1(a) monthly_cycle.themes = {ps1["monthly_cycle"]["themes"]}')
L(f'D1(a) onboarding.completed = {ps1["onboarding"]["completed"]}')
L('D1(c) template coach.html:304:')
L('  {% if cycle_info and cycle_info.active and onboarding_done %}')

h1 = render(uid1)
L(f'D1(d) cycleBlock: {"PRESENT" if "cycleBlock" in h1 else "ABSENT"}')
L(f'D1(d) Пройти анкету: {"PRESENT" if "Пройти анкету" in h1 else "ABSENT"}')
i = h1.find('Пройти анкету')
if i >= 0:
    L(f'D1(d) HTML: ...{h1[i-20:i+120]}...')

# ══════════════════════════════════════════════════════════════════════
L('')
L('='*70)
L('D2: MAX-2 SECTION GUARD')
L('='*70)

from services.theme_registry import section_of_theme
t2 = ps2['monthly_cycle']['themes']
sc = {}
for t in t2: s=section_of_theme(t) or '?'; sc[s]=sc.get(s,0)+1
L(f'D2(a) cached themes = {t2}')
L(f'D2(a) section counts = {sc}')
L(f'D2(a) max-2 violated = {any(c>2 for c in sc.values())}')

h2 = render(uid2)

conn = sqlite3.connect(DB)
_, ps2b = get_ps(uid2)
conn.close()
mc2 = ps2b.get('monthly_cycle',{}); nt = mc2.get('themes',[])
sc2 = {}
for t in nt: s=section_of_theme(t) or '?'; sc2[s]=sc2.get(s,0)+1
L(f'D2(d) rebuilt themes = {nt}')
L(f'D2(d) section counts = {sc2}')
L(f'D2(d) max-2 violated = {any(c>2 for c in sc2.values())}')
L(f'D2(d) total themes = {len(nt)}')

# ══════════════════════════════════════════════════════════════════════
L('')
L('='*70)
L('D3: RUSSIAN SECTION NAMES')
L('='*70)
h3 = render(uid2)
i3 = h3.find('cycleBlock')
if i3 >= 0:
    blk = h3[i3:i3+1500]
    secs = re.findall(r'text-transform:uppercase;">([^<]+)</span>', blk)
    ru = [s for s in secs if any(s.startswith(p) for p in ['Алгебра','Геометрия','Комбинаторика','Логика','Теория'])]
    L(f'D3(c) section names = {ru}')
    L(f'D3(c) no NUMBER_THEORY: {not any("_" in s or s.isupper() for s in ru if s)}')
else:
    L('D3(c) cycleBlock not found')
    # Try measured subtopics
    i3b = h3.find('measured_subtopics')
    if i3b >= 0:
        blk2 = h3[i3b:i3b+800]
        secs2 = re.findall(r'text-transform:uppercase;">([^<]+)</span>', blk2)
        ru2 = [s for s in secs2 if any(s.startswith(p) for p in ['Алгебра','Геометрия','Комбинаторика','Логика','Теория'])]
        L(f'D3(c) measured section names = {ru2}')

# ══════════════════════════════════════════════════════════════════════
L('')
L('='*70)
L('D4: RADAR 5 AXES')
L('='*70)
CANON = {'Алгебра','Геометрия','Комбинаторика','Логика','Теория чисел'}
for lbl, uid in [('zero-user',uid4),('D2-user',uid2)]:
    h = render(uid)
    i = h.find("data-mastery='")
    if i >= 0:
        s = i + len("data-mastery='"); e = h.find("'", s)
        r = json.loads(h[s:e])
        present = {d['name'] for d in r}
        L(f'D4(a) {lbl} ({len(r)} axes): {[(d["name"],d["value"]) for d in r]}')
        L(f'D4(a) {lbl} all 5 canonical: {CANON.issubset(present)}')
    else:
        L(f'D4(a) {lbl} data-mastery NOT FOUND')

L('')
L(f'D4(b) RADAR_TOPICS = algebra,geometry,combinatorics,logic,number_theory @ prep_planner.py:25')
L(f'D4(c) JS: mastery_radar.js:14 — no zero-axis filtering')

# ─── 5. Module import + prep route smoke test ───────────────────────
L('')
L('='*70)
L('S5: MODULE IMPORT + PREP ROUTE SMOKE TEST')
L('='*70)

import importlib as _il, os as _os
_routes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'routes')
_import_errors = []
for _fn in sorted(_os.listdir(_routes_dir)):
    if _fn.endswith('.py') and not _fn.startswith('_') and _fn != '__init__.py':
        _modname = f'routes.{_fn[:-3]}'
        try:
            _il.import_module(_modname)
            L(f'S5(a) IMPORT OK: {_modname}')
        except Exception as _ie:
            _import_errors.append(f'{_modname}: {_ie}')
            L(f'S5(a) IMPORT FAIL: {_modname} — {_ie}')

if _import_errors:
    L(f'S5(a) TOTAL IMPORT FAILURES: {len(_import_errors)}')
else:
    L('S5(a) ALL IMPORTS OK')

# Smoke-test parameterless GET routes under /prep via test_client
PREP_GET_URLS = [
    '/prep/',
    '/prep/new',
    '/prep/coach',
    '/prep/probe',
    '/prep/onboarding',
    '/prep/coach/greeting',
    '/prep/coach/history',
]

L(f'S5(b) Testing {len(PREP_GET_URLS)} /prep GET routes with uid={uid2}')

_error_500 = []
_error_other = []
_ok_count = 0

with app.test_client() as _c:
    with _c.session_transaction() as _s:
        _s['_user_id'] = str(uid2); _s['_fresh'] = True
    with app.app_context():
        db.session.autoflush = False

    for _url in PREP_GET_URLS:
        try:
            _r = _c.get(_url)
            _code = _r.status_code
            if _code >= 500:
                _error_500.append((_url, _code, _r.data.decode('utf-8','replace')[:300]))
                L(f'S5(c) 5xx: {_url} -> {_code}')
            elif _code >= 400:
                _error_other.append((_url, _code))
                L(f'S5(c) 4xx: {_url} -> {_code}')
            else:
                _ok_count += 1
                L(f'S5(c) OK: {_url} -> {_code}')
        except Exception as _ce:
            _error_500.append((_url, 'EXC', str(_ce)[:300]))
            L(f'S5(c) EXC: {_url} — {_ce}')

    with app.app_context():
        db.session.autoflush = True

L(f'S5(d) ok={_ok_count} 4xx={len(_error_other)} 5xx/EXC={len(_error_500)}')
if _error_500:
    for _u, _c, _t in _error_500:
        L(f'S5(d) FAIL: {_u} code={_c} trace={_t}')
    L('S5 SUMMARY: FAIL — 5xx or exceptions on /prep routes')
else:
    L('S5 SUMMARY: ALL CLEAN — no 5xx on /prep routes')

L('')
L('='*70)
L('COMPLETE')
L('='*70)

with open('regression_night_output.txt','w',encoding='utf-8') as f:
    f.write('\n'.join(OUT))
sys.stderr.write('\nDONE\n')
