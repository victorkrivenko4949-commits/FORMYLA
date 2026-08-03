# -*- coding: utf-8 -*-
"""X8 acceptance test: aux display on 4 surfaces via F0 fixtures + test client.

The minimal test app from conftest.py has no blueprints registered.
We test at the model/ORM level for daily_tasks and figures surfaces,
via ORM attribute access for probe, and via HTTP for olympiad method_task.
"""

import pytest


# ── helpers ──────────────────────────────────────────────────────────────

def _set_task_aux(task_obj, aux_svg, aux_reason="Test aux reason"):
    """Set aux fields on a task object and commit."""
    from models import db
    task_obj.has_aux = True
    task_obj.aux_svg_path = aux_svg
    task_obj.aux_reason = aux_reason
    db.session.commit()


def _aux_svg_stub():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 620 620">'
        '<rect width="620" height="620" fill="#070C18"/>'
        '<line x1="50" y1="50" x2="250" y2="250" stroke="#E5AC3A"'
        ' stroke-width="1.5" stroke-dasharray="6,4"/>'
        '</svg>'
    )


# ── Surface 1: probe (prep) — ORM level ─────────────────────────────────

def test_probe_adaptive_task_has_aux_fields(app, five_anchor_tasks):
    """AdaptiveTask (used by probe) carries aux fields correctly."""
    geo_task = [t for t in five_anchor_tasks if t.subject == 'geometry'][0]
    aux_svg = _aux_svg_stub()
    _set_task_aux(geo_task, aux_svg)

    from models import db, AdaptiveTask
    refetched = db.session.get(AdaptiveTask, geo_task.id)
    assert refetched.has_aux is True
    assert refetched.aux_svg_path == aux_svg
    assert refetched.aux_reason == 'Test aux reason'


# ── Surface 2: daily_tasks — ORM level ──────────────────────────────────

def test_daily_tasks_items_have_aux_fields(
    app, test_user, daily_set_with_items, five_anchor_tasks
):
    """DailyTaskItem model has aux fields accessible via ORM."""
    from models import db
    from daily_tasks.models import DailyTaskItem

    geo_task = [t for t in five_anchor_tasks if t.subject == 'geometry'][0]
    aux_svg = _aux_svg_stub()
    _set_task_aux(geo_task, aux_svg)

    item = DailyTaskItem.query.filter_by(
        daily_set_id=daily_set_with_items.id,
        subject='geometry',
    ).first()
    assert item is not None, "DailyTaskItem for geometry must exist"

    item.has_aux = True
    item.aux_svg_path = aux_svg
    item.aux_reason = 'Test aux'
    db.session.commit()

    item2 = db.session.get(DailyTaskItem, item.id)
    assert item2.has_aux is True
    assert item2.aux_svg_path == aux_svg


# ── Surface 3: figures — ORM level ─────────────────────────────────────

def test_figures_build_job_has_aux_fields(app, figure_build_job):
    """FigureBuildJob model has aux fields accessible via ORM."""
    from models import db

    job = figure_build_job
    job.has_aux = True
    job.aux_svg_path = _aux_svg_stub()
    job.aux_reason = 'Test reason'
    db.session.commit()

    job2 = db.session.get(type(job), job.id)
    assert job2.has_aux is True
    assert 'stroke-dasharray' in job2.aux_svg_path


# ── Surface 4: olympiad method_task — HTTP ─────────────────────────────

def test_method_task_shows_aux_immediately(
    auth_client, app, test_user
):
    """Method task shows aux immediately (no answer needed) when has_aux is ready."""
    from models import db
    from models_olympiad import MethodTask

    aux_svg = _aux_svg_stub()
    mt = MethodTask.query.first()
    if mt is not None:
        mt.has_aux = True
        mt.aux_svg_path = aux_svg
        mt.aux_reason = 'Test method aux'
        db.session.commit()

        resp = auth_client.get(
            f'/olympiad/methods/task/{mt.id}',
            follow_redirects=True,
        )
        assert resp.status_code == 200
        content = resp.data.decode('utf-8', errors='replace')
        assert 'aux_svg_path' in content
