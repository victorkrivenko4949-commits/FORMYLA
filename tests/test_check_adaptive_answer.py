# -*- coding: utf-8 -*-
"""Tests for app.check_adaptive_answer() — scoring, difficulty, streak logic."""

import json
from unittest.mock import MagicMock, patch

import pytest


# ── Helper ──────────────────────────────────────────────────────────────

def _call_check_answer(client, user_answer, mock_review_return,
                       user_solution="", slot=0, task_id=1,
                       difficulty=1, streak=0):
    """Simulate a POST to /api/check_adaptive_answer with given patches.

    Also patches the local answer checker (check_answer) so it returns
    (False, "parse_error") — forcing the AI review path to be exercised.

    Parameters
    ----------
    client : Flask test client
    user_answer : str
    mock_review_return : dict
        The return value for the mocked review_attempt.
    user_solution : str
    slot : int
    task_id : int
    difficulty : int
        Initial adaptive_current_difficulty (default 1).
    streak : int
        Initial partial_correct_streak (default 0).
    """
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.answer = "5"
    mock_task.difficulty = 1
    mock_task.difficulty_level = 1
    mock_task.topic = "algebra"
    mock_task.solution = "x = 5"
    mock_task.task_text = "Solve for x: 2x + 3 = 13"

    mock_review = MagicMock(return_value=mock_review_return)
    mock_checker = MagicMock(return_value=(False, "parse_error"))

    # ── Initialise adaptive test session ────────────────────────────
    # The check_adaptive_answer endpoint requires these session keys.
    with client.session_transaction() as sess:
        sess["adaptive_filtered_tasks"] = [task_id]
        sess["adaptive_current_difficulty"] = difficulty
        sess["partial_correct_streak"] = streak
        # adaptive_slots will be lazy-initialised by _adaptive_get_slots()

    # ── Apply patches ───────────────────────────────────────────────
    # Also patch the local answer checker so it falls through to AI
    with patch(
        "services.ai_tutor_review.review_attempt", mock_review
    ), patch(
        "models.AdaptiveTask",
    ) as MockAdaptiveTask, patch(
        "services.answer_checker.check_answer", mock_checker
    ):
        MockAdaptiveTask.query.get.return_value = mock_task

        resp = client.post(
            "/api/check_adaptive_answer",
            json={
                "task_id": task_id,
                "user_answer": user_answer,
                "user_solution": user_solution,
                "slot": slot,
            },
        )

    return resp


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Return a Flask test client for the main app.

    Creates a test user (id=999) in the DB if not present, and sets up the
    Flask-Login session so that require_registration() passes.
    """
    from app import app as flask_app
    from models import db, User

    flask_app.config["TESTING"] = True

    with flask_app.app_context():
        # Ensure a non-guest test user exists for Flask-Login
        user = db.session.get(User, 999)
        if not user:
            user = User(
                id=999,
                email="test_check_adaptive@formyla.local",
                nickname="test_adaptive_user",
                is_guest=False,
            )
            db.session.add(user)
            db.session.commit()

    with flask_app.test_client() as c:
        with c.session_transaction() as sess:
            # Flask-Login reads _user_id from session to load current_user
            sess["_user_id"] = "999"
            sess["_fresh"] = True
            sess["user_id"] = 999
            sess["_id"] = "test-session-999"
            sess["device_id"] = "test-device-999"
        yield c


# ═══════════════════════════════════════════════════════════════════════════

# ── Tests ─────────────────────────────────────────────────────────────────


# ═════════════════════════════════════════════════════════════════════════
# FORMYLA v2 scale (since commit "scoring v2"):
#   answer_correct=True,  method_correct=True/None      → score=+1, level+1
#   answer_correct=True,  method_correct=False (с реш.) → score= 0, level=ст.
#   answer_correct=False, method_correct=True  (с реш.) → score= 0, level=ст.
#   answer_correct=False, method_correct=False/None    → score=-1, level-1
#   answer_correct=None (AI failure / суждение неясно)  → score= 0, level=ст.
# Уровень clamped to [1, 7].
# ═════════════════════════════════════════════════════════════════════════


def test_correct_answer_level_up(client):
    """ТЗ FORMYLA v2: верный ответ + верный метод → +1 балл, уровень +1."""
    mock_return = {
        "score": 1.0,
        "feedback": "✅ Всё верно!",
        "category": "correct",
        "confidence": 1.0,
        "answer_correct": True,
        "method_correct": True,
    }
    resp = _call_check_answer(client, "5", mock_return)
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    assert data["score"] == 1  # +1 балл
    assert data["new_level"] == 2  # было 1 → стало 2


def test_correct_answer_wrong_method_neutral(client):
    """ТЗ FORMYLA v2: верный ответ + неверный метод → 0 баллов, уровень не меняется."""
    mock_return = {
        "score": 0.5,
        "feedback": "🟡 Ответ верный, но метод не тот.",
        "category": "correct_no_justification",
        "confidence": 1.0,
        "answer_correct": True,
        "method_correct": False,
    }
    resp = _call_check_answer(client, "5", mock_return, user_solution="неверное решение")
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    assert data["score"] == 0  # ответ верен, но метод неверный — нейтрально
    assert data["new_level"] == 1


def test_wrong_answer_full_negative(client):
    """ТЗ FORMYLA v2: неверный ответ + неверный метод → -1 балл, уровень -1.

    На level=1 уровень clamp'ится снизу — остаётся 1.
    """
    mock_return = {
        "score": -1.0,
        "feedback": "❌ Ответ не принят.",
        "category": "wrong_answer_wrong_method",
        "confidence": 1.0,
        "answer_correct": False,
        "method_correct": False,
    }
    resp = _call_check_answer(client, "42", mock_return)
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    assert data["score"] == -1
    # current=1, delta=-1, clamp → max(1, 0) = 1
    assert data["new_level"] == 1


def test_wrong_answer_level_down_from_5(client):
    """ТЗ FORMYLA v2: неверный ответ на уровне 5 → score=-1, уровень 5→4."""
    mock_return = {
        "score": -1.0,
        "feedback": "❌ Неверно.",
        "category": "wrong_answer_wrong_method",
        "confidence": 1.0,
        "answer_correct": False,
        "method_correct": False,
    }
    resp = _call_check_answer(client, "wrong", mock_return, difficulty=5)
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["score"] == -1
    assert data["new_level"] == 4


def test_correct_answer_no_solution_level_up(client):
    """ТЗ FORMYLA v2: только ответ (без решения), ответ верный → +1 балл, +1 уровень."""
    mock_return = {
        "score": 0.3,
        "feedback": "🟡 Верный ответ.",
        "category": "correct_no_justification",
        "confidence": 0.7,
        "answer_correct": True,
        "method_correct": None,  # без решения метод не оценивается
    }
    resp = _call_check_answer(client, "5", mock_return, user_solution="")
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    assert data["score"] == 1
    assert data["new_level"] == 2


def test_wrong_answer_good_method_neutral(client):
    """ТЗ FORMYLA v2: ответ неверный, но метод понят правильно → 0 баллов, уровень не меняется."""
    mock_return = {
        "score": 0.0,
        "feedback": "🟡 Метод верный, но ответ не сошёлся.",
        "category": "wrong_answer_good_method",
        "confidence": 0.9,
        "answer_correct": False,
        "method_correct": True,
    }
    resp = _call_check_answer(client, "wrong", mock_return, user_solution="правильное решение")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["score"] == 0
    assert data["new_level"] == 1  # без изменений


def test_ai_failure_neutral(client):
    """ТЗ FORMYLA v2: сбой AI (answer_correct=None) → 0 баллов, уровень не меняется."""
    mock_return = {
        "score": 0.0,
        "feedback": "",
        "category": "suspicious",
        "confidence": 0.0,
        "answer_correct": None,
        "method_correct": None,
    }
    resp = _call_check_answer(client, "5", mock_return)
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["score"] == 0
    assert data["new_level"] == 1
