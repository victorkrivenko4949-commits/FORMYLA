# -*- coding: utf-8 -*-
"""tests/test_t6_dashboard.py — T6 dashboard widgets tests."""
import pytest
from models import db, UserDashboardItem
from services.dashboard_widgets import AVAILABLE_WIDGETS


class TestDashboardSettings:
    """GET/POST /dashboard/settings."""

    def test_get_settings_200(self, app, test_user):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s['_user_id'] = str(test_user.id)
            r = c.get('/dashboard/settings', follow_redirects=True)
            assert r.status_code == 200
            assert len(r.data) > 100

    def test_add_widgets_visible_on_main(self, app, test_user):
        keys = [w['key'] for w in AVAILABLE_WIDGETS[:2]]
        with app.test_client() as c:
            with c.session_transaction() as s:
                s['_user_id'] = str(test_user.id)
            c.post('/dashboard/settings', data={
                f'widget_{keys[0]}_visible': '1',
                f'widget_{keys[0]}_position': '0',
                f'widget_{keys[1]}_visible': '1',
                f'widget_{keys[1]}_position': '1',
            }, follow_redirects=True)
            r = c.get('/', follow_redirects=True)
            text = r.data.decode('utf-8')
            assert keys[0] in text or 'widget-card' in text

    def test_hide_widgets(self, app, test_user):
        keys = [w['key'] for w in AVAILABLE_WIDGETS[:2]]
        with app.test_client() as c:
            with c.session_transaction() as s:
                s['_user_id'] = str(test_user.id)
            c.post('/dashboard/settings', data={
                f'widget_{keys[0]}_visible': '0',
                f'widget_{keys[0]}_position': '0',
                f'widget_{keys[1]}_visible': '0',
                f'widget_{keys[1]}_position': '1',
            }, follow_redirects=True)
        items = UserDashboardItem.query.filter_by(user_id=test_user.id).all()
        for it in items:
            assert it.visible == False

    def test_unknown_widget_key_400(self, app, test_user):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s['_user_id'] = str(test_user.id)
            r = c.post('/dashboard/settings', data={
                'widget_fake_key_visible': '1',
                'widget_fake_key_position': '0',
            }, follow_redirects=True)
            assert r.status_code == 400
