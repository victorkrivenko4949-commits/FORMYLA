# -*- coding: utf-8 -*-
"""E2E-тесты API «Банка неточностей» (разделы 8, 10 ТЗ).

Покрытие:
  - pending-уведомления возвращают suppressed:true при активном срезе;
  - уведомление после показа помечается seen (не повторяется);
  - dismiss ставит статус dismissed.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def authed_client(app, test_user):
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["_user_id"] = str(test_user.id)
            sess["_fresh"] = True
        yield client


def _make_notification(user_id):
    from models import db
    from models_insights import InsightNotification
    n = InsightNotification(user_id=user_id, kind="new", status="pending")
    db.session.add(n)
    db.session.commit()
    return n


def test_pending_notification_suppressed_when_review_active(app, test_user, authed_client, monkeypatch):
    with app.app_context():
        _make_notification(test_user.id)

    def _active(user_id):
        return True

    monkeypatch.setattr("routes.insights._active_review_session", _active)

    r = authed_client.get("/api/insights/notifications/pending")
    data = r.get_json()
    assert data["suppressed"] is True


def test_pending_notification_not_suppressed_when_no_review(app, test_user, authed_client, monkeypatch):
    with app.app_context():
        _make_notification(test_user.id)

    def _inactive(user_id):
        return False

    monkeypatch.setattr("routes.insights._active_review_session", _inactive)

    r = authed_client.get("/api/insights/notifications/pending")
    data = r.get_json()
    assert data["suppressed"] is False
    assert data["count"] >= 1


def test_mark_seen(app, test_user, authed_client):
    with app.app_context():
        n = _make_notification(test_user.id)
        nid = n.id

    r = authed_client.post(f"/api/insights/notifications/{nid}/seen")
    assert r.status_code == 200
    with app.app_context():
        from models_insights import InsightNotification
        n2 = InsightNotification.query.get(nid)
        assert n2.status == "seen"


def test_dismiss_insight(app, test_user, authed_client):
    with app.app_context():
        from models import db
        from models_insights import Insight, normalize_title
        title = "Считает размещения прямым перебором вместо правила умножения"
        ins = Insight(
            user_id=test_user.id,
            title=title,
            title_normalized=normalize_title(title),
            type="time_loss",
            severity=2,
        )
        db.session.add(ins)
        db.session.commit()
        iid = ins.id

    r = authed_client.post(
        f"/api/insights/{iid}/dismiss",
        data=json.dumps({"reason": "slip"}),
        content_type="application/json",
    )
    assert r.status_code == 200
    with app.app_context():
        from models_insights import Insight
        ins2 = Insight.query.get(iid)
        assert ins2.status == "dismissed"
        assert ins2.dismiss_reason == "slip"
