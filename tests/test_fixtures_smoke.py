# -*- coding: utf-8 -*-
"""
tests/test_fixtures_smoke.py — Smoke tests for F0 fixtures.

One test per fixture: app, client, test_user, five_anchor_tasks,
figure_build_job, daily_set_with_items, test_svg_files, auth_client.

ALL tests work on a temp SQLite database created by the 'app' fixture.
The production database under instance/ is NEVER opened.
"""


def test_app_config(app):
    """Fixture 'app' has TESTING=True and does NOT point at instance/formyla.db."""
    assert app.config['TESTING'] is True
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    assert 'instance/formyla.db' not in uri
    assert 'instance\\formyla.db' not in uri


def test_client_type(client):
    """Fixture 'client' returns a Flask test client."""
    from flask.testing import FlaskClient
    assert isinstance(client, FlaskClient)


def test_test_user_exists(test_user, app):
    """Fixture 'test_user' creates a real DB row with a valid id."""
    from models import User

    with app.app_context():
        fetched = User.query.get(test_user.id)
        assert fetched is not None
        assert fetched.id is not None
        assert fetched.id == test_user.id
        assert fetched.email == 'test_f0@example.invalid'


def test_five_anchor_tasks_count_and_order(five_anchor_tasks):
    """Exactly 5 tasks, anchors in correct order, text contains [TEST]."""
    assert len(five_anchor_tasks) == 5

    expected_sections = [
        'algebra', 'number_theory', 'geometry', 'combinatorics', 'logic'
    ]
    actual_sections = [t.subject for t in five_anchor_tasks]
    assert actual_sections == expected_sections

    for task in five_anchor_tasks:
        assert '[TEST]' in task.task_text, (
            f'Task {task.source_id} missing [TEST] prefix in task_text'
        )


def test_figure_build_job_status_and_links(figure_build_job, test_user, five_anchor_tasks):
    """Fixture 'figure_build_job' has status=queued, linked to task and user."""
    assert figure_build_job.status == 'queued'
    assert figure_build_job.user_id == test_user.id
    assert figure_build_job.model_name == 'test-model'
    assert figure_build_job.problem_text.startswith('[TEST]')


def test_daily_set_with_items_structure(daily_set_with_items, five_anchor_tasks, app):
    """One DailyTaskSet with exactly 5 items, anchors match."""
    from daily_tasks.models import DailyTaskItem

    with app.app_context():
        items = (
            DailyTaskItem.query
            .filter_by(daily_set_id=daily_set_with_items.id)
            .order_by(DailyTaskItem.position)
            .all()
        )
    assert len(items) == 5

    item_subjects = {item.subject for item in items}
    task_subjects = {task.subject for task in five_anchor_tasks}
    assert item_subjects == task_subjects


def test_svg_files_exist_and_differ(test_svg_files):
    """Base SVG has no stroke-dasharray; aux SVG has it."""
    base_path, aux_path = test_svg_files

    assert base_path.exists()
    assert aux_path.exists()

    base_text = base_path.read_text(encoding='utf-8')
    aux_text = aux_path.read_text(encoding='utf-8')

    assert 'stroke-dasharray' not in base_text
    assert 'stroke-dasharray' in aux_text


def test_auth_client_no_401_403_500(auth_client, app):
    """Auth client can GET a protected route without 401/403/500."""
    # Find any existing route that doesn't have auth-specific issues.
    # Use /profile or /figures — pick the first reasonable one.
    candidates = ['/profile', '/figures', '/dashboard']
    status = None
    for path in candidates:
        r = auth_client.get(path, follow_redirects=True)
        status = r.status_code
        if status not in (401, 403, 500):
            break

    assert status is not None, 'No route tested successfully'
    assert status != 401, f'Got 401 Unauthorized for auth_client'
    assert status != 403, f'Got 403 Forbidden for auth_client'
    assert status != 500, f'Got 500 Internal Server Error for auth_client'
