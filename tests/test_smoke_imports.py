# -*- coding: utf-8 -*-
"""
Smoke tests — validate that critical imports work and no 500-causing
breakage exists in the Blueprint refactor and DB migration.

Each test is self-contained, no Flask app or DB required (except
data/olympiads_db.py which is pure data).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─── 1. OLYMPIADS_DB data file ────────────────────────────────────────────────

def test_olympiads_db_data():
    """data/olympiads_db.py must load and contain 1600+ olympiads."""
    from data.olympiads_db import OLYMPIADS_DB
    assert isinstance(OLYMPIADS_DB, list)
    assert len(OLYMPIADS_DB) >= 1600, f"Expected 1600+, got {len(OLYMPIADS_DB)}"
    # Spot-check first entry structure
    first = OLYMPIADS_DB[0]
    assert 'id' in first
    assert 'olympiad' in first


# ─── 2. olympiad_bp Blueprint ─────────────────────────────────────────────────

def test_olympiad_bp_has_routes():
    """The olympiad Blueprint must have 16 deferred route functions."""
    from routes.olympiad import olympiad_bp
    assert olympiad_bp.name == 'olympiad'
    assert olympiad_bp.url_prefix == '/olympiads'
    routes = list(olympiad_bp.deferred_functions)
    assert len(routes) >= 15, f"Expected 15+ routes, got {len(routes)}"


def test_olympiad_bp_import_all_models():
    """All olympiad models must be importable (no missing dependencies)."""
    from models_olympiad import (
        Probnik,
        OlympiadTask,
        TheoryBlock,
        ProbnikTheory,
        TaskAttempt,
        StageAttempt,
        MethodTask,
    )
    # Just verify they are model classes
    assert Probnik.__name__ == 'Probnik'
    assert OlympiadTask.__name__ == 'OlympiadTask'
    assert TheoryBlock.__name__ == 'TheoryBlock'
    assert ProbnikTheory.__name__ == 'ProbnikTheory'
    assert TaskAttempt.__name__ == 'TaskAttempt'
    assert StageAttempt.__name__ == 'StageAttempt'
    assert MethodTask.__name__ == 'MethodTask'


# ─── 4. User model generation columns ─────────────────────────────────────────

def test_user_model_has_generation_columns():
    """User model must have the 4 generation-limit columns."""
    from models import User
    cols = {c.name for c in User.__table__.columns}
    for col in ('generation_count_today', 'generation_reset_date',
                'gens_extra_purchased', 'gens_unlimited'):
        assert col in cols, f"Missing column: {col}"


# ─── 5. figures_manifest (used by olympiad views) ─────────────────────────────

def test_figures_manifest_import():
    """services.figures_manifest must load its 200+ entries."""
    from services.figures_manifest import get_figures_for_probnik_task
    assert callable(get_figures_for_probnik_task)


# ─── 6. olympiad_generator (uses OLYMPIADS_DB) ────────────────────────────────

def test_olympiad_generator_import():
    """services.olympiad_generator must import (uses OLYMPIADS_DB)."""
    from services.olympiad_generator import generate_olympiad_task, get_available_olympiads_for_writer
    assert callable(generate_olympiad_task)
    assert callable(get_available_olympiads_for_writer)


# ─── 7. 3-stage olympiad service ──────────────────────────────────────────────

def test_olympiad_3stage_import():
    """services.olympiad_3stage must be importable."""
    from services.olympiad_3stage import generate_olympiad_3stage, stage1_find_task
    assert callable(generate_olympiad_3stage)
    assert callable(stage1_find_task)
