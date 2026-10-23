# -*- coding: utf-8 -*-
"""C11: aux blocked before answer — direct GET returns 403/404."""

import pytest

AUX_SVG_CONTENT = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<line x1="10" y1="10" x2="90" y2="90" stroke="#E5AC3A"'
    ' stroke-width="1.5" stroke-dasharray="6,4"/>'
    '</svg>'
)


def test_probe_aux_blocked_before_answer(auth_client, five_anchor_tasks, app):
    """GET /figures/aux/probe/<id> without answer returns 403."""
    task = five_anchor_tasks[2]  # geometry anchor

    with app.app_context():
        from models import db
        task.has_aux = True
        task.aux_svg_path = AUX_SVG_CONTENT
        task.aux_reason = 'test midline'
        db.session.commit()

    r = auth_client.get(f'/figures/aux/probe/{task.id}')
    assert r.status_code in (403, 404), (
        f'Expected 403 or 404 before answer, got {r.status_code}'
    )


def test_daily_aux_blocked_before_answer(auth_client, daily_set_with_items, app):
    """GET /figures/aux/daily/<id> without answer returns 403."""
    item_id = None
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
        db.session.commit()

    r = auth_client.get(f'/figures/aux/daily/{item_id}')
    assert r.status_code in (403, 404), (
        f'Expected 403 or 404 before answer, got {r.status_code}'
    )
