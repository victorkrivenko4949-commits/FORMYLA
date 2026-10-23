# -*- coding: utf-8 -*-
"""C11: olympiad method aux available immediately, without answer check."""

import pytest

AUX_SVG_CONTENT = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<line x1="10" y1="10" x2="90" y2="90" stroke="#E5AC3A"'
    ' stroke-width="1.5" stroke-dasharray="6,4"/>'
    '</svg>'
)


def test_method_aux_immediate_access(auth_client, app):
    """GET /figures/aux/method/<id> returns 200 without answer check."""
    with app.app_context():
        from models import db
        from models_olympiad import MethodTask

        # Find an existing MethodTask or create one
        method = MethodTask.query.first()
        if method is None:
            pytest.skip('No MethodTask in test DB — cannot test method aux')

        method.has_aux = True
        method.aux_svg_path = AUX_SVG_CONTENT
        method.aux_reason = 'test auxiliary construction'
        db.session.commit()

    r = auth_client.get(f'/figures/aux/method/{method.id}')
    if method.has_aux and method.aux_svg_path:
        assert r.status_code == 200, (
            f'Expected 200 for method aux, got {r.status_code}'
        )
        assert 'stroke-dasharray' in r.data.decode('utf-8')
    else:
        # Method has no aux — 404 is valid
        assert r.status_code in (200, 404), (
            f'Expected 200 or 404, got {r.status_code}'
        )
