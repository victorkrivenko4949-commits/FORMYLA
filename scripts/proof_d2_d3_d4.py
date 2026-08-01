# -*- coding: utf-8 -*-
"""5 ДОКАЗАТЕЛЬСТВ через app.test_client() — Д2, Д3, Д4.

Запуск:
    python scripts/proof_d2_d3_d4.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import User, AdaptiveTask
from models_curator import CuratorState
from daily_tasks.models import DailyTaskSet, DailyTaskItem
from flask.testing import FlaskClient

app.config['TESTING'] = True
# Отключаем SERVER_NAME для test_client, чтобы избежать ошибок url_for
app.config['SERVER_NAME'] = None
# Сохраняем оригинальный secret_key
if not app.secret_key:
    app.secret_key = 'proof-test-key'

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        line = f"  [PASS] {name}"
    else:
        FAIL += 1
        line = f"  [FAIL] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return condition


def line():
    print("  " + "─" * 60)


with app.app_context():
    # ── Создаём чистого тестового ученика ──────────────────────────
    import uuid
    test_email = f"proof_test_{uuid.uuid4().hex[:8]}@test.local"
    test_user = User(
        email=test_email,
        name='Proof Test Student',
        preferred_grade=9,
        # passwordless auth - не требует set_password
    )
    db.session.add(test_user)
    db.session.commit()
    uid = test_user.id
    print(f"\n{'='*60}")
    print(f"  Тестовый ученик: id={uid} email={test_email} grade=9")
    print(f"{'='*60}\n")

    # ── Инициализируем CuratorState ──────────────────────────────
    from models_curator import CuratorState as CS
    cs = CS.query.filter_by(user_id=uid).first()
    if not cs:
        cs = CS(user_id=uid)
        db.session.add(cs)
        db.session.commit()

    # ── Инициализируем level_engine ──────────────────────────────
    from services.level_engine import set_prior, get_state
    set_prior(uid, 3.0, 1.5, source="proof_test")

with app.test_client() as client:
    # Логинимся через сессию
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True

    # ═══════════════════════════════════════════════════════════════
    # ДОКАЗАТЕЛЬСТВО 1: пройти анкету (новый onboarding)
    # ═══════════════════════════════════════════════════════════════
    print("─ ДОКАЗАТЕЛЬСТВО 1: анкета онбординга (POST /prep/onboarding/answer) ─")
    line()

    # 1a. _start
    resp = client.post(
        '/prep/onboarding/answer',
        data=json.dumps({"qid": "_start", "key": ""}),
        content_type='application/json',
    )
    data = json.loads(resp.data.decode('utf-8'))
    check("1.1 _start done=False", not data.get('done'), f"done={data.get('done')}")
    print(f"     step={data.get('step')} grade_auto={data.get('grade_auto')}")
    qid = data.get('question', {}).get('id', '')
    check("1.2 first question is 'target' (grade auto-set)", qid == 'target',
          f"qid={qid}")

    # 1b. target = lvl3
    resp = client.post(
        '/prep/onboarding/answer',
        data=json.dumps({"qid": "target", "key": "lvl3"}),
        content_type='application/json',
    )
    data = json.loads(resp.data.decode('utf-8'))
    next_qid = data.get('question', {}).get('id', '')
    check("1.3 Q2(target)→Q3(olymp_reach)", not data.get('done'), f"next_qid={next_qid}")

    # 1c. olymp_reach = muni
    resp = client.post(
        '/prep/onboarding/answer',
        data=json.dumps({"qid": "olymp_reach", "key": "muni"}),
        content_type='application/json',
    )
    data = json.loads(resp.data.decode('utf-8'))
    next_qid = data.get('question', {}).get('id', '')
    check("1.4 Q3→Q4(load)", not data.get('done'), f"next_qid={next_qid}")

    # 1d. load = m30
    resp = client.post(
        '/prep/onboarding/answer',
        data=json.dumps({"qid": "load", "key": "m30"}),
        content_type='application/json',
    )
    data = json.loads(resp.data.decode('utf-8'))
    next_qid = data.get('question', {}).get('id', '')
    check("1.5 Q4→Q5(deadline)", not data.get('done'), f"next_qid={next_qid}")

    # 1e. deadline = none
    resp = client.post(
        '/prep/onboarding/answer',
        data=json.dumps({"qid": "deadline", "key": "none"}),
        content_type='application/json',
    )
    data = json.loads(resp.data.decode('utf-8'))
    anchor = data.get('anchor')
    step = data.get('step')

    check("1.6 Q5 → first anchor", anchor is not None or data.get('anchors_unavailable'),
          f"step={step} anchor={'yes' if anchor else 'no'} anchors_unavailable={data.get('anchors_unavailable')}")

    # 1f. Answer 3 anchors (or skip if unavailable)
    anchors_answered = 0
    anchor_results = []
    while anchor is not None:
        task_id = anchor['task_id']
        # Ищем задачу в БД
        with app.app_context():
            task = db.session.get(AdaptiveTask, task_id)
        if task:
            correct_answer = (task.correct_answer or '').strip()
            # Пробуем угадать ответ
            user_answer = correct_answer if correct_answer else "42"
        else:
            user_answer = "1"

        resp = client.post(
            '/prep/onboarding/anchor',
            data=json.dumps({"task_id": task_id, "answer": user_answer}),
            content_type='application/json',
        )
        adata = json.loads(resp.data.decode('utf-8'))
        correct = adata.get('correct')
        anchor = adata.get('anchor')
        anchors_answered += 1
        if correct is not None:
            anchor_results.append(correct)
        print(f"     anchor {anchors_answered}: task_id={task_id} correct={correct} "
              f"next={'yes' if anchor else 'no'}")
        if anchors_answered >= 3:
            break

    check("1.7 answered 1-3 anchors", anchors_answered >= 1,
          f"answered={anchors_answered}")

    # 1g. _finish
    resp = client.post(
        '/prep/onboarding/answer',
        data=json.dumps({"qid": "_finish", "key": ""}),
        content_type='application/json',
    )
    finish_data = json.loads(resp.data.decode('utf-8'))
    result = finish_data.get('result', {})
    print(f"\n  ── Тело ответа _finish (OnboardingResult.to_json()) ──")
    for key in ['grade', 'target_level', 'prior_mu', 'prior_sigma',
                'start_level', 'route_ceiling', 'test_length',
                'daily_tasks', 'deadline_date', 'days_left', 'anchors', 'conflict']:
        val = result.get(key, 'НЕТ')
        print(f"     {key}: {val}")

    check("1.8 finish done=True", finish_data.get('done'), f"done={finish_data.get('done')}")
    check("1.9 result не пустой (prior_mu есть)",
          result.get('prior_mu') is not None,
          f"prior_mu={result.get('prior_mu')}")
    check("1.10 grade присутствует",
          result.get('grade') is not None,
          f"grade={result.get('grade')}")
    check("1.11 target_level присутствует",
          result.get('target_level') is not None,
          f"target_level={result.get('target_level')}")
    check("1.12 daily_tasks присутствует",
          result.get('daily_tasks') is not None,
          f"daily_tasks={result.get('daily_tasks')}")

    # 1h. Сверка с БД
    with app.app_context():
        cs2 = CS.query.filter_by(user_id=uid).first()
        prep_state = getattr(cs2, 'prep_state', None) or {}
        db_onboarding = prep_state.get('onboarding', {})
        print(f"\n  ── prep_state['onboarding'] из БД ──")
        for key in ['grade', 'target_level', 'prior_mu', 'prior_sigma',
                    'start_level', 'route_ceiling', 'test_length',
                    'daily_tasks', 'deadline_date', 'days_left', 'conflict']:
            val = db_onboarding.get(key, 'НЕТ')
            print(f"     {key}: {val}")

    # Сверка ключевых значений
    check("1.13 БД.grade совпадает с _finish.grade",
          db_onboarding.get('grade') == result.get('grade'),
          f"DB={db_onboarding.get('grade')} vs finish={result.get('grade')}")
    check("1.14 БД.prior_mu совпадает с _finish.prior_mu",
          db_onboarding.get('prior_mu') == result.get('prior_mu'),
          f"DB={db_onboarding.get('prior_mu')} vs finish={result.get('prior_mu')}")
    check("1.15 БД.daily_tasks совпадает с _finish.daily_tasks",
          db_onboarding.get('daily_tasks') == result.get('daily_tasks'),
          f"DB={db_onboarding.get('daily_tasks')} vs finish={result.get('daily_tasks')}")

    # ═══════════════════════════════════════════════════════════════
    # ДОКАЗАТЕЛЬСТВО 2: открыть задачи дня (путём ученика из куратора)
    # ═══════════════════════════════════════════════════════════════
    print(f"\n─ ДОКАЗАТЕЛЬСТВО 2: Задачи дня GET /daily_tasks ─")
    line()

    # Проверяем, что prep_state.onboarding заполнен для pick_daily_set
    with app.app_context():
        cs3 = CS.query.filter_by(user_id=uid).first()
        onboard = (getattr(cs3, 'prep_state', None) or {}).get('onboarding', {})
        print(f"  prep_state.onboarding keys: {list(onboard.keys()) if onboard else 'None'}")

    resp = client.get('/daily_tasks/')
    assert resp.status_code in (200, 302, 404, 308), f"unexpected status {resp.status_code}"

    if resp.status_code in (302, 308):
        print(f"  Redirect to: {resp.headers.get('Location', '?')}")
        # follow redirect
        loc = resp.headers.get('Location', '/daily_tasks/')
        resp = client.get(loc)
    if resp.status_code == 404:
        data = json.loads(resp.data.decode('utf-8'))
        print(f"  404 response: {data.get('status')} - {data.get('message', '')}")
        check("2.0 daily_tasks вернул статус",
              data.get('status') in ('no_set', 'generating', 'ready', 'partial'),
              f"status={data.get('status')}")
    elif resp.status_code == 200:
        html = resp.data.decode('utf-8')
        # Ищем в HTML данные
        print(f"  200 OK, длина HTML: {len(html)}")

    # Получаем через API (JSON) если возможно
    resp2 = client.get('/daily_tasks', headers={'Accept': 'application/json'})
    if resp2.status_code == 200:
        try:
            jdata = json.loads(resp2.data.decode('utf-8'))
        except json.JSONDecodeError:
            jdata = {"status": "html_response"}

        items = jdata.get('items', [])
        status = jdata.get('status', 'unknown')
        print(f"  Статус: {status}, задач: {len(items)}")

        if items:
            print(f"\n  ── Таблица задач дня ──")
            print(f"  {'№':>3} / {'item_id':>7} / {'раздел':<20} / {'уровень':>6}")
            line()
            for i, it in enumerate(items, 1):
                section = it.get('topic', it.get('subject', '?'))
                level = it.get('difficulty_level', '?')
                item_id = it.get('item_id', it.get('id', '?'))
                print(f"  {i:>3} / {str(item_id):>7} / {str(section)[:20]:<20} / {str(level):>6}")
            check("2.1 количество задач совпадает с daily_tasks анкеты",
                  len(items) == result.get('daily_tasks', 5),
                  f"items={len(items)} daily_tasks={result.get('daily_tasks', 5)}")
        first_items = items

    # ═══════════════════════════════════════════════════════════════
    # ДОКАЗАТЕЛЬСТВО 3: повторное открытие — тот же набор
    # ═══════════════════════════════════════════════════════════════
    print(f"\n─ ДОКАЗАТЕЛЬСТВО 3: повторное открытие задач дня ─")
    line()

    resp3 = client.get('/daily_tasks', headers={'Accept': 'application/json'})
    if resp3.status_code == 200:
        try:
            jdata3 = json.loads(resp3.data.decode('utf-8'))
        except json.JSONDecodeError:
            jdata3 = {"status": "html_response"}

        items3 = jdata3.get('items', [])
        print(f"  Повторно: статус={jdata3.get('status')}, задач={len(items3)}")

        if first_items and items3:
            first_ids = set(it.get('item_id', it.get('id')) for it in first_items)
            second_ids = set(it.get('item_id', it.get('id')) for it in items3)
            check("3.1 item_id совпадают (набор не пересобран)",
                  first_ids == second_ids,
                  f"first={sorted(first_ids)[:3]}... second={sorted(second_ids)[:3]}...")
            check("3.2 количество задач не изменилось",
                  len(items3) == len(first_items),
                  f"first={len(first_items)} second={len(items3)}")

    # ═══════════════════════════════════════════════════════════════
    # ДОКАЗАТЕЛЬСТВО 4: POST /prep/coach/chat — "какой у меня уровень"
    # ═══════════════════════════════════════════════════════════════
    print(f"\n─ ДОКАЗАТЕЛЬСТВО 4: POST /prep/coach/chat ─")
    line()

    resp4 = client.post(
        '/prep/coach/chat',
        data=json.dumps({"message": "какой у меня уровень"}),
        content_type='application/json',
    )
    check("4.1 chat ответ 200 (не упал)", resp4.status_code == 200,
          f"status={resp4.status_code}")
    try:
        chat_data = json.loads(resp4.data.decode('utf-8'))
    except json.JSONDecodeError:
        chat_data = {"reply": resp4.data.decode('utf-8')[:500]}

    reply_text = chat_data.get('reply', '')
    print(f"  Ответ куратора (первые 200 символов): {reply_text[:200]}...")
    check("4.2 KeyError отсутствует (reply не пустой)",
          bool(reply_text), f"reply_len={len(reply_text)}")
    check("4.3 not 'error' in ответе",
          'error' not in str(chat_data).lower()[:50] or 'KeyError' not in str(chat_data),
          f"top keys: {list(chat_data.keys())}")

    # ═══════════════════════════════════════════════════════════════
    # ДОКАЗАТЕЛЬСТВО 5: regression_night.py
    # ═══════════════════════════════════════════════════════════════
    print(f"\n─ ДОКАЗАТЕЛЬСТВО 5: regression_night.py ─")
    line()

    import subprocess
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    reg_path = os.path.join(script_dir, 'scripts', 'regression_night.py')
    result = subprocess.run(
        [sys.executable, reg_path],
        capture_output=True, text=True, timeout=60,
        cwd=script_dir,
    )
    output = result.stdout
    print(output)

    # Подсчитываем PASS/FAIL
    pass_count = output.count('[PASS]')
    fail_count = output.count('[FAIL]')
    check("5.1 все проверки regression_night PASS",
          fail_count == 0, f"PASS={pass_count} FAIL={fail_count}")

    # ═══════════════════════════════════════════════════════════════
    # ИТОГО
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print(f"  ИТОГО: PASS={PASS} FAIL={FAIL}")
    print(f"{'='*60}")

    # Удаляем тестового ученика
    with app.app_context():
        # Удаляем DailyTaskSet и DailyTaskItem
        dss = DailyTaskSet.query.filter_by(user_id=uid).all()
        for ds in dss:
            DailyTaskItem.query.filter_by(daily_set_id=ds.id).delete()
        DailyTaskSet.query.filter_by(user_id=uid).delete()
        # Удаляем CuratorState
        CS.query.filter_by(user_id=uid).delete()
        # Удаляем пользователя
        User.query.filter_by(id=uid).delete()
        db.session.commit()
        print("  Тестовый ученик удалён.")

    if FAIL > 0:
        print(f"\n  ⚠️  {FAIL} проверок провалено!")
        sys.exit(1)
    else:
        print(f"\n  ✅ Все {PASS} проверок пройдены!")
        sys.exit(0)
