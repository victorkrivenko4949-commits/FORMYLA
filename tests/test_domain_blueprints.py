"""Focused contracts for extraction without booting another full application."""
import importlib

import pytest
from flask import Flask, url_for
from flask_login import LoginManager

from utils.blueprint_compat import register_legacy_blueprint


@pytest.fixture
def domain_app():
    app = Flask(__name__)
    app.config.update(SECRET_KEY="local-tests", TESTING=True)
    login = LoginManager(app)
    login.user_loader(lambda _id: None)
    for domain in ("teacher", "billing", "bank"):
        module = importlib.import_module(f"{domain}.routes")
        register_legacy_blueprint(app, module.bp, module.LEGACY_ENDPOINTS)
    return app


@pytest.mark.parametrize("endpoint,path,method", [
    ("send_mentorship_request", "/api/social/mentorship/request", "POST"),
    ("respond_mentorship_request", "/api/social/mentorship/respond", "POST"),
    ("list_students", "/api/social/mentorship/students", "GET"),
    ("list_teachers", "/api/social/mentorship/teachers", "GET"),
    ("subscribe_page", "/subscribe", "GET"),
    ("api_subscribe", "/api/subscribe", "POST"),
    ("api_cancel_subscription", "/api/cancel_subscription", "POST"),
    ("secrets", "/secrets", "GET"),
    ("api_secrets", "/api/secrets", "GET"),
])
def test_old_urls_and_auth(domain_app, endpoint, path, method):
    with domain_app.test_request_context():
        assert url_for(endpoint) == path
        matched, _ = domain_app.url_map.bind("localhost").match(path, method=method)
        assert matched.endswith("." + endpoint)
    assert domain_app.test_client().open(path, method=method).status_code == 401


def test_public_article_endpoint(domain_app):
    with domain_app.test_request_context():
        assert url_for("secret_detail", secret_id=12) == "/secrets/12"
        assert domain_app.url_map.bind("localhost").match("/secrets/12")[0] == "bank.secret_detail"


@pytest.mark.parametrize("endpoint,path,key", [
    ("accept_request", "/accept_request/7", "mentorship_id"),
    ("reject_request", "/reject_request/7", "mentorship_id"),
    ("student_profile", "/student/7", "student_id"),
])
def test_remaining_teacher_routes(domain_app, endpoint, path, key):
    method = "GET" if key == "student_id" else "POST"
    with domain_app.test_request_context():
        assert url_for(endpoint, **{key: 7}) == path
        assert domain_app.url_map.bind("localhost").match(path, method=method)[0] == "teacher." + endpoint
    assert domain_app.test_client().open(path, method=method).status_code == 401


def test_modules_share_cache_and_private_helpers():
    import daily_tasks.formyla_bank as old_bank
    import bank.repository as new_bank
    import routes.parent_teacher as old_teacher
    import teacher.groups as new_teacher
    assert old_bank is new_bank
    assert old_teacher is new_teacher
    assert old_bank._BANK_PATH.name == "FORMYLA_BANK.jsonl"
    assert old_teacher._require_role is new_teacher._require_role


def test_global_subscription_context(domain_app):
    with domain_app.test_request_context():
        context = {}
        domain_app.update_template_context(context)
        assert context["is_premium"] is False


@pytest.mark.parametrize("value,expected", [
    ("premium", True), (" PREMIUM_MONTHLY ", True), ("premium_yearly", True),
    ("free", False), (None, False), ("pro", False),
])
def test_legacy_plan_semantics(value, expected):
    from billing.routes import _is_premium_plan
    assert _is_premium_plan(value) is expected


def test_demo_subscription_roundtrip(domain_app, monkeypatch):
    from datetime import datetime
    from types import SimpleNamespace
    from flask_login import UserMixin
    import billing.routes as routes
    class DemoUser(UserMixin):
        id = 99
        current_plan = "free"
        plan_expires_at = None
    user = DemoUser()
    domain_app.login_manager.request_loader(lambda request: user)
    commits = []
    monkeypatch.setattr(routes, "db", SimpleNamespace(
        session=SimpleNamespace(commit=lambda: commits.append(True))))
    client = domain_app.test_client()
    assert client.post("/api/subscribe", json={"plan": "unknown"}).status_code == 400
    response = client.post("/api/subscribe", json={"plan": "premium_monthly"})
    assert response.status_code == 200
    assert response.json["plan"] == "premium"
    assert 29 <= (user.plan_expires_at - datetime.utcnow()).days <= 30
    assert client.post("/api/cancel_subscription").json["ok"] is True
    assert user.current_plan == "free"
    assert user.plan_expires_at is None
    assert client.post("/api/cancel_subscription").status_code == 400
    assert len(commits) == 2
