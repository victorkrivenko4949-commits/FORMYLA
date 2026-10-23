# -*- coding: utf-8 -*-
"""Tests for tasks/prep_tasks.py -- scheduled prep cron jobs."""
import json
import pytest
from datetime import date, timedelta
from unittest.mock import patch

from models import db, PrepPlan, PrepDay, OlympiadPrep, User


@pytest.fixture(scope='module')
def app():
    from flask import Flask
    from flask_login import LoginManager

    test_app = Flask(__name__)
    test_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    test_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    test_app.config['TESTING'] = True
    test_app.config['SECRET_KEY'] = 'test-prep-tasks'

    db.init_app(test_app)
    login_manager = LoginManager(test_app)

    @login_manager.user_loader
    def load_user(uid):
        return db.session.get(User, int(uid))

    with test_app.app_context():
        db.create_all()

    yield test_app


@pytest.fixture(autouse=True)
def clean_db(app):
    with app.app_context():
        PrepDay.query.delete()
        PrepPlan.query.delete()
        OlympiadPrep.query.delete()
        User.query.delete()
        db.session.commit()
    yield


def _seed(app):
    with app.app_context():
        user = User(email='cron@test.com', name='CronUser')
        db.session.add(user)
        db.session.flush()

        oly = OlympiadPrep(
            slug='test-oly', name='Test Olympiad', short_name='TO',
            grades='[9]', stages='["Stage1"]', color_hex='#22d3a6',
        )
        db.session.add(oly)
        db.session.flush()

        today = date.today()
        plan = PrepPlan(
            user_id=user.id,
            olympiad_id=oly.id,
            target_stage='Stage1',
            start_date=today - timedelta(days=3),
            target_date=today + timedelta(days=27),
            baseline_radar=json.dumps(dict(algebra=50, geometry=50)),
            current_radar=json.dumps(dict(algebra=55, geometry=48)),
            daily_task_count=5,
            status='active',
            current_streak=0,
            longest_streak=0,
        )
        db.session.add(plan)
        db.session.flush()

        yesterday = today - timedelta(days=1)
        day_y = PrepDay(
            plan_id=plan.id, date=yesterday, status='today',
            target_topics=json.dumps(['algebra']),
            problem_ids=json.dumps([101, 102, 103]),
            completed_problem_ids=json.dumps([]),
            day_score=0,
        )
        db.session.add(day_y)

        day_t = PrepDay(
            plan_id=plan.id, date=today, status='upcoming',
            target_topics=json.dumps(['geometry']),
            problem_ids=json.dumps([201, 202]),
            completed_problem_ids=json.dumps([]),
            day_score=0,
        )
        db.session.add(day_t)

        db.session.commit()
        return dict(
            user_id=user.id, plan_id=plan.id,
            day_y_id=day_y.id, day_t_id=day_t.id,
        )


class TestDailyCron:

    def test_activates_today_days(self, app):
        ids = _seed(app)
        with app.app_context():
            from tasks.prep_tasks import daily_prep_cron
            result = daily_prep_cron()
            day_t = db.session.get(PrepDay, ids['day_t_id'])
            assert day_t.status == 'today'
            assert result['activated_today'] >= 1

    def test_closes_yesterday_missed(self, app):
        ids = _seed(app)
        with app.app_context():
            from tasks.prep_tasks import daily_prep_cron
            daily_prep_cron()
            day_y = db.session.get(PrepDay, ids['day_y_id'])
            assert day_y.status == 'missed'
            plan = db.session.get(PrepPlan, ids['plan_id'])
            assert plan.current_streak == 0

    def test_closes_yesterday_completed(self, app):
        ids = _seed(app)
        with app.app_context():
            day_y = db.session.get(PrepDay, ids['day_y_id'])
            day_y.completed_problem_ids = json.dumps([101, 102])
            day_y.day_score = 2
            plan = db.session.get(PrepPlan, ids['plan_id'])
            plan.current_streak = 5
            plan.longest_streak = 5
            db.session.commit()

            from tasks.prep_tasks import daily_prep_cron
            daily_prep_cron()

            day_y = db.session.get(PrepDay, ids['day_y_id'])
            assert day_y.status == 'completed'
            plan = db.session.get(PrepPlan, ids['plan_id'])
            assert plan.current_streak == 6
            assert plan.longest_streak == 6

    def test_breaks_streak_on_missed(self, app):
        ids = _seed(app)
        with app.app_context():
            plan = db.session.get(PrepPlan, ids['plan_id'])
            plan.current_streak = 10
            plan.longest_streak = 10
            db.session.commit()

            from tasks.prep_tasks import daily_prep_cron
            daily_prep_cron()

            plan = db.session.get(PrepPlan, ids['plan_id'])
            assert plan.current_streak == 0
            assert plan.longest_streak == 10

    def test_expires_overdue_plans(self, app):
        ids = _seed(app)
        with app.app_context():
            plan = db.session.get(PrepPlan, ids['plan_id'])
            plan.target_date = date.today() - timedelta(days=1)
            db.session.commit()

            from tasks.prep_tasks import daily_prep_cron
            result = daily_prep_cron()

            plan = db.session.get(PrepPlan, ids['plan_id'])
            assert plan.status == 'completed'
            assert result['expired'] >= 1


class TestWeeklyReview:

    @patch('services.prep_planner.recompute_plan')
    def test_recomputes_active_plans(self, mock_recompute, app):
        ids = _seed(app)
        with app.app_context():
            from tasks.prep_tasks import weekly_prep_review
            result = weekly_prep_review()
            assert result['reviewed'] >= 1
            mock_recompute.assert_called()


class TestStreakRescue:

    def test_no_warn_if_already_solved(self, app):
        ids = _seed(app)
        with app.app_context():
            plan = db.session.get(PrepPlan, ids['plan_id'])
            plan.current_streak = 5
            day_t = db.session.get(PrepDay, ids['day_t_id'])
            day_t.status = 'today'
            day_t.completed_problem_ids = json.dumps([201])
            db.session.commit()

            from tasks.prep_tasks import streak_rescue_cron
            result = streak_rescue_cron()
            assert result['warned'] == 0

    def test_no_warn_if_streak_low(self, app):
        ids = _seed(app)
        with app.app_context():
            plan = db.session.get(PrepPlan, ids['plan_id'])
            plan.current_streak = 1
            day_t = db.session.get(PrepDay, ids['day_t_id'])
            day_t.status = 'today'
            day_t.completed_problem_ids = json.dumps([])
            db.session.commit()

            from tasks.prep_tasks import streak_rescue_cron
            result = streak_rescue_cron()
            assert result['warned'] == 0
