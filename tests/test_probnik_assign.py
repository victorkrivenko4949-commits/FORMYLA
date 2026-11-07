# -*- coding: utf-8 -*-
"""PROBNIK_ASSIGN_V1: назначенный пробник (Росатом, заключительный этап).

Проверяем весь поток на настоящих маршрутах:
  * подбор полного варианта под класс (7–11), формулы LaTeX сбалансированы;
  * в день назначения задачи дня показывают карточку пробника вместо
    «Сегодня выходной», с текстом владельца, «Старт» и «Сменить пробник»;
  * смена варианта до старта; старт → таймер; текст и фото к задачам;
  * сдача → ИИ-проверка 0–7 по задачам → сумма → разбор куратора в чат,
    баннер-уведомление гаснет после открытия;
  * автосдача по таймеру; разовые назначения SEED (Лаврик = как Роман).
ИИ, распознавание фото и фоновые потоки подменены — тест детерминирован.
"""
from __future__ import annotations

import io
import json
import re
from datetime import date, datetime, timedelta

import pytest

_DT_INIT_RE = re.compile(r'<script id="dt-init-data" type="application/json">(.*?)</script>', re.S)


@pytest.fixture
def svc(app, monkeypatch):
    import models_probnik_assign  # noqa: F401
    from models import db
    db.create_all()
    # base.html ждёт переменные из контекст-процессоров боевого app.py
    app.context_processor(lambda: {'tg_trial_state': lambda: None})
    from services import probnik_assign as s
    # фоновые задачи — синхронно, ИИ и OCR — заглушки
    monkeypatch.setattr(s, '_bg', lambda _app, fn, *a: fn(*a))
    monkeypatch.setattr('services.solution_ocr.ocr_solution_images',
                        lambda imgs, task_text='': {'text': 'Пусть \\(x=2\\). Тогда ответ 4.'})
    calls = {'grade': 0, 'review': 0}

    def fake_llm(messages, thinking, max_tokens, timeout):
        assert thinking is True, 'проверка и разбор — только с рассуждением'
        if 'член жюри' in messages[0]['content']:
            calls['grade'] += 1
            return json.dumps({'score': 5, 'verdict': 'partial',
                               'feedback': 'Идея верная, \\(x=2\\), но нет обоснования.',
                               'gaps': ['обоснование']}, ensure_ascii=False)
        calls['review'] += 1
        return 'Итог хороший. План: две недели — обоснования.\n[[ACTION {"type": "raise_level"}]]'
    monkeypatch.setattr(s, '_llm', fake_llm)
    s._calls = calls
    return s


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (400, 300), (250, 250, 250)).save(buf, format='PNG')
    return buf.getvalue()


def _login(client, uid):
    # фикстура app держит общий app context → flask-login кэширует
    # пользователя в g между запросами; сбрасываем при смене аккаунта
    from flask import g
    g.pop('_login_user', None)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_csrf_token'] = 'tok'


H = {'X-CSRF-Token': 'tok'}


# ─── Варианты и LaTeX ─────────────────────────────────────────────────────

@pytest.mark.parametrize('grade', [7, 8, 9, 10, 11])
def test_rosatom_final_variants_complete(svc, grade):
    vs = svc.candidate_variants('rosatom', grade, 'final')
    assert len(vs) >= 2, 'нужен запас для «Сменить пробник»'
    for v in vs:
        assert v['grade'] == grade and 'аключ' in v['round']
        nums = [t['num'] for t in v['tasks']]
        assert len(nums) == len(set(nums)) >= 3
        for t in v['tasks']:
            assert t['text'] and t['solution']
    years = [v['year'] for v in vs]
    assert years == sorted(years, reverse=True), 'свежие годы первыми'


def _balanced(s: str) -> bool:
    return (s.count('\\(') == s.count('\\)') and s.count('\\[') == s.count('\\]')
            and s.count('{') == s.count('}') and s.count('$') % 2 == 0)


@pytest.mark.parametrize('grade', [7, 8, 9, 10, 11])
def test_latex_of_first_variants(svc, grade):
    """Формулы в выдаваемых вариантах (первые 3 — их увидит ученик) корректны."""
    for v in svc.candidate_variants('rosatom', grade, 'final')[:3]:
        for t in v['tasks']:
            for fld in ('text', 'solution', 'answer'):
                assert _balanced(t[fld]), (v['key'], t['num'], fld)
                assert not re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', t[fld]), (v['key'], t['num'])
            for f in t['fig_statement'] + t['fig_solution']:
                import os
                assert os.path.isfile(os.path.join('static', f.lstrip('/').split('static/', 1)[1])), f


def test_hours_text(svc):
    assert svc.hours_text(180) == '3 часа'
    assert svc.hours_text(240) == '4 часа'
    assert svc.hours_text(300) == '5 часов'
    assert svc.hours_text(150) == '2 часа 30 минут'


# ─── Поток ученика ────────────────────────────────────────────────────────

def _user(uid=4242, grade=10):
    from models import db, User
    from models_curator import CuratorState
    u = User(id=uid, email=f'pa{uid}@test.invalid', nickname=f'pa{uid}')
    db.session.add(u)
    db.session.add(CuratorState(user_id=uid, grade=grade))
    db.session.commit()
    return u


def test_dashboard_card_instead_of_rest(svc, client):
    u = _user()
    a = svc.assign(u.id, date.today(), slug='rosatom', stage='final')
    assert a.grade == 10 and '10 класс' in a.title and 'аключительный' in a.title
    _login(client, u.id)
    html = client.get('/daily_tasks', follow_redirects=True).get_data(as_text=True)
    data = json.loads(_DT_INIT_RE.search(html).group(1))
    assert data['status'] == 'probnik_assignment'
    assert 'По вашей просьбе выдали вам пробник Росатома' in html
    assert 'ИИ его разберёт' in html and 'У вас доступно 3 часа' in html
    assert 'Нажмите «Старт» — таймер запустится' in html
    assert 'точный процесс обучения' in html
    assert 'Сменить пробник' in html and 'Старт' in html
    assert 'Сегодня выходной — отдыхай' not in html


def test_swap_then_start_then_submit_and_review(svc, client):
    from models import db, CuratorChatMessage
    u = _user()
    a = svc.assign(u.id, date.today())
    first = a.variant_key
    _login(client, u.id)

    # до старта задачи скрыты от ученика
    page = client.get(f'/probnik-assign/{a.id}').get_data(as_text=True)
    assert 'Задача 1' not in page and 'Сменить пробник' in page

    # без CSRF — отказ
    assert client.post(f'/probnik-assign/{a.id}/swap').status_code == 403
    r = client.post(f'/probnik-assign/{a.id}/swap', headers=H).get_json()
    assert r['ok'] and a.variant_key != first

    r = client.post(f'/probnik-assign/{a.id}/start', headers=H).get_json()
    assert r['ok'] and a.status == 'started' and a.deadline_at > datetime.utcnow()
    assert not client.post(f'/probnik-assign/{a.id}/swap', headers=H).get_json()['ok']

    page = client.get(f'/probnik-assign/{a.id}').get_data(as_text=True)
    assert 'Задача 1' in page and 'Добавить фото решения' in page and 'Сдать работу' in page
    # официальное решение во время работы ученику не показываем
    assert 'Официальное решение' not in page

    n = len(svc.tasks_of(a))
    assert client.post(f'/probnik-assign/{a.id}/text', json={'idx': 0, 'text': 'x=2'},
                       headers=H).get_json()['ok']
    r = client.post(f'/probnik-assign/{a.id}/photo', headers=H,
                    data={'idx': '1', 'photo': (io.BytesIO(_png()), 'p.png', 'image/png')},
                    content_type='multipart/form-data').get_json()
    assert r['ok'], r
    ph = r['tasks'][1]['photos']
    assert len(ph) == 1 and ph[0]['ocr_status'] == 'ok' and 'x=2' in ph[0]['ocr_text']

    r = client.post(f'/probnik-assign/{a.id}/submit', headers=H).get_json()
    assert r['ok']
    db.session.refresh(a)
    assert a.status == 'reviewed'
    # две задачи с работой — по 5 баллов, остальные пустые — 0 без вызова ИИ
    assert svc._calls['grade'] == 2
    assert a.total_score == 10 and a.max_score == 7 * n
    assert 'План' in a.curator_review and 'ACTION' not in a.curator_review
    msg = CuratorChatMessage.query.filter_by(user_id=u.id, role='curator').all()
    assert msg and 'Разбор пробника' in msg[-1].content

    # баннер «куратор разобрал» → гаснет после открытия страницы
    assert svc.unseen_review(u.id).id == a.id
    page = client.get(f'/probnik-assign/{a.id}').get_data(as_text=True)
    assert f'{a.total_score} <span' in page and 'Официальное решение' in page
    assert svc.unseen_review(u.id) is None

    # после сдачи править нельзя
    assert client.post(f'/probnik-assign/{a.id}/text', json={'idx': 0, 'text': 'y'},
                       headers=H).status_code == 409


def test_auto_submit_on_timeout(svc, client):
    from models import db
    u = _user()
    a = svc.assign(u.id, date.today(), duration_minutes=60)
    svc.start(a)
    a.deadline_at = datetime.utcnow() - timedelta(minutes=1)
    db.session.commit()
    svc.sweep()
    db.session.refresh(a)
    assert a.status == 'reviewed' and a.auto_submitted and a.total_score == 0


def test_not_before_date_and_foreign_user(svc, client):
    u = _user()
    other = _user(uid=4343)
    a = svc.assign(u.id, date.today() + timedelta(days=2))
    _login(client, u.id)
    r = client.post(f'/probnik-assign/{a.id}/start', headers=H)
    assert r.status_code == 400
    _login(client, other.id)
    rv = client.get(f'/probnik-assign/{a.id}')
    assert rv.status_code == 404


def test_seed_mirror(svc, monkeypatch):
    from models import db, User
    from models_curator import CuratorState
    from models_probnik_assign import ProbnikAssignment as PA
    roman = User(id=777, email='r@test.invalid', nickname='roman_x', name='Роман Петров')
    lav = User(id=5, email='l@test.invalid', nickname='Lavrik')
    db.session.add_all([roman, lav, CuratorState(user_id=777, grade=8)])
    db.session.commit()
    monkeypatch.setattr('services.pilot.has_premium_access', lambda u: getattr(u, 'id', u) == 777)
    today = date.today()
    monkeypatch.setattr(svc, 'SEED', [
        {'key': 'roman', 'who': {'find_name': ['роман', 'roman']},
         'date': (today + timedelta(days=2)).isoformat(), 'slug': 'rosatom', 'stage': 'final'},
        {'key': 'lavrik', 'who': {'id': 5}, 'date': today.isoformat(),
         'slug': 'rosatom', 'stage': 'final', 'mirror': 'roman'},
    ])
    log = svc.ensure_seed()
    r = PA.query.filter_by(user_id=777).one()
    lv = PA.query.filter_by(user_id=5).one()
    assert r.grade == 8 and lv.variant_key == r.variant_key and lv.assigned_date == today, log
    assert svc.ensure_seed() == []   # идемпотентно
