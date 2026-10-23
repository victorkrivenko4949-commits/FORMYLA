# -*- coding: utf-8 -*-
"""
Unit tests for olympiad models (models_olympiad.py).

Covers:
  * Создание Probnik (topic + stage) с валидным набором полей.
  * Создание OlympiadTask, привязка к пробнику, проверка UNIQUE (probnik_id, number).
  * Создание TheoryBlock + ProbnikTheory с порядком.
  * UNIQUE constraint на TaskAttempt(user_id, task_id).
  * `related_methods` хранится как JSON-список.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime
from flask import Flask
from sqlalchemy.exc import IntegrityError

from models import (
    db as _db,
    User,
    Probnik,
    OlympiadTask,
    TheoryBlock,
    ProbnikTheory,
    TaskAttempt,
    StageAttempt,
)


@pytest.fixture(scope='module')
def app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['TESTING'] = True
    _db.init_app(app)
    with app.app_context():
        _db.create_all()
        # Базовый пользователь для FK.
        u = User(id=1, email='u1@test.ru', name='U1', preferred_grade=9)
        _db.session.add(u)
        _db.session.commit()
    yield app


@pytest.fixture(autouse=True)
def app_context(app):
    with app.app_context():
        yield


# ─── Probnik ──────────────────────────────────────────────────────────────────

def test_create_topic_probnik():
    p = Probnik(
        code='test-topic-1', type='topic', number=1,
        title='Тема 1', description='desc',
        competition='ВсОШ', grade=9, season_year=2027,
    )
    _db.session.add(p)
    _db.session.commit()
    assert p.id is not None
    assert p.is_published is True
    assert p.created_at is not None


def test_create_stage_probnik():
    p = Probnik(
        code='test-stage-1', type='stage', number=1,
        title='Этап 1',
        duration_minutes=180, max_score=49,
        threshold_prize=15, threshold_winner=30,
    )
    _db.session.add(p)
    _db.session.commit()
    assert p.duration_minutes == 180
    assert p.max_score == 49


def test_probnik_unique_slot_constraint():
    """Дублирование (competition, grade, season, type, number) запрещено."""
    p1 = Probnik(code='dup-a', type='topic', number=42, title='A')
    p2 = Probnik(code='dup-b', type='topic', number=42, title='B')
    _db.session.add_all([p1, p2])
    with pytest.raises(IntegrityError):
        _db.session.commit()
    _db.session.rollback()


# ─── OlympiadTask ─────────────────────────────────────────────────────────────

def test_create_task_and_unique_number_within_probnik():
    p = Probnik(code='tcase-tp-1', type='topic', number=101, title='T101')
    _db.session.add(p)
    _db.session.commit()

    t1 = OlympiadTask(
        probnik_id=p.id, number='1.1', sort_order=1,
        method_primary='E14',
        condition_md='Условие', idea_md='Идея', solution_md='Решение',
        answer='42',
    )
    _db.session.add(t1)
    _db.session.commit()
    assert t1.id is not None
    assert t1.max_score == 7  # server_default

    # Тот же номер внутри пробника -> конфликт.
    t2 = OlympiadTask(
        probnik_id=p.id, number='1.1', sort_order=2,
        method_primary='F4a',
        condition_md='X', idea_md='Y', solution_md='Z',
    )
    _db.session.add(t2)
    with pytest.raises(IntegrityError):
        _db.session.commit()
    _db.session.rollback()


def test_task_cascade_delete_with_probnik():
    p = Probnik(code='tcase-tp-2', type='topic', number=102, title='T102')
    _db.session.add(p)
    _db.session.commit()
    t = OlympiadTask(
        probnik_id=p.id, number='2.1', method_primary='F3',
        condition_md='c', idea_md='i', solution_md='s',
    )
    _db.session.add(t)
    _db.session.commit()
    tid = t.id

    _db.session.delete(p)
    _db.session.commit()
    assert _db.session.get(OlympiadTask, tid) is None


# ─── TheoryBlock + ProbnikTheory ──────────────────────────────────────────────

def test_create_theory_block_with_related_methods_json():
    tb = TheoryBlock(
        method_code='E14', method_name='Индукция', section='E',
        definition_md='Опр.', main_theorems_md='Теоремы',
        related_methods=['F4a', 'F3'],
    )
    _db.session.add(tb)
    _db.session.commit()
    assert tb.related_methods == ['F4a', 'F3']

    fetched = TheoryBlock.query.filter_by(method_code='E14').one()
    assert isinstance(fetched.related_methods, list)
    assert 'F4a' in fetched.related_methods


def test_probnik_theory_link_with_order():
    p = Probnik(code='tcase-tp-3', type='topic', number=103, title='T103')
    tb1 = TheoryBlock(method_code='X1', method_name='X1', section='A')
    tb2 = TheoryBlock(method_code='X2', method_name='X2', section='A')
    _db.session.add_all([p, tb1, tb2])
    _db.session.commit()

    l1 = ProbnikTheory(probnik_id=p.id, theory_block_id=tb1.id, display_order=2)
    l2 = ProbnikTheory(probnik_id=p.id, theory_block_id=tb2.id, display_order=1)
    _db.session.add_all([l1, l2])
    _db.session.commit()

    links = (
        ProbnikTheory.query
        .filter_by(probnik_id=p.id)
        .order_by(ProbnikTheory.display_order)
        .all()
    )
    assert [l.theory_block_id for l in links] == [tb2.id, tb1.id]


# ─── TaskAttempt ──────────────────────────────────────────────────────────────

def test_task_attempt_unique_user_task():
    p = Probnik(code='tcase-tp-4', type='topic', number=104, title='T104')
    _db.session.add(p)
    _db.session.commit()
    t = OlympiadTask(
        probnik_id=p.id, number='4.1', method_primary='E14',
        condition_md='c', idea_md='i', solution_md='s',
    )
    _db.session.add(t)
    _db.session.commit()

    a1 = TaskAttempt(user_id=1, task_id=t.id, status='viewed')
    _db.session.add(a1)
    _db.session.commit()

    a2 = TaskAttempt(user_id=1, task_id=t.id, status='attempted')
    _db.session.add(a2)
    with pytest.raises(IntegrityError):
        _db.session.commit()
    _db.session.rollback()


def test_task_attempt_status_transitions():
    p = Probnik(code='tcase-tp-5', type='topic', number=105, title='T105')
    _db.session.add(p)
    _db.session.commit()
    t = OlympiadTask(
        probnik_id=p.id, number='5.1', method_primary='E14',
        condition_md='c', idea_md='i', solution_md='s',
    )
    _db.session.add(t)
    _db.session.commit()

    a = TaskAttempt(user_id=1, task_id=t.id, status='viewed')
    _db.session.add(a)
    _db.session.commit()

    a.status = 'attempted'
    a.self_score = 5
    a.finished_at = datetime.utcnow()
    _db.session.commit()
    refetched = TaskAttempt.query.get(a.id)
    assert refetched.status == 'attempted'
    assert refetched.self_score == 5
    assert refetched.finished_at is not None


# ─── StageAttempt ─────────────────────────────────────────────────────────────

def test_stage_attempt_with_task_scores_json():
    p = Probnik(
        code='tcase-stg-1', type='stage', number=201, title='Stage 201',
        duration_minutes=180, max_score=49,
        threshold_prize=15, threshold_winner=30,
    )
    _db.session.add(p)
    _db.session.commit()

    s = StageAttempt(
        user_id=1, probnik_id=p.id,
        total_score=22,
        task_scores={'Э1.1': 7, 'Э1.2': 4, 'Э1.3': 7, 'Э1.4': 4, 'Э1.5': 0},
        result='prize',
    )
    _db.session.add(s)
    _db.session.commit()

    fetched = StageAttempt.query.get(s.id)
    assert fetched.task_scores['Э1.1'] == 7
    assert fetched.result == 'prize'
    assert fetched.probnik is not None
    assert fetched.probnik.code == p.code
