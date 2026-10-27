# -*- coding: utf-8 -*-
"""REAL_PROBNIK_V1 — маршрутные проверки (ревью 28.10.2026, раунд 3).

Не изолированные вызовы функций, а НАСТОЯЩИЕ Flask-маршруты через
test_client реального приложения (как tests/test_session_plan_routes.py):
пробник открывается по своему коду, стартует, чертежи каталога отдаются
на странице задачи, сдача завершает занятие-пробник, двухдневные варианты
идут без таймера, а занятие без назначенного кода чужой сдачей НЕ
закрывается (никаких подмен). Параллельные комплекты (разбивка по
документам) не подмешивают чужие чертежи на страницу задания.

Run: pytest tests/test_real_probnik_routes.py -v
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest


def _setup_user(user_id: int, with_prep: bool, grade: int = 9,
                slug: str = 'vsosh') -> int:
    """Пилот с (или без) prep-планом vsosh; 5 закрытых практик за прошлые дни.

    Возвращает ФАКТИЧЕСКИЙ id юзера (может отличаться от запрошенного, если
    тестовый юзер уже существует с другим id — база между прогонами общая)."""
    from app import app
    from models import db, OlympiadPrep, PrepPlan, User
    from models_curator import CuratorState
    from sqlalchemy import text
    from curator.session_plan import ensure_tables

    with app.app_context():
        u = User.query.get(user_id)
        if not u:
            # идемпотентно между прогонами (email может остаться с прошлого):
            u = User.query.filter_by(email=f'rp{user_id}@test.local').first()
        if not u:
            u = User(id=user_id, email=f'rp{user_id}@test.local')
            db.session.add(u)
            db.session.flush()
        uid = u.id  # фактический id может отличаться от запрошенного
        cs = CuratorState.query.filter_by(user_id=uid).first()
        if cs is None:
            cs = CuratorState(user_id=uid)
            db.session.add(cs)
            db.session.flush()
        cs.grade = grade
        cs.prep_state = json.dumps({'intake': {'completed': True}})
        # локальная база при старте приложения сеет активные premium-подписки
        # тестовым юзерам — вычищаем, чтобы не попадать в «неделю диагностики»
        db.session.execute(text(
            "DELETE FROM subscriptions WHERE user_id = :uid"), {'uid': uid})
        if with_prep:
            db.session.execute(text(
                'DELETE FROM prep_plans WHERE user_id = :uid'), {'uid': uid})
            op = OlympiadPrep.query.filter_by(slug=slug).first()
            if not op:
                op = OlympiadPrep(slug='vsosh', name='ВсОШ', short_name='ВсОШ')
                db.session.add(op)
                db.session.flush()
            db.session.add(PrepPlan(
                user_id=uid, olympiad_id=op.id,
                start_date=date.today() - timedelta(days=6),
                target_date=date.today() + timedelta(days=180)))
        db.session.commit()
        ensure_tables()
        db.session.execute(text(
            'DELETE FROM curator_lessons WHERE user_id = :uid'), {'uid': uid})
        # 5 закрытых практик: сегодня создаётся занятие слота 6 — ПРОБНИК
        for i in range(1, 6):
            db.session.execute(text(
                "INSERT INTO curator_lessons (user_id, seq, lesson_type, "
                "status, assigned_date) VALUES (:uid, :seq, 'practice', "
                "'completed', :d)"),
                {'uid': uid, 'seq': i,
                 'd': date.today() - timedelta(days=6 - i)})
        db.session.commit()
        return uid


@pytest.fixture()
def prep_client():
    """Пилот с prep-планом vsosh (9 класс), залогинен через dev_login."""
    uid = _setup_user(1, with_prep=True)
    from app import app
    with app.test_client() as c:
        rv = c.get(f'/dev_login?uid={uid}')
        assert rv.status_code in (200, 302), (rv.status_code, rv.data[:200])
        c.uid = uid
        yield c


@pytest.fixture()
def noplan_client():
    """Пилот с prep-планом по олимпиаде, которой НЕТ в каталоге задач
    (itmo): занятие-пробник создаётся БЕЗ кода — подмен быть не должно."""
    uid = _setup_user(7452, with_prep=True, slug='itmo')
    from app import app
    with app.test_client() as c:
        rv = c.get(f'/dev_login?uid={uid}')
        assert rv.status_code in (200, 302), (rv.status_code, rv.data[:200])
        c.uid = uid
        yield c


def test_real_probnik_full_flow(prep_client):
    """Неделя -> пробник открывается по коду, сдача закрывает занятие."""
    from app import app
    from models import db
    from curator import session_plan

    # 1) дашборд создаёт занятие-пробник и ведёт на реальный вариант
    rv = prep_client.get('/daily_tasks')
    assert rv.status_code == 200, rv.status_code
    html = rv.get_data(as_text=True)
    # код всегда содержит тег названия (ревю 28.10.2026):
    # real-vsosh-2025-school<тег>-g9 — проверяем по частям
    assert 'real-vsosh-' in html and '-school' in html and '-g9' in html, html[:500]

    with app.app_context():
        lesson = session_plan._current_assigned(prep_client.uid)
        assert lesson is not None and lesson['lesson_type'] == 'probnik'
        code = lesson['probnik_code']
        assert code and code.startswith('real-vsosh-')

    # 2) страница пробника открывается по коду: задачи каталога на месте
    rv = prep_client.get(f'/olympiads/probnik/{code}')
    assert rv.status_code == 200, rv.status_code
    html = rv.get_data(as_text=True)
    assert 'Реальный вариант олимпиады' in html
    assert 'olymp-tasks' in html or 'task' in html

    # 3) старт -> активная страница: таймер школьного этапа ВсОШ (120 мин)
    rv = prep_client.post(f'/olympiads/probnik/{code}/start')
    assert rv.status_code == 302, rv.status_code
    rv = prep_client.get(f'/olympiads/probnik/{code}/active')
    assert rv.status_code == 200, rv.status_code
    html = rv.get_data(as_text=True)
    assert 'durationMinutes: 120' in html, html[:800]
    assert 'Сдать' in html

    # 4) страница задачи: чертежи каталога отдаются с корректным URL
    with app.app_context():
        from models_olympiad import OlympiadTask, Probnik
        from services.real_probnik import figures_for_task
        p = Probnik.query.filter_by(code=code).first()
        assert p is not None
        fig_task = None
        for t in OlympiadTask.query.filter_by(probnik_id=p.id).all():
            if figures_for_task(code, t.number).get('condition'):
                fig_task = t
                break

    # NB: HTTP-запросы НИКОГДА не делаем внутри `with app.app_context():` —
    # Flask-тест-клиент сам пушит/попает app-контексты, и вложенный pop
    # ломает контекстный стек («Popped wrong app context").
    if fig_task is not None:  # у варианта есть задачи с чертежами
        rv = prep_client.get(f'/olympiads/task/{fig_task.id}')
        assert rv.status_code == 200, rv.status_code
        thtml = rv.get_data(as_text=True)
        assert '/static/olymp_figures/' in thtml
        assert "openOnBoard('/static/olymp_figures/" in thtml
        # чертёж РЕАЛЬНО отдаётся: GET файла -> 200 + картинка
        import re as _re
        m = _re.search(r"openOnBoard\('(/static/olymp_figures/[^']+)'\)", thtml)
        assert m, thtml[:300]
        fig_rv = prep_client.get(m.group(1))
        assert fig_rv.status_code == 200, (m.group(1), fig_rv.status_code)
        assert (fig_rv.content_type or '').startswith('image/'), \
            fig_rv.content_type

    # 5) сдача пробника завершает занятие-пробник (маршрут + хук)
    rv = prep_client.post(f'/olympiads/probnik/{code}/submit', json={
        'total_score': 10, 'task_scores': {}, 'result': 'participant'})
    assert rv.status_code == 200, rv.status_code
    data = rv.get_json()
    assert data.get('ok') is True
    with app.app_context():
        lesson = session_plan._current_assigned(prep_client.uid)
        assert lesson is None or lesson['lesson_type'] != 'probnik', \
            'занятие-пробник должно закрыться сдачей назначенного варианта'


def test_untimed_variant_no_timer(prep_client):
    """Двухдневный (региональный) и не-ВсОШ варианты — без таймера."""
    from app import app
    from models import db
    from models_olympiad import Probnik
    from services.real_probnik import ensure_real_probnik

    with app.app_context():
        from services.real_probnik import variant_codes
        # региональный этап 2025, 9 класс — двухдневный; код — из
        # генератора (объекты ordered_variants пересоздаются при каждом
        # вызове, сравниваем по содержимому, а не по identity)
        reg = [(c, v) for c, v in variant_codes('vsosh', 9)
               if v['year'] == 2025 and 'егион' in v['round']]
        if not reg:
            pytest.skip('нет регионального варианта в каталоге')
        code, reg_v = reg[0]
        made = ensure_real_probnik(code, reg_v, 'vsosh')
        db.session.commit()
        assert made is not None
        rp = Probnik.query.filter_by(code=code).first()
        assert rp.duration_minutes is None  # двухдневный — без выдуманного таймера
    rv = prep_client.post(f'/olympiads/probnik/{code}/start')
    assert rv.status_code == 302, rv.status_code
    rv = prep_client.get(f'/olympiads/probnik/{code}/active')
    assert rv.status_code == 200, rv.status_code
    html = rv.get_data(as_text=True)
    assert 'durationMinutes: null' in html, html[:800]
    # кнопка сдачи доступна и без таймера
    assert 'Сдать' in html


def test_no_code_probnik_not_completed_by_foreign_submit(noplan_client):
    """Пробник без назначенного кода НЕ закрывается чужой сдачей (без подмен)."""
    from app import app
    from curator import session_plan

    # дашборд создаёт занятие-пробник без кода (олимпиада не выбрана)
    rv = noplan_client.get('/daily_tasks')
    assert rv.status_code == 200, rv.status_code
    with app.app_context():
        lesson = session_plan._current_assigned(noplan_client.uid)
        assert lesson is not None and lesson['lesson_type'] == 'probnik'
        assert not lesson['probnik_code'], lesson

    # сдача чужого реального пробника НЕ закрывает занятие без кода.
    # «Чужой» создаём сами (не полагаемся на другие тесты/состояние базы):
    from services.real_probnik import variant_codes, ensure_real_probnik
    from models import db
    with app.app_context():
        foreign_code, foreign_variant = variant_codes('vsosh', 9)[0]
        ensure_real_probnik(foreign_code, foreign_variant, 'vsosh')
        db.session.commit()
    rv = noplan_client.post(f'/olympiads/probnik/{foreign_code}/start')
    assert rv.status_code == 302, rv.status_code
    rv = noplan_client.post(
        f'/olympiads/probnik/{foreign_code}/submit', json={
            'total_score': 0, 'task_scores': {}, 'result': 'participant'})
    assert rv.status_code == 200, rv.status_code
    with app.app_context():
        lesson = session_plan._current_assigned(noplan_client.uid)
        assert lesson is not None and lesson['lesson_type'] == 'probnik'
        assert lesson['status'] == 'assigned', \
            'занятие без назначенного кода не должно закрываться чужой сдачей'

def test_parallel_variant_figures_isolated(prep_client):
    """Параллельные комплекты (doc-split): страница задания через МАРШРУТ.

    Вариант A из разбивки по документам: чертёж A рендерится (img src),
    файл отдаётся 200; чертёж ПАРАЛЛЕЛЬНОГО комплекта B с тем же номером
    задачи на страницу A не попадает (ревью 28.10.2026, раунд 6).
    """
    import os
    from app import app
    from models import db
    from models_olympiad import OlympiadTask
    import services.real_probnik as rp
    from services.real_probnik import ensure_real_probnik, variant_codes

    # два РЕАЛЬНО существующих файла чертежей каталога
    figs_exist = []
    with app.app_context():
        for t in rp._load_catalog('vsosh'):
            for f in (t.get('fig_statement') or []):
                path = os.path.join('static', 'olymp_figures', f)
                if os.path.isfile(path) and f not in figs_exist:
                    figs_exist.append(f)
                if len(figs_exist) >= 2:
                    break
            if len(figs_exist) >= 2:
                break
    assert len(figs_exist) >= 2, 'нужно два существующих чертежа каталога'
    fig_a, fig_b = figs_exist[0], figs_exist[1]

    # синтетический каталог: два параллельных комплекта (одни и те же
    # номера, разные uid/документы) — как «Ломоносов»-2023
    def _synth():
        out = []
        for doc, tag, fig in (('a.pdf', 'A', fig_a), ('b.pdf', 'B', fig_b)):
            for num in (1, 2, 3):
                out.append({
                    'uid': f'route-syn-{tag}-{num}', 'year': 2024,
                    'round': 'Финал', 'grade': '9', 'num': num,
                    'source': f'https://example.org/{doc}',
                    'text': f'Условие {tag}{num}', 'solution': '',
                    'fig_statement': ([fig] if num == 2 else []),
                })
        return out

    orig_load = rp._load_catalog
    rp._load_catalog = lambda slug: _synth() if slug == 'synthetic' else \
        orig_load(slug)
    task_id = None
    try:
        with app.app_context():
            pairs = variant_codes('synthetic', 9)
            assert len(pairs) == 2, pairs
            code_a, v_a = next(
                (c, v) for c, v in pairs
                if any('A2' in (t.get('text') or '') for t in v['tasks']))
            made = ensure_real_probnik(code_a, v_a, 'synthetic')
            db.session.commit()
            assert made is not None
            p = made if hasattr(made, 'id') else None
            from models_olympiad import Probnik
            p_a = Probnik.query.filter_by(code=code_a).first()
            assert p_a is not None
            t2 = next(t for t in OlympiadTask.query.filter_by(
                probnik_id=p_a.id).all() if t.number == '2')
            task_id = t2.id
            url_a = f'/static/olymp_figures/{fig_a}'
            url_b = f'/static/olymp_figures/{fig_b}'

        # страница задания через НАСТОЯЩИЙ маршрут
        rv = prep_client.get(f'/olympiads/task/{task_id}')
        assert rv.status_code == 200, rv.status_code
        html = rv.get_data(as_text=True)
        # чертёж A рендерится именно как <img src=...> (не только в
        # обработчике кнопки; ревю 28.10.2026, раунд 7)
        import re as _re2
        img_srcs = _re2.findall(r'<img[^>]+src="([^"]+)"', html)
        assert url_a in img_srcs, img_srcs[:10]
        # чертёж параллельного комплекта B с тем же номером НЕ подмешан
        assert url_b not in html and url_b not in img_srcs, img_srcs[:10]
        # файл чертежа РЕАЛЬНО отдаётся
        fig_rv = prep_client.get(url_a)
        assert fig_rv.status_code == 200, (url_a, fig_rv.status_code)
        assert (fig_rv.content_type or '').startswith('image/')
    finally:
        rp._load_catalog = orig_load
