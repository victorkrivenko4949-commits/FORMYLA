"""Regression coverage for checked/solved counters and XP level display."""

from datetime import datetime, timedelta

from daily_tasks.models import DailyTaskItem, DailyTaskSet
from models import (
    BankIssue, TestResult as StoredTestResult, User, VerifiedProblemCheck, db,
)
from services.solved_stats import solved_counts_by_user, task_counts_by_user


def test_checked_and_correct_tasks_include_all_recorded_outcomes(app, test_user):
    now = datetime.utcnow()
    old = now - timedelta(days=10)
    task_set = DailyTaskSet(
        user_id=test_user.id, target_date=now.date(), status="ready")
    db.session.add(task_set)
    db.session.flush()
    db.session.add_all([
        DailyTaskItem(daily_set_id=task_set.id, position=1,
                      task_text="Correct", is_correct=True, answered_at=now),
        DailyTaskItem(daily_set_id=task_set.id, position=2,
                      task_text="Incorrect", is_correct=False, answered_at=now),
        BankIssue(user_id=test_user.id, task_id=101, subtopic="Algebra",
                  level=1, issued_date=old.date(), is_correct=True,
                  answered_at=old),
        StoredTestResult(user_id=test_user.id, test_type="practice", task_id=42,
                   is_correct=True, created_at=now),
        StoredTestResult(user_id=test_user.id, test_type="practice", task_id=42,
                   is_correct=True, created_at=now),  # retry: one task
        StoredTestResult(user_id=test_user.id, test_type="practice", task_id=43,
                   is_correct=False, created_at=now),
    ])
    db.session.commit()

    assert solved_counts_by_user()[test_user.id] == 3
    assert task_counts_by_user(checked=True)[test_user.id] == 5
    since = now - timedelta(days=1)
    assert task_counts_by_user(since=since)[test_user.id] == 2
    assert task_counts_by_user(checked=True, since=since)[test_user.id] == 4
    assert task_counts_by_user(checked=True)[test_user.id] >= solved_counts_by_user()[test_user.id]


def test_xp_level_is_not_a_stale_cached_column(app, test_user):
    test_user.experience_points = 155
    test_user.current_level = 1
    db.session.commit()
    assert db.session.get(User, test_user.id).xp_level == 2
    assert test_user.get_leaderboard_score() == 155


def test_regular_problem_is_persisted_and_credited_only_once(
        app, auth_client, test_user, monkeypatch):
    import app as main_app

    monkeypatch.setattr(main_app, "PROBLEMS_DB", [
        {"id": 987654, "answer": "42", "solution": "42",
         "difficulty": 1, "title": "Test"},
    ])
    app.add_url_rule("/api/check_answer", view_func=main_app.check_answer,
                     methods=["POST"])
    payload = {"problem_id": 987654, "user_answer": "41"}
    first = auth_client.post("/api/check_answer", json=payload)
    assert first.status_code == 200
    assert first.json["correct"] is False
    assert task_counts_by_user(checked=True)[test_user.id] == 1
    assert solved_counts_by_user().get(test_user.id, 0) == 0

    payload["user_answer"] = "42"
    accepted = auth_client.post("/api/check_answer", json=payload)
    assert accepted.status_code == 200
    assert accepted.json["xp_gained"] == 10
    points = db.session.get(User, test_user.id).experience_points
    assert points == 30  # 10 base + 20 first-difficulty bonus

    repeated = auth_client.post("/api/check_answer", json=payload)
    assert repeated.status_code == 200
    assert repeated.json["xp_gained"] == 0
    assert db.session.get(User, test_user.id).experience_points == points
    assert VerifiedProblemCheck.query.count() == 1
    assert VerifiedProblemCheck.query.first().attempts_count == 3
    assert solved_counts_by_user()[test_user.id] == 1
    assert task_counts_by_user(checked=True)[test_user.id] == 1
