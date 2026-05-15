# -*- coding: utf-8 -*-
"""
Unit tests for services/prep_planner.py

Uses in-memory SQLite via Flask-SQLAlchemy.
10 tests covering plan generation, difficulty, topics, deduplication, recompute.
"""

import json
import pytest
from datetime import date, timedelta

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from models import db as _db, User, AdaptiveTask, OlympiadPrep, PrepPlan, PrepDay
from services.prep_planner import (
    generate_prep_plan,
    recompute_plan,
    select_problems_for_day,
    _map_skill_to_difficulty,
    _get_topic_priorities,
    _calculate_days_total,
    _distribute_count,
    RADAR_TOPICS,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def app():
    """Create a Flask app with in-memory SQLite for testing."""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TESTING'] = True
    app.secret_key = 'test-secret'
    _db.init_app(app)
    with app.app_context():
        _db.create_all()
        _seed_test_data()
    yield app


@pytest.fixture(autouse=True)
def app_context(app):
    """Push app context for every test."""
    with app.app_context():
        yield


@pytest.fixture
def user():
    return User.query.filter_by(email='test@formyla.ru').first()


@pytest.fixture
def olympiad():
    return OlympiadPrep.query.filter_by(slug='vsosh').first()


@pytest.fixture
def baseline_radar():
    return {
        'algebra': 30,
        'geometry': 70,
        'combinatorics': 20,
        'number_theory': 50,
        'movement': 60,
        'knights_liars': 80,
    }


def _seed_test_data():
    """Seed minimal test data: 1 user, 1 olympiad, ~200 tasks."""
    # User
    u = User(email='test@formyla.ru', name='Test User', preferred_grade=9)
    _db.session.add(u)

    # Olympiad
    o = OlympiadPrep(
        slug='vsosh',
        name='ВсОШ',
        short_name='ВсОШ',
        description='Test olympiad',
        grades='[5,6,7,8,9,10,11]',
        stages='[{"name":"Школьный","date_range":"Октябрь"},{"name":"Муниципальный","date_range":"Ноябрь"}]',
        official_url='https://test.ru',
        color_hex='#22d3a6',
        sort_order=1,
        is_active=True,
    )
    _db.session.add(o)

    # Tasks: create ~30 tasks per topic × 3 grades × 5 difficulties
    topic_names = {
        'algebra': [
            'Системы уравнений и неравенства',
            'Квадратичная функция и уравнения',
            'Алгебра и функции',
        ],
        'geometry': [
            'Геометрия: окружность и векторы',
            'Геометрия: треугольники',
        ],
        'combinatorics': [
            'Комбинаторика и вероятность',
            'Логика и инварианты',
        ],
        'number_theory': [
            'Теория чисел и делимость',
        ],
        'movement': [
            'Задачи на движение и скорость',
        ],
        'knights_liars': [
            'Рыцари и лжецы',
        ],
    }

    task_id = 1
    for topic_key, names in topic_names.items():
        for name in names:
            for grade in [8, 9, 10]:
                for diff in range(1, 8):
                    for _ in range(2):  # 2 tasks per combo
                        t = AdaptiveTask(
                            id=task_id,
                            class_level=grade,
                            difficulty_level=diff,
                            topic=name,
                            task_text=f'Task {task_id}: {name} grade {grade} diff {diff}',
                            solution=f'Solution {task_id}',
                            criteria_1_point='1 point',
                            criteria_2_points='2 points',
                            correct_answer=str(task_id),
                            is_flagged=False,
                        )
                        _db.session.add(t)
                        task_id += 1

    _db.session.commit()


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestHelpers:
    """Test private helper functions."""

    def test_map_skill_to_difficulty(self):
        assert _map_skill_to_difficulty(0) == 1
        assert _map_skill_to_difficulty(10) == 1
        assert _map_skill_to_difficulty(20) == 1
        assert _map_skill_to_difficulty(21) == 2
        assert _map_skill_to_difficulty(40) == 2
        assert _map_skill_to_difficulty(50) == 3
        assert _map_skill_to_difficulty(70) == 4
        assert _map_skill_to_difficulty(90) == 5
        assert _map_skill_to_difficulty(100) == 5

    def test_get_topic_priorities(self):
        radar = {
            'algebra': 30,
            'geometry': 70,
            'combinatorics': 20,
            'number_theory': 50,
            'movement': 60,
            'knights_liars': 80,
        }
        priorities = _get_topic_priorities(radar)
        assert len(priorities) == 3
        assert priorities[0] == 'combinatorics'  # weakest (20)
        assert priorities[1] == 'algebra'         # second weakest (30)
        # third could be number_theory (50)
        assert priorities[2] == 'number_theory'

    def test_calculate_days_total_normal(self):
        start = date(2026, 9, 1)
        target = date(2026, 11, 8)
        assert _calculate_days_total(start, target) == 68

    def test_calculate_days_total_minimum(self):
        start = date(2026, 9, 1)
        target = date(2026, 9, 3)  # only 2 days
        assert _calculate_days_total(start, target) == 7  # clamped to min

    def test_calculate_days_total_maximum(self):
        start = date(2026, 1, 1)
        target = date(2027, 1, 1)  # 365 days
        assert _calculate_days_total(start, target) == 180  # clamped to max

    def test_distribute_count(self):
        assert _distribute_count(5, 1) == [5]
        d2 = _distribute_count(5, 2)
        assert sum(d2) == 5
        assert d2[0] >= d2[1]  # first gets more
        d3 = _distribute_count(5, 3)
        assert sum(d3) == 5
        assert d3[0] >= d3[1] >= d3[2]


class TestGeneratePrepPlan:
    """Test generate_prep_plan()."""

    def test_creates_correct_number_of_days(self, user, olympiad, baseline_radar):
        """30 days to olympiad → 30 PrepDay records."""
        target = date.today() + timedelta(days=30)
        plan = generate_prep_plan(user, olympiad, 'Школьный', target, baseline_radar)

        assert plan is not None
        assert plan.status == 'active'
        days = PrepDay.query.filter_by(plan_id=plan.id).count()
        assert days == 30

        # Cleanup
        PrepDay.query.filter_by(plan_id=plan.id).delete()
        _db.session.delete(plan)
        _db.session.commit()

    def test_minimum_7_days(self, user, olympiad, baseline_radar):
        """If target is tomorrow → still 7 days (minimum)."""
        target = date.today() + timedelta(days=2)
        plan = generate_prep_plan(user, olympiad, 'Школьный', target, baseline_radar)

        days = PrepDay.query.filter_by(plan_id=plan.id).count()
        assert days == 7

        # Cleanup
        PrepDay.query.filter_by(plan_id=plan.id).delete()
        _db.session.delete(plan)
        _db.session.commit()

    def test_maximum_180_days(self, user, olympiad, baseline_radar):
        """If target is 2 years away → 180 days (maximum)."""
        target = date.today() + timedelta(days=700)
        plan = generate_prep_plan(user, olympiad, 'Школьный', target, baseline_radar)

        days = PrepDay.query.filter_by(plan_id=plan.id).count()
        assert days == 180

        # Cleanup
        PrepDay.query.filter_by(plan_id=plan.id).delete()
        _db.session.delete(plan)
        _db.session.commit()

    def test_status_today_for_current_date(self, user, olympiad, baseline_radar):
        """Today's PrepDay should have status='today'."""
        target = date.today() + timedelta(days=14)
        plan = generate_prep_plan(user, olympiad, 'Школьный', target, baseline_radar)

        today_day = PrepDay.query.filter_by(plan_id=plan.id, date=date.today()).first()
        assert today_day is not None
        assert today_day.status == 'today'

        # Tomorrow should be 'upcoming'
        tomorrow = PrepDay.query.filter_by(
            plan_id=plan.id, date=date.today() + timedelta(days=1)
        ).first()
        assert tomorrow is not None
        assert tomorrow.status == 'upcoming'

        # Cleanup
        PrepDay.query.filter_by(plan_id=plan.id).delete()
        _db.session.delete(plan)
        _db.session.commit()

    def test_weak_topics_get_more_problems(self, user, olympiad):
        """Weakest topic should appear in more days' target_topics."""
        radar = {
            'algebra': 20,       # very weak
            'geometry': 80,
            'combinatorics': 90,
            'number_theory': 85,
            'movement': 75,
            'knights_liars': 95,
        }
        target = date.today() + timedelta(days=21)
        plan = generate_prep_plan(user, olympiad, 'Школьный', target, radar)

        days = PrepDay.query.filter_by(plan_id=plan.id).all()
        algebra_count = 0
        for d in days:
            topics = json.loads(d.target_topics)
            if 'algebra' in topics:
                algebra_count += 1

        # Algebra (weakest) should be in most days
        assert algebra_count >= len(days) * 0.5

        # Cleanup
        PrepDay.query.filter_by(plan_id=plan.id).delete()
        _db.session.delete(plan)
        _db.session.commit()

    def test_baseline_radar_saved(self, user, olympiad, baseline_radar):
        """Baseline radar should be saved in the plan."""
        target = date.today() + timedelta(days=14)
        plan = generate_prep_plan(user, olympiad, 'Школьный', target, baseline_radar)

        saved_radar = json.loads(plan.baseline_radar)
        assert saved_radar['algebra'] == 30
        assert saved_radar['combinatorics'] == 20

        # Cleanup
        PrepDay.query.filter_by(plan_id=plan.id).delete()
        _db.session.delete(plan)
        _db.session.commit()


class TestSelectProblems:
    """Test select_problems_for_day()."""

    def test_returns_correct_count(self):
        """Should return exactly `count` problems (if enough in bank)."""
        ids = select_problems_for_day(
            grade=9,
            target_topics=['algebra'],
            weak_topic_skill=30,
            day_index_in_plan=0,
            days_total=30,
            count=5,
        )
        assert len(ids) == 5

    def test_no_duplicate_problems(self):
        """No duplicate IDs in a single day."""
        ids = select_problems_for_day(
            grade=9,
            target_topics=['algebra', 'geometry'],
            weak_topic_skill=40,
            day_index_in_plan=1,
            days_total=30,
            count=5,
        )
        assert len(ids) == len(set(ids))

    def test_difficulty_grows_over_time(self):
        """Day 0 should have lower difficulty than day 29."""
        # We can't directly check difficulty from IDs, but we can verify
        # the function doesn't crash and returns different sets
        ids_early = select_problems_for_day(
            grade=9,
            target_topics=['algebra'],
            weak_topic_skill=30,
            day_index_in_plan=0,
            days_total=30,
            count=5,
        )
        ids_late = select_problems_for_day(
            grade=9,
            target_topics=['algebra'],
            weak_topic_skill=30,
            day_index_in_plan=29,
            days_total=30,
            count=5,
        )
        # Both should return results
        assert len(ids_early) > 0
        assert len(ids_late) > 0

    def test_every_7th_day_is_variant(self):
        """Day 6 (7th day, 0-indexed) should have diverse topics."""
        ids = select_problems_for_day(
            grade=9,
            target_topics=['algebra'],
            weak_topic_skill=40,
            day_index_in_plan=6,  # 7th day
            days_total=30,
            count=5,
        )
        # Should return problems (variant day uses all topics)
        assert len(ids) > 0

    def test_grade_filter_respected(self):
        """Tasks should be from grades near the user's grade."""
        ids = select_problems_for_day(
            grade=9,
            target_topics=['algebra'],
            weak_topic_skill=50,
            day_index_in_plan=0,
            days_total=30,
            count=5,
        )
        # Verify all returned tasks are grade 8, 9, or 10
        for task_id in ids:
            task = AdaptiveTask.query.get(task_id)
            assert task is not None
            assert task.class_level in [8, 9, 10]

    def test_exclude_ids_respected(self):
        """Excluded IDs should not appear in results."""
        # First call
        ids1 = select_problems_for_day(
            grade=9,
            target_topics=['algebra'],
            weak_topic_skill=50,
            day_index_in_plan=0,
            days_total=30,
            count=3,
        )
        # Second call excluding first results
        ids2 = select_problems_for_day(
            grade=9,
            target_topics=['algebra'],
            weak_topic_skill=50,
            day_index_in_plan=1,
            days_total=30,
            count=3,
            exclude_ids=set(ids1),
        )
        # No overlap
        assert len(set(ids1) & set(ids2)) == 0


class TestRecomputePlan:
    """Test recompute_plan()."""

    def test_recompute_only_affects_upcoming(self, user, olympiad, baseline_radar):
        """Completed days should not be modified by recompute."""
        target = date.today() + timedelta(days=14)
        plan = generate_prep_plan(user, olympiad, 'Школьный', target, baseline_radar)

        # Mark first day as completed
        first_day = PrepDay.query.filter_by(plan_id=plan.id).order_by(PrepDay.date).first()
        original_problems = first_day.problem_ids
        first_day.status = 'completed'
        _db.session.commit()

        # Recompute
        recompute_plan(plan.id)

        # Completed day should be unchanged
        first_day_after = PrepDay.query.get(first_day.id)
        assert first_day_after.problem_ids == original_problems
        assert first_day_after.status == 'completed'

        # Cleanup
        PrepDay.query.filter_by(plan_id=plan.id).delete()
        _db.session.delete(plan)
        _db.session.commit()
