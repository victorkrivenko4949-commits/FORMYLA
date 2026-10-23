# -*- coding: utf-8 -*-
"""C11: aux allowed after answer — after submit, GET returns 200 with SVG."""

import pytest

AUX_SVG_CONTENT = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<line x1="10" y1="10" x2="90" y2="90" stroke="#E5AC3A"'
    ' stroke-width="1.5" stroke-dasharray="6,4"/>'
    '</svg>'
)


def test_probe_aux_allowed_after_answer(auth_client, five_anchor_tasks,
                                         test_user, app):
    """GET /figures/aux/probe/<id> after answer returns 200 with SVG."""
    task_id = five_anchor_tasks[2].id  # geometry anchor (id=3)

    with app.app_context():
        from models import db, AdaptiveTask, SolutionAttempt

        # Write aux via raw_connection to bypass scoped_session identity map
        raw = db.engine.raw_connection()
        raw.execute(
            "UPDATE adaptive_tasks SET has_aux=1, aux_svg_path=?, "
            "aux_reason='test midline' WHERE id=?",
            (AUX_SVG_CONTENT, task_id),
        )
        raw.commit()
        raw.close()

        # Remove scoped session so route handler creates a fresh session
        # that reads the updated row.
        db.session.remove()

        # Record answer in the fresh session
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
    assert r.status_code == 200, (
        f'Expected 200 after answer, got {r.status_code}: {r.data[:200]}'
    )
    assert 'stroke-dasharray' in r.data.decode('utf-8'), (
        'Response must contain aux SVG with stroke-dasharray'
    )


def test_daily_aux_allowed_after_answer(auth_client, daily_set_with_items, app):
    """GET /figures/aux/daily/<id> after answer returns 200 with SVG."""
    with app.app_context():
        from models import db
        from daily_tasks.models import DailyTaskItem

        items = (
            DailyTaskItem.query
            .filter_by(daily_set_id=daily_set_with_items.id)
            .order_by(DailyTaskItem.position)
            .all()
        )
        item = items[2]  # geometry
        item_id = item.id
        item.has_aux = True
        item.aux_svg_path = AUX_SVG_CONTENT
        item.aux_reason = 'test midline'
        item.user_answer = '42'
        db.session.commit()

    r = auth_client.get(f'/figures/aux/daily/{item_id}')
    assert r.status_code == 200, (
        f'Expected 200 after answer, got {r.status_code}: {r.data[:200]}'
    )
    assert 'stroke-dasharray' in r.data.decode('utf-8'), (
        'Response must contain aux SVG with stroke-dasharray'
    )
