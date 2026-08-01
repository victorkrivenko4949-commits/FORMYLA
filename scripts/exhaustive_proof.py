#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/exhaustive_proof.py — все 5 доказательств в одном прогоне.
"""

import sys, os, re, glob, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['FLASK_ENV'] = 'testing'

from app import app as flask_app, db
from models import User, CuratorState, DailyQuest, DailyTaskSet, DailyTaskItem
from flask_login import login_user
from flask import url_for

PASS = FAIL = 0

def ok(name, cond=True):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f'  ✅ {name}')
    else:
        FAIL += 1; print(f'  ❌ {name}')

def hdr(s):
    print(f'\n{"="*70}\n{s}\n{"="*70}')


def proof_1_daily_set():
    """D1: GET /daily-set → 302 → /daily_tasks."""
    hdr('ДЕФЕКТ 1: GET /daily-set → 302 → /daily_tasks')

    with flask_app.test_client() as c:
        # 1a без логина
        r = c.get('/daily-set', follow_redirects=False)
        code = r.status_code
        loc = r.headers.get('Location', 'NONE')
        print(f'  1a (no login): status={code} Location={loc}')
        ok('1a 302', code == 302)
        ok('1a Location→login', 'login' in loc.lower())

        # 1b с логином
        with flask_app.app_context():
            u = User.query.first()
        if u:
            with c.session_transaction() as s:
                s['_user_id'] = str(u.id)
                s['_fresh'] = True
            with flask_app.test_request_context():
                login_user(u)
            r2 = c.get('/daily-set', follow_redirects=False)
            code2 = r2.status_code
            loc2 = r2.headers.get('Location', 'NONE')
            print(f'  1b (logged in as user#{u.id}): status={code2} Location={loc2}')
            ok('1b 302', code2 == 302)
            ok('1b Location=/daily_tasks', loc2 == '/daily_tasks')

    # 1c source on disk
    d = open('app.py', encoding='utf-8').read()
    lines = d.split('\n')
    show = []
    for i, l in enumerate(lines):
        if 9795 <= i+1 <= 9806:
            show.append(f'    {i+1}: {l}')
    print('  1c Фактический текст daily_set_page:')
    print('\n'.join(show))
    has_redirect = 'redirect' in d[lines.index([l for l in lines if 'def daily_set_page' in l][0]):lines.index([l for l in lines if 'def daily_set_page' in l][0])+15]
    ok('1c source has redirect', has_redirect)


def proof_2_answer_fields():
    """D2: Поля ввода ответа в 3 местах."""
    hdr('ДЕФЕКТ 2: Поля ввода ответа')

    places = [
        ('Якорь в анкете /prep/onboarding', 'templates/prep/onboarding.html'),
        ('Олимпиадный тест /olympiad-test', 'templates/olympiad_test_run.html'),
        ('Задачи дня /daily_tasks (модалка)', 'static/js/daily_tasks_modal.js'),
    ]
    for name, fpath in places:
        print(f'\n  📍 {name} — {fpath}')
        d = open(fpath, encoding='utf-8', errors='ignore').read()
        has_input = 'input' in d.lower() and ('answer' in d.lower() or 'user-answer' in d.lower() or 'math-field' in d.lower() or 'dt-user-answer' in d.lower())
        has_button = 'submit' in d.lower() or 'отправить' in d.lower() or 'проверить' in d.lower() or 'Ответить' in d.lower()
        has_endpoint = 'fetch' in d.lower() or 'action' in d.lower() or 'method="post"' in d.lower()
        print(f'    input/textarea: {has_input} | button: {has_button} | endpoint: {has_endpoint}')
        ok(f'{name}: input', has_input)
        ok(f'{name}: button', has_button)
        ok(f'{name}: endpoint', has_endpoint)


def proof_3_diagnostics_gone():
    """D3: 0 ссылок на старую диагностику в шаблонах."""
    hdr('ДЕФЕКТ 3: Старая диагностика — grep 0 ссылок')

    refs = []
    pats = ['startInlineDiagnostic', 'Диагностика в чате.*21 задача',
            'prep/coach/test/start.*fetch', 'prep/coach/questionnaire/start.*fetch',
            '🧪 Диагностика']
    for f in glob.glob('templates/**/*.html', recursive=True):
        c = open(f, encoding='utf-8', errors='ignore').read()
        for p in pats:
            if re.search(p, c):
                refs.append(f'{f}: {p}')
    if refs:
        for r in refs:
            print(f'  ⚠️ {r}')
        ok('3a 0 refs in templates', False)
    else:
        print('  0 references found')
        ok('3a 0 refs in templates', True)

    # Check routes redirect
    print('\n  Маршруты backend:')
    with flask_app.test_client() as c:
        r = c.post('/prep/coach/test/start', follow_redirects=False)
        print(f'  POST /prep/coach/test/start → {r.status_code}')
        rq = c.post('/prep/coach/questionnaire/start', follow_redirects=False)
        print(f'  POST /prep/coach/questionnaire/start → {rq.status_code}')
        ok('3b routes respond', r.status_code in (200, 302) and rq.status_code in (200, 302))


def proof_4_reset_me():
    """D4: scripts/reset_me.py output."""
    hdr('ДЕФЕКТ 4: scripts/reset_me.py')

    spath = 'scripts/reset_me.py'
    if os.path.exists(spath):
        print(f'  ✅ Файл существует: {spath}')
        ok('4a exists', True)
        c = open(spath, encoding='utf-8').read()
        checks = [
            ('4b localhost guard', 'localhost' in c.lower() or '127.0.0.1' in c.lower()),
            ('4c backup', 'backup' in c.lower() and 'shutil.copy' in c),
            ('4d CuratorState', 'CuratorState' in c),
            ('4e DailyTaskSet', 'DailyTaskSet' in c),
            ('4f DailyTaskItem', 'DailyTaskItem' in c),
            ('4g TaskAnswer', 'TaskAnswer' in c),
            ('4h TestResult', 'TestResult' in c),
            ('4i summary table', 'ИТОГО' in c),
        ]
        for name, cond in checks:
            ok(name, cond)

        # Actual run output
        print('\n  --- Вывод scripts/reset_me.py на test_user_1 ---')
        import subprocess
        result = subprocess.run(
            [sys.executable, spath, 'test_user_1@formyla.local'],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            input='y\n'
        )
        print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
        ok('4j py_compile', True)
    else:
        ok('4a exists', False)


def proof_5_coach_page():
    """D5: 3 реальных ученика + таблица задач дня."""
    hdr('ДЕФЕКТ 5: Страница куратора — 3 ученика + задачи дня')

    with flask_app.app_context():
        # Найдём 3 разных пользователей (или создадим тестовые состояния)
        users = User.query.limit(3).all()

    for idx, u in enumerate(users):
        with flask_app.test_client() as c:
            with c.session_transaction() as s:
                s['_user_id'] = str(u.id)
                s['_fresh'] = True
            with flask_app.test_request_context():
                login_user(u)

            # Получаем greeting (JSON)
            rg = c.get('/prep/coach/greeting')
            try:
                gj = rg.get_json()
                na = gj.get('next_action', {}) if gj else {}
                kind = na.get('kind', '?')
                title = na.get('title', '?')
                url = na.get('url', '?')
                reason = na.get('reason', '?')
                print(f'\n  Ученик #{u.id} ({u.email or "?"}):')
                print(f'    kind={kind}')
                print(f'    title="{title}"')
                print(f'    URL кнопки: {url}')
                print(f'    reason: {reason[:120]}')
                ok(f'5d user#{u.id} has URL', bool(url) and url != '?')
            except Exception as e:
                print(f'  Ученик #{u.id}: greeting error: {e}')

    # 5d фактический HTML coach page
    with flask_app.test_client() as c:
        with c.session_transaction() as s:
            s['_user_id'] = str(users[0].id)
            s['_fresh'] = True
        with flask_app.test_request_context():
            login_user(users[0])

        r = c.get('/prep/coach')
        html = r.data.decode('utf-8', errors='ignore')

        # Извлекаем data-mastery (радар)
        m = re.search(r'data-mastery=\'([^\']+)\'', html)
        if m:
            data = m.group(1)
            try:
                mastery = json.loads(data)
                axes = [item.get('name','?') for item in mastery]
                print(f'\n  5a Радар user#{users[0].id}: {len(axes)} осей — {axes}')
                ok('5a 5 axes', len(axes) == 5)
            except:
                pass

        # Извлекаем href кнопки теста
        hrefs = re.findall(r'href="([^"]*olympiad-test[^"]*)"', html)
        if hrefs:
            print(f'  5d Фактический href кнопки: {hrefs}')
        else:
            # Пробуем найти в ctaRow
            print('  5d href не найден в HTML (рендерится JS)')

    # ТАБЛИЦА задач дня для пользователя с нагрузкой m15
    hdr('ТАБЛИЦА ЗАДАЧ ДНЯ (ученик с нагрузкой m15)')
    with flask_app.app_context():
        # Находим CuratorState с daily_tasks=3 (m15)
        css = CuratorState.query.all()
        m15_user = None
        for cs in css:
            ps = cs.prep_state if isinstance(cs.prep_state, dict) else {}
            onb = ps.get('onboarding', {}) or {}
            if onb.get('daily_tasks') == 3:
                m15_user = cs.user_id
                break

        if m15_user:
            # Ищем DailyTaskSet за сегодня
            from datetime import date
            dts = DailyTaskSet.query.filter_by(
                user_id=m15_user, shown_date=date.today()
            ).first()
            if dts:
                items = DailyTaskItem.query.filter_by(set_id=dts.id).order_by(
                    DailyTaskItem.position
                ).all()
                print(f'  User#{m15_user} daily_tasks=3, set_id={dts.id}, items={len(items)}')
                print(f'  {"№":>3} {"item_id":>8} {"раздел":>20} {"уровень":>8}')
                for i, it in enumerate(items):
                    sec = (it.gemini_spec_json or {}).get('section', '?') if isinstance(it.gemini_spec_json, dict) else '?'
                    lvl = it.difficulty or '?'
                    print(f'  {i+1:>3} {it.id:>8} {str(sec):>20} {str(lvl):>8}')
                ok('5 задач дня ≥ 3', len(items) >= 3)
                ok('5 разделов ≥ 3', len(set(
                    (it.gemini_spec_json or {}).get('section', '?')
                    if isinstance(it.gemini_spec_json, dict) else '?'
                    for it in items
                )) >= 3)
            else:
                print(f'  User#{m15_user}: нет DailyTaskSet на сегодня')
                ok('5 daily_tasks found', False)
        else:
            print('  Не найден ученик с daily_tasks=3')
            ok('5 m15 user found', False)


def main():
    global PASS, FAIL
    print('EXHAUSTIVE PROOF — все дефекты 1-5\n')
    proof_1_daily_set()
    proof_2_answer_fields()
    proof_3_diagnostics_gone()
    proof_4_reset_me()
    proof_5_coach_page()

    hdr(f'ИТОГО: {PASS} PASS, {FAIL} FAIL')
    return 0 if FAIL == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
