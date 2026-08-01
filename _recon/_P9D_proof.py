# -*- coding: utf-8 -*-
"""P9D_PROOF — Сквозной proof-тест 8 задач."""
from __future__ import annotations

import json, os, sys, traceback, subprocess
from datetime import datetime, timezone

sys.path.insert(0, os.getcwd())

from app import app, db
from models import User
from models_curator import CuratorState

import logging
logging.basicConfig(level=logging.ERROR)

NOW = datetime.now(timezone.utc)
TS = NOW.strftime('%Y%m%d%H%M%S')
TEST_EMAIL = f"p9d_{TS}@test.local"
OUT = []

def p(*a):
    line = ' '.join(str(x) for x in a)
    print(line); OUT.append(line)

def hr(t):
    p(f"\n{'='*70}\n=== {t}\n{'='*70}")

def get_u(email=TEST_EMAIL):
    return User.query.filter_by(email=email).first()

def del_u(email):
    u = get_u(email)
    if not u: return
    uid = u.id
    try:
        db.session.execute(db.text("DELETE FROM curator_state WHERE user_id=:uid"), {"uid": uid})
        db.session.execute(db.text("DELETE FROM users WHERE id=:uid"), {"uid": uid})
        db.session.commit()
    except Exception as e:
        db.session.rollback()

def make_user(email=TEST_EMAIL):
    """Create user directly in DB, bypassing SMTP."""
    del_u(email)
    u = User(email=email)
    db.session.add(u)
    db.session.flush()
    uid = u.id
    db.session.commit()
    p(f"    created user id={uid}")
    return uid


# ═══════════════════════════════════════════════════════════════════
def task1():
    hr("TASK 1: ЦЕПОЧКА РЕДИРЕКТОВ")

    with app.test_client() as c:
        # Use dev_login to get authenticated
        r = c.get('/dev_login?uid=1', follow_redirects=False)
        p(f"\n  dev_login uid=1 → {r.status_code}")

        # Now test /intake vs /prep/onboarding for existing user
        r = c.get('/intake', follow_redirects=False)
        p(f"  GET /intake → {r.status_code}")
        if r.status_code == 200:
            html = r.data.decode('utf-8', errors='replace')
            p(f"    HTML: {len(html)} bytes")

        r = c.get('/prep/onboarding', follow_redirects=False)
        p(f"  GET /prep/onboarding → {r.status_code}")

        p("\n  === ЦЕПОЧКА (факты из кода) ===")
        p("  Новый пользователь:")
        p("    POST /login → 302 → /verify-code")
        p("    POST /verify-code → 302 → /about?onboarding=1")
        p("    GET /about?onboarding=1 → 200 (КОНЕЧНЫЙ)")
        p("    CTA → / (главная)")
        p("    НЕТ автоматического редиректа на анкету")
        p("  Новая анкета: /intake")
        p("  Старая анкета: /prep/onboarding")

        p("\n  === СТАРЫЕ ТОЧКИ ВХОДА ===")
        for path, lbl in [('/prep/coach','coach'),('/prep/probe','probe')]:
            r = c.get(path, follow_redirects=False)
            dest = r.headers.get('Location','') if r.status_code == 302 else f'200 html:{len(r.data)}b'
            p(f"    GET {path} → {r.status_code} {dest}")
            if r.status_code == 200:
                t = r.data.decode('utf-8', errors='replace')[:500]
                if '/prep/onboarding' in t:
                    p(f"      → СТАРАЯ анкета")
                if '/intake' in t:
                    p(f"      → НОВАЯ анкета")

        p("\n  === 5 МЕСТ → СТАРАЯ АНКЕТА ===")
        for pt in [
            "routes/prep.py:2941 — onboarding_page()",
            "routes/prep.py:1312 — /prep/probe guard",
            "routes/prep.py:3004 — questionnaire_start redirect",
            "routes/prep.py:3014 — questionnaire_answer redirect",
            "routes/prep.py:1945 — coach_test_start redirect",
        ]:
            p(f"    {pt}")
        p("  ТРЕБУЕТСЯ: переключить с /prep/onboarding на /intake")
    return True


# ═══════════════════════════════════════════════════════════════════
def task2():
    hr("TASK 2: СКВОЗНОЙ ПРОХОД /intake → дамп")

    with app.test_client() as c:
        uid = make_user(TEST_EMAIL)

        # Login via dev_login style — authenticate the session
        r = c.get(f'/dev_login?uid={uid}', follow_redirects=False)
        p(f"\n  dev_login uid={uid} → {r.status_code}")

        p("\n[1] GET /intake")
        r = c.get('/intake', follow_redirects=False)
        p(f"    → {r.status_code}")

        p("[2] POST /intake/start")
        r = c.post('/intake/start', content_type='application/json')
        p(f"    → {r.status_code}")
        d = r.get_json() or {}
        q = d.get('question', {})
        p(f"    Q: «{q.get('text','?')}»")

        answers = [
            ('class','9'),
            ('goal','dont_know'),
            ('experience','participated'),
            ('time','m60'),
            ('weak_sections','geometry,logic'),
        ]
        for qid, key in answers:
            r = c.post('/intake/answer', json={'qid':qid,'key':key}, content_type='application/json')
            d = r.get_json() or {}
            code = r.status_code
            if d.get('anchor'):
                a = d['anchor']
                p(f"    {qid} → ЯКОРЬ#{a.get('anchor_idx')}: {a.get('section_ru')}")
                stmt = a.get('statement','')
                p(f"      «{stmt[:200]}»")
            elif d.get('question'):
                nq = d['question']
                p(f"    {qid} → {code} next: «{nq.get('text','?')[:60]}»")
            elif d.get('done'):
                p(f"    {qid} → {code} done: {json.dumps(d.get('result',{}),ensure_ascii=False)[:200]}")
            else:
                p(f"    {qid} → {code} {d}")

        p("\n[3] ЯКОРЯ:")
        for i in range(5):
            with c.session_transaction() as s:
                ist = s.get('intake', {})
                tasks = ist.get('anchor_tasks', [])
                idx = ist.get('current_anchor_idx', 0)
            if idx >= len(tasks): break
            t = tasks[idx]
            r = c.post('/intake/anchor', json={'task_id':t['db_id'],'answer':'0'}, content_type='application/json')
            d = r.get_json() or {}
            p(f"    #{i+1}: {t['section']:<16} → {r.status_code}")
            if d.get('done'):
                p(f"      result: {json.dumps(d.get('result',{}),ensure_ascii=False)[:300]}")
                break

        p("\n[4] ДАМП ПРОФИЛЯ:")
        cs = CuratorState.query.filter_by(user_id=uid).first()
        if cs:
            ps = dict(cs.prep_state) if isinstance(cs.prep_state, dict) else {}
            it = ps.get('intake', {})
            skip = {'anchor_results','answers'}
            for k in sorted(it):
                if k not in skip:
                    p(f"    {k}: {it[k]}")
            p(f"    answers: {json.dumps(it.get('answers',{}),ensure_ascii=False)}")
            ar = it.get('anchor_results', [])
            p(f"    anchors ({len(ar)}):")
            for a in ar:
                p(f"      {a.get('section'):<16} task_id={a.get('task_id')} correct={a.get('correct')}")
            p(f"    onboarding_done: {cs.onboarding_done}")
            p(f"    grade: {cs.grade}")
            p(f"    level_mu/sigma: {cs.level_mu} / {cs.level_sigma}")
        u2 = db.session.get(User, uid)
        if u2:
            p(f"    preferred_grade: {u2.preferred_grade}")
            p(f"    onboarded_at: {u2.onboarded_at}")
    return True


# ═══════════════════════════════════════════════════════════════════
def task3():
    hr("TASK 3: НОРМА ИЗ ВРЕМЕНИ")
    from services.daily_task_rotation import get_daily_task_count

    u = get_u()
    if not u: p("\n  Нет пользователя"); return True
    cs = CuratorState.query.filter_by(user_id=u.id).first()

    p(f"\n  {'День':<6} {'Размер':<8} {'Примечание'}")
    p(f"  {'-'*6} {'-'*8} {'-'*30}")
    for day in range(1, 11):
        if cs:
            ps = dict(cs.prep_state) if isinstance(cs.prep_state, dict) else {}
            ps['monthly_cycle'] = {'start_date': '2026-01-01', 'day_index': day}
            cs.prep_state = ps; db.session.commit()
        c = get_daily_task_count(u.id)
        note = "зондирование" if day <= 7 else "норма"
        p(f"  {day:<6} {c:<8} {note}")
    if cs:
        ps = dict(cs.prep_state) if isinstance(cs.prep_state, dict) else {}
        ps.pop('monthly_cycle', None)
        cs.prep_state = ps; db.session.commit()
    p("\n  ОЖИДАНИЕ: 1-7→5, 8-10→15")
    return True


# ═══════════════════════════════════════════════════════════════════
def task4():
    hr("TASK 4: АВТО-ЦЕЛЬ")
    from services.intake_questions import assign_goal, AUTO_GOAL_TABLE

    u = get_u()
    if not u: p("\n  Нет пользователя"); return True
    cs = CuratorState.query.filter_by(user_id=u.id).first()
    it = {}
    if cs:
        ps = dict(cs.prep_state) if isinstance(cs.prep_state, dict) else {}
        it = ps.get('intake', {})

    p(f"\n  Ответ: goal=dont_know, class=9, experience=participated")
    p(f"  Сохранено: goal={it.get('goal')}, goal_auto={it.get('goal_auto')}")
    g, auto = assign_goal(9, 'participated')
    p(f"  Правило → {g}, auto={auto}")

    p(f"\n  ТАБЛИЦА:")
    p(f"  {'Класс':<8} {'Опыт':<18} {'→ Цель':<20}")
    p(f"  {'-'*8} {'-'*18} {'-'*20}")
    em = {'none':'не участвовал','participated':'участвовал','school_prize':'призёр','region_plus':'регион+'}
    gm = {'just_grow':'расти','school_muni':'школьный','region':'регион',
          'region_prize':'призёр рег.','perechnevye':'перечневые'}
    for mc, mxc, exp, goal in AUTO_GOAL_TABLE:
        cs2 = f"{mc}-{mxc}" if mc != mxc else str(mc)
        p(f"  {cs2:<8} {em.get(exp,exp):<18} {gm.get(goal,goal):<20}")
    return True


# ═══════════════════════════════════════════════════════════════════
def task5():
    hr("TASK 5: СЛАБЫЕ РАЗДЕЛЫ")
    from services.daily_task_rotation import _get_onboarding

    u = get_u()
    if not u: p("\n  Нет пользователя"); return True
    onb = _get_onboarding(u.id)
    p(f"\n  weak_sections={onb.get('weak_sections') if onb else 'N/A'}")
    p(f"  weak_priority={onb.get('weak_priority') if onb else 'N/A'}")

    p("\n  pick_daily_set:")
    try:
        from services.daily_task_rotation import pick_daily_set
        r = pick_daily_set(u.id, force_regenerate=True)
        if r and isinstance(r, dict) and 'items' in r:
            items = r['items']
            p(f"  {len(items)} задач")
            from collections import Counter
            sc = Counter(it.get('section',it.get('topic','?')) for it in items)
            p(f"  {'Раздел':<18} {'Задач':<8}")
            p(f"  {'-'*18} {'-'*8}")
            for s,n in sorted(sc.items()):
                p(f"  {s:<18} {n:<8}")
            all5 = {'algebra','geometry','combinatorics','logic','number_theory'}.issubset(set(sc.keys()))
            gl = sc.get('geometry',0)+sc.get('logic',0)
            p(f"  Все 5 разделов: {all5}")
            p(f"  Геометрия+логика: {gl}/{sum(sc.values())}")
        elif r is None:
            p("  Нет данных (тестовая среда)")
            p("  ОЖИДАНИЕ: геометрия+логика > остальных, все 5 разделов каждый день")
    except Exception as e:
        p(f"  Ошибка: {e}")
    return True


# ═══════════════════════════════════════════════════════════════════
def task6():
    hr("TASK 6: КНОПКА НАЗАД")
    femail = f"p9d_back_{TS}@test.local"

    with app.test_client() as c:
        uid = make_user(femail)
        c.get(f'/dev_login?uid={uid}', follow_redirects=False)

        c.post('/intake/start', content_type='application/json')
        c.post('/intake/answer', json={'qid':'class','key':'9'}, content_type='application/json')
        c.post('/intake/answer', json={'qid':'goal','key':'dont_know'}, content_type='application/json')
        c.post('/intake/answer', json={'qid':'experience','key':'participated'}, content_type='application/json')

        with c.session_transaction() as s:
            before = dict(s.get('intake',{}))
            ba = dict(before.get('answers',{}))
        p(f"\n  ДО назад: step={before.get('step')} answers={json.dumps(ba,ensure_ascii=False)}")

        r = c.post('/intake/back', content_type='application/json')
        d = r.get_json() or {}
        p(f"  POST /intake/back → {r.status_code} step={d.get('step')} saved={d.get('saved_answer')}")

        with c.session_transaction() as s:
            after = dict(s.get('intake',{}))
            aa = dict(after.get('answers',{}))
        p(f"  ПОСЛЕ: step={after.get('step')} answers={json.dumps(aa,ensure_ascii=False)}")
        p(f"  Ответы на месте: {all(aa.get(k)==v for k,v in ba.items())}")

        r = c.post('/intake/answer', json={'qid':'experience','key':'participated'}, content_type='application/json')
        p(f"  Вперёд → {r.status_code} step={r.get_json().get('step','?')}")

        with c.session_transaction() as s:
            fin = dict(s.get('intake',{}))
            fa = dict(fin.get('answers',{}))
        p(f"  ФИНАЛ: step={fin.get('step')} answers={json.dumps(fa,ensure_ascii=False)}")

        del_u(femail)
    return True


# ═══════════════════════════════════════════════════════════════════
def task7():
    hr("TASK 7: ЯКОРЯ")
    u = get_u()
    if not u: p("\n  Нет пользователя"); return True
    cs = CuratorState.query.filter_by(user_id=u.id).first()
    if not cs: p("\n  CuratorState не найден"); return True

    ps = dict(cs.prep_state) if isinstance(cs.prep_state, dict) else {}
    it = ps.get('intake', {})
    ar = it.get('anchor_results', [])

    p(f"\n  Якорей: {len(ar)}")
    for i,a in enumerate(ar):
        p(f"    {i+1}. {a.get('section'):<16} correct={a.get('correct')} task_id={a.get('task_id')}")

    p(f"\n  set_prior: intake_service.py:211 (q5→anchors, ДО первого)")
    p(f"  prior_mu={it.get('prior_mu')} prior_sigma={it.get('prior_sigma')}")
    p(f"  level_mu={cs.level_mu} level_sigma={cs.level_sigma}")
    if cs.level_by_section:
        for s,v in sorted((dict(cs.level_by_section) if isinstance(cs.level_by_section,dict) else {}).items()):
            if isinstance(v,dict):
                p(f"  {s}: mu={v.get('mu','?')} sigma={v.get('sigma','?')}")

    p("\n  ОЖИДАНИЕ: 5 якорей, algebra→number_theory→geometry→combinatorics→logic, set_prior 1 раз")
    return True


# ═══════════════════════════════════════════════════════════════════
def task8():
    hr("TASK 8: УДАЛЕНИЕ + PYTEST")
    del_u(TEST_EMAIL)
    p(f"\n  Удалён: {'✓' if get_u() is None else 'ОШИБКА'}")

    # Clean up any remaining test users
    for pat in ['p9d_back_','p9d_']:
        users = User.query.filter(User.email.like(f'%{pat}%')).all()
        for lu in users:
            try:
                db.session.execute(db.text("DELETE FROM curator_state WHERE user_id=:uid"), {"uid":lu.id})
                db.session.execute(db.text("DELETE FROM users WHERE id=:uid"), {"uid":lu.id})
            except Exception:
                pass
        if users: db.session.commit()

    p("\n  python -m pytest -q --tb=no --ignore=_recon --ignore=scripts")
    r = subprocess.run(
        [sys.executable,'-m','pytest','-q','--tb=no','--ignore=_recon','--ignore=scripts'],
        capture_output=True, text=True, timeout=300)
    output = (r.stdout + '\n' + r.stderr)[:5000]
    p(f"\n{output}")
    return True


# ═══════════════════════════════════════════════════════════════════
def main():
    p(f"P9D_PROOF {NOW.isoformat()}")
    p(f"email={TEST_EMAIL}")

    with app.app_context():
        for nm, fn in [
            ('TASK 1',task1),('TASK 2',task2),('TASK 3',task3),
            ('TASK 4',task4),('TASK 5',task5),('TASK 6',task6),
            ('TASK 7',task7),('TASK 8',task8),
        ]:
            try:
                fn()
            except Exception as e:
                p(f"\n!!! {nm} FAILED: {e}")
                traceback.print_exc()
                try: db.session.rollback()
                except: pass

    rp = os.path.join('_recon','P9D_PROOF.md')
    with open(rp,'w',encoding='utf-8') as f:
        f.write('# P9D PROOF\n\n')
        f.write(f'{NOW.isoformat()}\n\n```\n')
        f.write('\n'.join(OUT))
        f.write('\n```\n')
    p(f"\nОтчёт: {rp}")

if __name__ == '__main__':
    main()
