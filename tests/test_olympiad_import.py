# -*- coding: utf-8 -*-
"""
Tests for Pydantic schemas and the importer (`scripts/import_olympiad.py`).

Covers:
  * Pydantic схемы валидируют корректный JSON.
  * Невалидные данные (missing required, wrong enum, score>7 и т. п.) бросают ValidationError.
  * Stage-пробник без duration_minutes/max_score отвергается.
  * Importer: первичный insert и повторный run = идемпотентный update без дублей.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from flask import Flask
from pydantic import ValidationError

from models import db as _db, Probnik, OlympiadTask, TheoryBlock, ProbnikTheory
from schemas.olympiad import (
    TheoryBlockSchema,
    TaskSchema,
    ProbnikSchema,
    ProbnikTheoryLinkSchema,
)

from scripts.import_olympiad import (
    _validate_each,
    _upsert_theory,
    _upsert_probniks,
    _replace_tasks,
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
    yield app


@pytest.fixture(autouse=True)
def app_context(app):
    with app.app_context():
        yield


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

def test_theory_block_schema_valid():
    s = TheoryBlockSchema.model_validate({
        'method_code': 'E14',
        'method_name': 'Индукция',
        'section': 'E',
        'definition_md': 'Метод…',
        'related_methods': ['F4a', 'F3'],
    })
    assert s.method_code == 'E14'
    assert s.related_methods == ['F4a', 'F3']


def test_theory_block_invalid_section():
    with pytest.raises(ValidationError):
        TheoryBlockSchema.model_validate({
            'method_code': 'E14',
            'method_name': 'X',
            'section': 'Z',          # допустимы только A..H
        })


def test_task_schema_valid():
    t = TaskSchema.model_validate({
        'probnik_code': 'imp-topic-1',
        'number': '1.1',
        'sort_order': 1,
        'difficulty': 'yellow',
        'method_primary': 'E14',
        'condition_md': 'Условие',
        'idea_md': 'Идея',
        'solution_md': 'Решение',
        'answer': '42',
        'max_score': 7,
    })
    assert t.number == '1.1'
    assert t.max_score == 7


def test_task_schema_invalid_max_score():
    """max_score должен быть неотрицательным (ge=0)."""
    with pytest.raises(ValidationError):
        TaskSchema.model_validate({
            'probnik_code': 'imp-topic-1',
            'number': '1.1',
            'method_primary': 'E14',
            'condition_md': 'c', 'idea_md': 'i', 'solution_md': 's',
            'max_score': -1,
        })


def test_task_schema_missing_required():
    with pytest.raises(ValidationError):
        TaskSchema.model_validate({
            'number': '1.1',
            # probnik_code, method_primary, condition_md, idea_md, solution_md missing
        })


def test_probnik_schema_topic_valid():
    p = ProbnikSchema.model_validate({
        'code': 'vsosh-9-2027-topic-1',
        'type': 'topic',
        'number': 1,
        'title': 'Тема 1',
        'description': 'desc',
    })
    assert p.type == 'topic'
    assert p.competition == 'ВсОШ'  # default
    assert p.grade == 9
    assert p.season_year == 2027


def test_probnik_schema_stage_requires_duration_and_max_score():
    """Stage-пробник без duration_minutes и max_score -> отвергается."""
    with pytest.raises(ValidationError):
        ProbnikSchema.model_validate({
            'code': 'vsosh-9-2027-stage-1',
            'type': 'stage',
            'number': 1,
            'title': 'Stage 1',
            # duration_minutes / max_score missing
        })


def test_probnik_schema_stage_valid():
    p = ProbnikSchema.model_validate({
        'code': 'vsosh-9-2027-stage-1',
        'type': 'stage',
        'number': 1,
        'title': 'Stage 1',
        'duration_minutes': 180,
        'max_score': 49,
        'threshold_prize': 15,
        'threshold_winner': 30,
    })
    assert p.duration_minutes == 180
    assert p.max_score == 49


# ─── Importer end-to-end (in-memory DB) ───────────────────────────────────────

_FIXT_THEORY = [
    {
        'method_code': 'E14', 'method_name': 'Индукция', 'section': 'E',
        'definition_md': 'Опр.', 'related_methods': ['F4a'],
    },
    {
        'method_code': 'F4a', 'method_name': 'Дирихле', 'section': 'F',
        'definition_md': 'Опр.',
    },
]
_FIXT_PROBNIKS = [
    {
        'code': 'imp-topic-1', 'type': 'topic', 'number': 1,
        'title': 'Imp Topic 1',
        'theory': [{'method_code': 'E14', 'order': 1}],
    },
    {
        'code': 'imp-stage-1', 'type': 'stage', 'number': 1,
        'title': 'Imp Stage 1',
        'duration_minutes': 60, 'max_score': 21,
        'threshold_prize': 10, 'threshold_winner': 15,
    },
]
_FIXT_TASKS = [
    {
        'probnik_code': 'imp-topic-1',
        'number': '1.1', 'sort_order': 1,
        'method_primary': 'E14',
        'condition_md': 'c', 'idea_md': 'i', 'solution_md': 's',
        'answer': '42',
    },
    {
        'probnik_code': 'imp-stage-1',
        'number': 'Э1.1', 'sort_order': 1,
        'method_primary': 'F4a',
        'condition_md': 'c', 'idea_md': 'i', 'solution_md': 's',
    },
]


def _validate_all():
    theory_items = _validate_each(_FIXT_THEORY, TheoryBlockSchema, "theory")
    probnik_items = _validate_each(_FIXT_PROBNIKS, ProbnikSchema, "probniks")
    task_items = _validate_each(_FIXT_TASKS, TaskSchema, "tasks")
    return theory_items, probnik_items, task_items


def test_importer_insert_then_idempotent_update():
    """Первый прогон создаёт записи, повторный — обновляет без дублей."""
    theory_items, probnik_items, task_items = _validate_all()

    # Run 1: insert.
    th_c, th_u = _upsert_theory(theory_items)
    code_to_id, p_c, p_u = _upsert_probniks(probnik_items)
    t_del, t_ins = _replace_tasks(task_items, code_to_id)
    _db.session.commit()

    assert th_c == 2 and th_u == 0
    assert p_c == 2 and p_u == 0
    assert t_ins == 2 and t_del == 0

    assert TheoryBlock.query.count() == 2
    assert Probnik.query.count() == 2
    assert OlympiadTask.query.count() == 2
    assert ProbnikTheory.query.count() == 1

    # Run 2: idempotent — те же данные, никаких новых строк.
    theory_items2, probnik_items2, task_items2 = _validate_all()
    th_c2, th_u2 = _upsert_theory(theory_items2)
    code_to_id2, p_c2, p_u2 = _upsert_probniks(probnik_items2)
    t_del2, t_ins2 = _replace_tasks(task_items2, code_to_id2)
    _db.session.commit()

    assert th_c2 == 0 and th_u2 == 2
    assert p_c2 == 0 and p_u2 == 2
    # Tasks: delete-and-reinsert per probnik (source-of-truth).
    assert t_ins2 == 2
    assert t_del2 == 2

    assert TheoryBlock.query.count() == 2
    assert Probnik.query.count() == 2
    assert OlympiadTask.query.count() == 2
    assert ProbnikTheory.query.count() == 1


def test_importer_strict_extra_fields_in_schema():
    """Schemas have extra='forbid' — unknown JSON keys are rejected."""
    with pytest.raises(ValidationError):
        TheoryBlockSchema.model_validate({
            'method_code': 'X1',
            'method_name': 'X',
            'extra_unknown_field': 'oops',
        })


def test_probnik_theory_link_schema():
    """Standalone link schema."""
    link = ProbnikTheoryLinkSchema.model_validate({
        'method_code': 'E14',
        'order': 3,
    })
    assert link.method_code == 'E14'
    assert link.order == 3
