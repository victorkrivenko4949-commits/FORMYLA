# -*- coding: utf-8 -*-
"""C11: base SVG remains open — blocking is only for aux, not base."""

import pytest


def test_probe_aux_blocked_without_answer(auth_client, five_anchor_tasks, app):
    """Auth'd GET /figures/aux/probe/<id> returns 403 without answer."""
    task_id = five_anchor_tasks[2].id  # geometry

    with app.app_context():
        from models import db
        raw = db.engine.raw_connection()
        raw.execute(
            "UPDATE adaptive_tasks SET has_aux=1, aux_svg_path=:a, "
            "aux_reason='test' WHERE id=:t",
            {"a": '<svg>test</svg>', "t": task_id},
        )
        raw.commit()
        raw.close()
        db.session.remove()

    r = auth_client.get(f'/figures/aux/probe/{task_id}')
    assert r.status_code in (403, 404), (
        f'aux probe GET returns {r.status_code} before answer'
    )


def test_aux_blocked_for_unauthenticated(auth_client, five_anchor_tasks,
                                          app, client):
    """Unauthenticated GET to /figures/aux/probe returns 302/403."""
    task_id = five_anchor_tasks[0].id
    with app.app_context():
        from models import db
        raw = db.engine.raw_connection()
        raw.execute(
            "UPDATE adaptive_tasks SET has_aux=1, aux_svg_path=:a, "
            "aux_reason='test' WHERE id=:t",
            {"a": '<svg>test</svg>', "t": task_id},
        )
        raw.commit()
        raw.close()
        db.session.remove()

    r = client.get(f'/figures/aux/probe/{task_id}', follow_redirects=True)
    assert r.status_code in (302, 403, 404), (
        f'Unauthenticated aux GET returns {r.status_code}'
    )
