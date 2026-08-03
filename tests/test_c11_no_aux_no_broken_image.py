# -*- coding: utf-8 -*-
"""C11: absence of aux does not render broken image or empty frame."""

import pytest


def test_no_aux_no_broken_image_probe(auth_client, five_anchor_tasks,
                                       test_user, app):
    """Probe task without aux returns 404 from aux endpoint."""
    task_id = five_anchor_tasks[0].id  # algebra anchor — no aux

    with app.app_context():
        from models import db, SolutionAttempt

        # Raw write: set has_aux=0 explicitly
        raw = db.engine.raw_connection()
        raw.execute(
            "UPDATE adaptive_tasks SET has_aux=0, aux_svg_path=NULL, "
            "aux_reason=NULL WHERE id=?",
            (task_id,),
        )
        raw.commit()
        raw.close()
        db.session.remove()

        # Record answer so the route passes answer check
        attempt = SolutionAttempt(
            user_id=test_user.id,
            task_id=task_id,
            probe_id=None,
            attempt_type='probe',
            solution_text='test solution',
        )
        db.session.add(attempt)
        db.session.commit()

    r = auth_client.get(f'/figures/aux/probe/{task_id}')
    assert r.status_code == 404, (
        f'Expected 404 when no aux, got {r.status_code}'
    )


def test_no_aux_no_broken_image_daily(auth_client, daily_set_with_items, app):
    """Daily task item without aux gets 404 from aux endpoint."""
    with app.app_context():
        from models import db
        from daily_tasks.models import DailyTaskItem

        items = (
            DailyTaskItem.query
            .filter_by(daily_set_id=daily_set_with_items.id)
            .order_by(DailyTaskItem.position)
            .all()
        )
        item = items[0]  # algebra — no aux
        item_id = item.id
        item.has_aux = False
        item.aux_svg_path = None
        item.user_answer = '42'  # answered, but no aux
        db.session.commit()

    r = auth_client.get(f'/figures/aux/daily/{item_id}')
    assert r.status_code == 404, (
        f'Expected 404 when no aux, got {r.status_code}'
    )
