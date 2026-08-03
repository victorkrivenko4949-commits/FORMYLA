# -*- coding: utf-8 -*-
"""
Integration tests for routes/prep.py

Uses in-memory SQLite via Flask-SQLAlchemy + test client.
8 tests covering CRUD, validation, authorization, cascading.
"""

import json
import pytest
from datetime import date, timedelta

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from flask_login import LoginManager, login_user
from models import db as _db, User, AdaptiveTask, OlympiadPrep, PrepPlan, PrepDay
from routes.prep import prep_bp


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def app():
    """Create a Flask app with in-memory SQLite for testing."""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TESTING'] = True
    app.secret_key = 'test-secret'

    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return _db.session.get(User, int(user_id))

    # Register blueprint
    app.register_blueprint(prep_bp)

    _db.init_app(app)
    with app.app_context():
        _db.create_all()
        _seed_test_data()
    yield app


@pytest.fixture(autouse=True)
def app_context(app):
    with app.app_context():
        yield


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(app, client):
    """Client logged in as test user."""
    with client.session_transaction() as sess:
        # Flask-Login stores user_id in session
        sess['_user_id'] = '1'
        sess['_fresh'] = True
    return client


@pytest.fixture
def other_client(app, client):
    """Client logged in as another user."""
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['_user_id'] = '2'
            sess['_fresh'] = True
        yield c


def _seed_test_data():
    """Seed: 2 users, 1 olympiad, ~100 tasks."""
    u1 = User(id=1, email='user1@test.ru', name='User 1', preferred_grade=9)
    u2 = User(id=2, email='user2@test.ru', name='User 2', preferred_grade=10)
    _db.session.add_all([u1, u2])

    o = OlympiadPrep(
        id=1, slug='vsosh', name='ВсОШ', short_name='ВсОШ',
        description='Test', grades='[5,6,7,8,9,10,11]',
        stages='[{"name":"Школьный","date_range":"Октябрь"},{"name":"Муниципальный","date_range":"Ноябрь"}]',
        official_url='https://test.ru', color_hex='#22d3a6',
        sort_order=1, is_active=True,
    )
    _db.session.add(o)

    # Tasks
    topics = [
        'Системы уравнений', 'Геометрия: окружность', 'Комбинаторика',
        'Теория чисел', 'Задачи на движение', 'Рыцари и лжецы',
    ]
    tid = 1
    for topic in topics:
        for grade in [8, 9, 10]:
            for diff in range(1, 6):
                for _ in range(3):
                    t = AdaptiveTask(
                        id=tid, class_level=grade, difficulty_level=diff,
                        topic=topic, task_text=f'Task {tid}',
                        solution=f'Sol {tid}', criteria_1_point='1p',
                        criteria_2_points='2p', correct_answer=str(tid),
                        is_flagged=False,
                    )
                    _db.session.add(t)
                    tid += 1

    _db.session.commit()


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestCreatePlan:

    def test_create_plan_success(self, auth_client):
        """POST /prep/new -> 201, plan created."""
        resp = auth_client.post('/prep/new', json={
            'olympiad_slug': 'vsosh',
            'target_stage': 'Муниципальный',
            'target_date': (date.today() + timedelta(days=30)).isoformat(),
            'use_baseline': 'radar',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'plan_id' in data
        assert data['days_total'] == 30
        assert data['redirect_url'] == f"/prep/{data['plan_id']}"

    def test_create_plan_duplicate_conflict(self, auth_client):
        """Duplicate plan for same olympiad+stage -> 409."""
        # First plan already created in previous test
        resp = auth_client.post('/prep/new', json={
            'olympiad_slug': 'vsosh',
            'target_stage': 'Муниципальный',
            'target_date': (date.today() + timedelta(days=60)).isoformat(),
            'use_baseline': 'radar',
        })
        assert resp.status_code == 409

    def test_create_plan_no_adaptive_test(self, auth_client):
        """use_baseline=adaptive_test without test -> 400."""
        resp = auth_client.post('/prep/new', json={
            'olympiad_slug': 'vsosh',
            'target_stage': 'Школьный',
            'target_date': (date.today() + timedelta(days=30)).isoformat(),
            'use_baseline': 'adaptive_test',
        })
        assert resp.status_code == 400
        assert 'адаптивный тест' in resp.get_json()['error'].lower()


class TestPlanAccess:

    def test_get_plan_detail_success(self, auth_client):
        """GET /prep/<id>?format=json -> plan details."""
        plan = PrepPlan.query.filter_by(user_id=1).first()
        assert plan is not None
        resp = auth_client.get(f'/prep/{plan.id}?format=json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['plan']['id'] == plan.id
        assert len(data['days']) > 0

    def test_get_plan_detail_forbidden(self, other_client):
        """GET /prep/<id> for another user's plan -> 403."""
        plan = PrepPlan.query.filter_by(user_id=1).first()
        resp = other_client.get(f'/prep/{plan.id}?format=json')
        assert resp.status_code == 403


class TestTodayProblems:

    def test_today_returns_problems(self, auth_client):
        """GET /prep/<id>/today?format=json -> problems for today."""
        plan = PrepPlan.query.filter_by(user_id=1).first()
        resp = auth_client.get(f'/prep/{plan.id}/today?format=json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'problems' in data
        assert len(data['problems']) > 0
        assert data['date'] == date.today().isoformat()


class TestCompleteProblem:

    def test_complete_problem_updates_radar(self, auth_client):
        """POST complete -> radar updated."""
        plan = PrepPlan.query.filter_by(user_id=1).first()
        old_radar = json.loads(plan.current_radar)

        # Get today's problems
        resp = auth_client.get(f'/prep/{plan.id}/today?format=json')
        data = resp.get_json()
        problem_id = data['problems'][0]['id']

        # Complete it
        resp = auth_client.post(
            f'/prep/{plan.id}/today/complete/{problem_id}',
            json={'is_correct': True, 'user_answer': '42'},
        )
        assert resp.status_code == 200
        result = resp.get_json()
        assert result['status'] == 'ok'
        assert result['day_score'] >= 1

    def test_complete_all_problems_marks_day_completed(self, auth_client):
        """After completing all problems -> day status=completed."""
        plan = PrepPlan.query.filter_by(user_id=1).first()

        # Get today's problems
        resp = auth_client.get(f'/prep/{plan.id}/today?format=json')
        data = resp.get_json()

        # Complete all problems
        for p in data['problems']:
            auth_client.post(
                f'/prep/{plan.id}/today/complete/{p["id"]}',
                json={'is_correct': True},
            )

        # Check day status
        today_day = PrepDay.query.filter_by(plan_id=plan.id, date=date.today()).first()
        assert today_day.status == 'completed'


class TestDeletePlan:

    def test_delete_plan_cascades_days(self, auth_client):
        """DELETE /prep/<id> -> plan and all days deleted."""
        # Create a new plan to delete
        resp = auth_client.post('/prep/new', json={
            'olympiad_slug': 'vsosh',
            'target_stage': 'Школьный',
            'target_date': (date.today() + timedelta(days=14)).isoformat(),
            'use_baseline': 'radar',
        })
        plan_id = resp.get_json()['plan_id']

        # Verify days exist
        days_count = PrepDay.query.filter_by(plan_id=plan_id).count()
        assert days_count > 0

        # Delete
        resp = auth_client.delete(f'/prep/{plan_id}')
        assert resp.status_code == 204

        # Verify cascade
        assert PrepPlan.query.get(plan_id) is None
        assert PrepDay.query.filter_by(plan_id=plan_id).count() == 0
