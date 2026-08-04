# -*- coding: utf-8 -*-
"""
Integration tests for routes/olympiad.py (`/olympiads/*`).

We use a self-contained Flask test app with in-memory SQLite, register the
olympiad blueprint, seed minimal data, and hit each endpoint.

Covers:
  * GET catalog, course, probnik, task, methods, method_detail, my_progress.
  * POST task attempt: создаёт TaskAttempt + обновляет статус/самооценку.
  * POST stage start + submit: создаёт StageAttempt, считает total_score
    и сохраняет result в зависимости от порогов.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from flask import Flask
from flask_login import LoginManager

from models import (
    db as _db,
    User,
    Probnik,
    OlympiadTask,
    TheoryBlock,
    TaskAttempt,
    StageAttempt,
)
from routes.olympiad import olympiad_bp
from services.md_render import md_render


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def app():
    app = Flask(
        __name__,
        template_folder=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'templates',
        ),
        static_folder=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'static',
        ),
    )
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.secret_key = 'test-secret'

    # Минимальный asset_version для шаблонов base.html.
    @app.context_processor
    def _ctx():
        return {'asset_version': 'test'}

    # Jinja-фильтры (md_render + inject_geometry — оба используются в шаблонах
    # olympiad/method.html, иначе TemplateRuntimeError).
    app.jinja_env.filters['md_render'] = md_render
    try:
        from services.geometry_drawings import inject_geometry_drawings
        app.jinja_env.filters['inject_geometry'] = inject_geometry_drawings
    except Exception:
        # Тест может работать без чертежей — фолбэк: identity-фильтр.
        app.jinja_env.filters['inject_geometry'] = lambda s, _code=None: s

    # Flask-Login.
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def _load_user(uid):
        return _db.session.get(User, int(uid))

    # Регистрируем blueprint.
    app.register_blueprint(olympiad_bp)

    # Также «фиктивные» эндпоинты, на которые ссылаются шаблоны base.html
    # (login, logout, leaderboard, daily_quest_main, olympiads, …) —
    # делаем noop-handlers, чтобы url_for(...) не падал.
    for name in (
        'index', 'login', 'logout', 'leaderboard', 'daily_quest_main',
        'olympiads', 'profile', 'secrets', 'subscribe_page',
        'olympiad_prep', 'olympiad_prep.dashboard',
        # base.html ссылается на эти эндпоинты — добавляем стабы, чтобы
        # url_for() в шапке не валил тесты с BuildError.
        'olympiad_prep.calendar', 'olympiad_prep.index',
        'olympiad_prep.detail',
    ):
        # add_url_rule вместе с endpoint-name; для blueprint-стиля 'a.b'
        # достаточно простой функции, имя URL — уникально.
        try:
            app.add_url_rule(f'/_stub_{name.replace(".","_")}', name,
                             lambda: '', methods=['GET'])
        except Exception:
            pass

    _db.init_app(app)
    with app.app_context():
        _db.create_all()
        _seed()
    yield app


def _seed():
    u = User(id=1, email='u1@test.ru', name='U1', preferred_grade=9)
    _db.session.add(u)

    # Theory blocks.
    tb1 = TheoryBlock(method_code='E14', method_name='Индукция', section='E',
                      definition_md='Опр.', related_methods=['F4a'])
    tb2 = TheoryBlock(method_code='F4a', method_name='Дирихле', section='F',
                      definition_md='Опр.')
    _db.session.add_all([tb1, tb2])

    # Probniks.
    p_topic = Probnik(
        id=1, code='vsosh-9-2027-topic-1', type='topic', number=1,
        title='Topic 1', description='Topic descr',
    )
    p_stage = Probnik(
        id=2, code='vsosh-9-2027-stage-1', type='stage', number=1,
        title='Stage 1',
        duration_minutes=180, max_score=21,
        threshold_prize=10, threshold_winner=15,
    )
    _db.session.add_all([p_topic, p_stage])
    _db.session.flush()

    # Tasks.
    t1 = OlympiadTask(
        id=101, probnik_id=p_topic.id, number='1.1', sort_order=1,
        method_primary='E14',
        condition_md='Cond 1.1', idea_md='Idea 1.1', solution_md='Sol 1.1',
        answer='42',
    )
    t2 = OlympiadTask(
        id=102, probnik_id=p_topic.id, number='1.2', sort_order=2,
        method_primary='F4a',
        condition_md='Cond 1.2', idea_md='Idea 1.2', solution_md='Sol 1.2',
    )
    s1 = OlympiadTask(
        id=201, probnik_id=p_stage.id, number='Э1.1', sort_order=1,
        method_primary='E14',
        condition_md='SC 1', idea_md='SI 1', solution_md='SS 1',
    )
    s2 = OlympiadTask(
        id=202, probnik_id=p_stage.id, number='Э1.2', sort_order=2,
        method_primary='F4a',
        condition_md='SC 2', idea_md='SI 2', solution_md='SS 2',
    )
    s3 = OlympiadTask(
        id=203, probnik_id=p_stage.id, number='Э1.3', sort_order=3,
        method_primary='E14',
        condition_md='SC 3', idea_md='SI 3', solution_md='SS 3',
    )
    _db.session.add_all([t1, t2, s1, s2, s3])
    _db.session.commit()


@pytest.fixture(autouse=True)
def app_context(app):
    with app.app_context():
        yield


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(app, client):
    """Test client authenticated as user_id=1."""
    with client.session_transaction() as sess:
        sess['_user_id'] = '1'
        sess['_fresh'] = True
    return client


# ─── GET endpoints ────────────────────────────────────────────────────────────

    assert b'1.1' in r.data
    assert b'1.2' in r.data


def test_probnik_404(client):
    r = client.get('/olympiads/probnik/nope-nope')
    assert r.status_code == 404


def test_task_page(client):
    r = client.get('/olympiads/task/101')
    assert r.status_code == 200
    assert b'Cond 1.1' in r.data


def test_methods_catalog(client):
    r = client.get('/olympiads/methods')
    assert r.status_code == 200
    assert b'E14' in r.data
    assert b'F4a' in r.data


def test_method_detail(client):
    r = client.get('/olympiads/methods/E14')
    assert r.status_code == 200
    assert 'Индукция'.encode('utf-8') in r.data


def test_method_detail_404(client):
    r = client.get('/olympiads/methods/UNKNOWN')
    assert r.status_code == 404


# ─── POST: task attempt ───────────────────────────────────────────────────────

def test_task_attempt_requires_login(client):
    r = client.post('/olympiads/task/101/attempt',
                    json={'status': 'attempted'})
    # login_required -> redirect 302 (или 401 если настроено).
    assert r.status_code in (302, 401)


def test_task_attempt_create_and_update(auth_client):
    # 1) Создаём attempt.
    r = auth_client.post(
        '/olympiads/task/101/attempt',
        json={'status': 'attempted', 'self_score': 5, 'note': 'first try'},
    )
    assert r.status_code == 200
    j = r.get_json()
    assert j['ok'] is True
    assert j['attempt']['status'] == 'attempted'
    assert j['attempt']['self_score'] == 5

    # 2) Тот же task -> обновление, без новой строки.
    r2 = auth_client.post(
        '/olympiads/task/101/attempt',
        json={'status': 'solved', 'self_score': 7, 'note': 'got it'},
    )
    assert r2.status_code == 200
    assert r2.get_json()['attempt']['status'] == 'solved'
    assert r2.get_json()['attempt']['self_score'] == 7

    count = TaskAttempt.query.filter_by(user_id=1, task_id=101).count()
    assert count == 1


def test_task_attempt_invalid_status(auth_client):
    r = auth_client.post(
        '/olympiads/task/102/attempt',
        json={'status': 'BOGUS'},
    )
    assert r.status_code == 400


def test_task_attempt_invalid_self_score(auth_client):
    r = auth_client.post(
        '/olympiads/task/102/attempt',
        json={'status': 'attempted', 'self_score': 99},
    )
    assert r.status_code == 400


# ─── POST: stage start/submit ─────────────────────────────────────────────────

def test_stage_start_requires_login(client):
    r = client.post('/olympiads/stage/vsosh-9-2027-stage-1/start')
    assert r.status_code in (302, 401)


def test_stage_start_rejects_topic_probnik(auth_client):
    r = auth_client.post(
        '/olympiads/stage/vsosh-9-2027-topic-1/start',
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    assert r.status_code == 400
    assert r.get_json()['error'] == 'not_a_stage_probnik'


def test_stage_start_creates_attempt(auth_client):
    r = auth_client.post(
        '/olympiads/stage/vsosh-9-2027-stage-1/start',
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    assert r.status_code == 200
    j = r.get_json()
    assert j['ok'] is True
    assert j['duration_minutes'] == 180
    attempt_id = j['attempt_id']
    assert StageAttempt.query.get(attempt_id) is not None


def test_stage_submit_computes_total_and_result(auth_client):
    # 1) Start.
    r = auth_client.post(
        '/olympiads/stage/vsosh-9-2027-stage-1/start',
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    attempt_id = r.get_json()['attempt_id']

    # 2) Submit с оценками 7+7+1 = 15 -> пороги: prize=10, winner=15 -> winner.
    r2 = auth_client.post(
        '/olympiads/stage/vsosh-9-2027-stage-1/submit',
        json={
            'attempt_id': attempt_id,
            'scores': {'Э1.1': 7, 'Э1.2': 7, 'Э1.3': 1},
        },
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    assert r2.status_code == 200
    j = r2.get_json()
    assert j['total_score'] == 15
    assert j['result'] == 'winner'

    a = StageAttempt.query.get(attempt_id)
    assert a.finished_at is not None
    assert a.task_scores == {'Э1.1': 7, 'Э1.2': 7, 'Э1.3': 1}


def test_stage_submit_double_finalize_blocked(auth_client):
    # Start + submit + submit again -> 409.
    r = auth_client.post(
        '/olympiads/stage/vsosh-9-2027-stage-1/start',
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    attempt_id = r.get_json()['attempt_id']

    r2 = auth_client.post(
        '/olympiads/stage/vsosh-9-2027-stage-1/submit',
        json={'attempt_id': attempt_id, 'scores': {}},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    assert r2.status_code == 200

    r3 = auth_client.post(
        '/olympiads/stage/vsosh-9-2027-stage-1/submit',
        json={'attempt_id': attempt_id, 'scores': {}},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    assert r3.status_code == 409
