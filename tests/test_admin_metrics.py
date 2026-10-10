"""Known-value SQLite fixtures: dates, distinct users, missing data and access."""
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin
from jinja2 import ChoiceLoader, DictLoader, FileSystemLoader
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from admin_metrics.service import collect_metrics


def make_engine():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    statements = [
        "CREATE TABLE users(id INTEGER PRIMARY KEY, is_guest BOOLEAN, created_at DATETIME, role TEXT, telegram_id TEXT, trial_started_at DATETIME)",
        "INSERT INTO users VALUES(1,0,'2026-10-01','teacher','111',NULL),(2,0,'2026-10-07 21:00:00','student',NULL,'2026-10-07 21:00:00'),(3,1,'2026-10-08','student','333',NULL),(4,0,'2026-10-08 21:00:00','student',NULL,NULL)",
        "CREATE TABLE site_time_sections(user_id INTEGER, day DATE, seconds INTEGER)",
        "INSERT INTO site_time_sections VALUES(1,'2026-10-08',10),(1,'2026-10-08',20),(2,'2026-10-02',5),(3,'2026-10-08',100),(2,'2026-10-08',0)",
        "CREATE TABLE daily_task_sets(id INTEGER PRIMARY KEY, user_id INTEGER)",
        "INSERT INTO daily_task_sets VALUES(1,1),(2,3)",
        "CREATE TABLE daily_task_items(daily_set_id INTEGER, is_correct BOOLEAN, answered_at DATETIME)",
        "INSERT INTO daily_task_items VALUES(1,1,'2026-10-07 21:00:00'),(1,1,'2026-10-08 20:59:59'),(1,1,'2026-10-08 21:00:00'),(1,0,'2026-10-08 12:00:00'),(2,1,'2026-10-08 12:00:00')",
        "CREATE TABLE bank_issues(user_id INTEGER, is_correct BOOLEAN, answered_at DATETIME)",
        "INSERT INTO bank_issues VALUES(2,1,'2026-10-08 12:00:00')",
        "CREATE TABLE olympiad_task_attempts(user_id INTEGER, status TEXT, finished_at DATETIME)",
        "INSERT INTO olympiad_task_attempts VALUES(1,'solved','2026-10-08 12:00:00'),(1,'attempted','2026-10-08 12:00:00')",
        "CREATE TABLE verified_problem_checks(user_id INTEGER, is_correct BOOLEAN, solved_at DATETIME)",
        "CREATE TABLE insights(id INTEGER PRIMARY KEY, user_id INTEGER)",
        "INSERT INTO insights VALUES(1,2)",
        "CREATE TABLE insight_practice_tasks(insight_id INTEGER, is_correct BOOLEAN, solved_at DATETIME)",
        "INSERT INTO insight_practice_tasks VALUES(1,1,'2026-10-08 12:00:00')",
        "CREATE TABLE test_results_detail(user_id INTEGER, task_id TEXT, test_type TEXT, is_correct BOOLEAN, created_at DATETIME)",
        "INSERT INTO test_results_detail VALUES(1,'a','practice',1,'2026-10-08 12:00:00'),(1,'a','practice',1,'2026-10-08 13:00:00'),(2,'a','practice',1,'2026-10-08 12:00:00'),(2,'b','exam',1,'2026-10-08 12:00:00')",
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
    return engine


@pytest.fixture
def metrics_engine():
    engine = make_engine()
    yield engine
    engine.dispose()


def test_exact_counts_and_moscow_boundaries(metrics_engine):
    m = collect_metrics(metrics_engine, date(2026, 10, 8), 7)
    assert m["registrations"] == 2  # guest and next-day registration excluded
    assert m["registrations_day"] == 1
    assert m["teachers_current"] == 1
    assert m["telegram_linked_current"] == 1
    assert m["trials_started_day"] == 1
    assert m["tracked_dau"] == 1
    assert m["tracked_wau"] == 2  # not sum(DAU)
    assert m["series"][-1]["solved_by_source"] == {
        "daily": 2, "bank": 1, "olympiad": 1, "verified": 0,
        "insight": 1, "client_practice": 2,
    }
    assert m["series"][-1]["server_solved"] == 5
    assert m["unavailable"] == []
    assert m["paying_users"] is None
    assert m["telegram_subscribers"] is None


def test_missing_source_is_unknown_not_zero(metrics_engine):
    with metrics_engine.begin() as c:
        c.exec_driver_sql("DROP TABLE bank_issues")
        c.exec_driver_sql("DROP TABLE site_time_sections")
    m = collect_metrics(metrics_engine, date(2026, 10, 8), 1)
    assert m["tracked_dau"] is None
    assert m["tracked_wau"] is None
    assert m["series"][0]["server_solved"] is None
    assert m["series"][0]["available_server_solved"] == 4
    assert "bank_issues" in m["unavailable"]


def test_empty_database_returns_unknown():
    engine = create_engine("sqlite://")
    m = collect_metrics(engine, date(2026, 10, 8), 1)
    assert m["registrations"] is None
    assert m["series"][0]["server_solved"] is None
    engine.dispose()


def test_collector_has_no_write_queries(metrics_engine):
    statements = []
    event.listen(metrics_engine, "before_cursor_execute",
                 lambda conn, cursor, statement, params, ctx, many: statements.append(statement))
    collect_metrics(metrics_engine, date(2026, 10, 8), 1)
    forbidden = ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP")
    assert not any(s.lstrip().upper().startswith(forbidden) for s in statements)


@pytest.mark.parametrize("day,days", [
    (date(2099, 1, 1), 7), (date(2026, 10, 8), 0), (date(2026, 10, 8), 32),
])
def test_invalid_window(metrics_engine, day, days):
    with pytest.raises(ValueError):
        collect_metrics(metrics_engine, day, days)


def make_test_app(engine):
    import admin_metrics.routes as routes
    app = Flask(__name__, static_folder=str(Path(__file__).resolve().parents[1] / "static"))
    app.config.update(SECRET_KEY="synthetic-tests-only", TESTING=True)
    app.jinja_loader = ChoiceLoader([
        DictLoader({"base.html": '<!doctype html><html lang="ru"><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>{% block title %}{% endblock %}</title></head><body style="margin:0;font-family:Arial,sans-serif">{% block content %}{% endblock %}</body></html>'}),
        FileSystemLoader(str(Path(__file__).resolve().parents[1] / "templates")),
    ])
    login = LoginManager(app)
    class TestUser(UserMixin):
        id = "metrics-test-user"
        def __init__(self, admin):
            self.is_admin = admin
    @login.request_loader
    def load(request):
        role = request.headers.get("X-Test-Role")
        return TestUser(role == "admin") if role else None
    app.register_blueprint(routes.bp)
    return app


@pytest.fixture
def metrics_client(metrics_engine, monkeypatch):
    monkeypatch.setattr("admin_metrics.routes.db", SimpleNamespace(engine=metrics_engine))
    return make_test_app(metrics_engine).test_client()


@pytest.mark.parametrize("path", ["/admin/metrics", "/admin/metrics.json"])
def test_metrics_access(metrics_client, path):
    assert metrics_client.get(path).status_code == 401
    response = metrics_client.get(path, headers={"X-Test-Role": "student"})
    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "no-store, private"
    assert metrics_client.get(path, headers={"X-Test-Role": "teacher"}).status_code == 403
    response = metrics_client.get(path, headers={"X-Test-Role": "admin"})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store, private"


@pytest.mark.parametrize("query", ["date=wrong", "date=2099-01-01", "days=0", "days=32", "days=no"])
def test_route_invalid_input(metrics_client, query):
    assert metrics_client.get("/admin/metrics?" + query, headers={"X-Test-Role": "admin"}).status_code == 400


def test_html_and_json_use_same_counts(metrics_client):
    headers = {"X-Test-Role": "admin"}
    m = metrics_client.get("/admin/metrics.json?date=2026-10-08", headers=headers).json
    html = metrics_client.get("/admin/metrics?date=2026-10-08", headers=headers).text
    assert m["series"][-1]["server_solved"] == 5
    assert "Серверный итог" in html
    assert "/admin/metrics.json?date=2026-10-08" in html
    assert "Нет данных" in html
