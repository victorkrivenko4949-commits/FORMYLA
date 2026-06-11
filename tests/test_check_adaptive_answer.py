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


def test_correct_answer_score_1_level_up(client):
    """ТЗ FORMYLA: верный ответ + полное решение → score=2, уровень повышается."""
    mock_return = {
        "score": 1.0,
        "feedback": "✅ Всё верно!",
        "category": "correct",
        "confidence": 1.0,
    }
    resp = _call_check_answer(client, "5", mock_return)
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    assert data["score"] == 2  # +2 балла (верный ответ + решение)
    assert data["new_level"] == 2  # было 1 → стало 2


def test_partial_score_score_1(client):
    """ТЗ FORMYLA: float 0.5 теперь означает верный ответ без полного обоснования → +1 балл."""
    mock_return = {
        "score": 0.5,
        "feedback": "🟡 Верный ответ, добавь обоснование для +2.",
        "category": "correct_no_justification",
        "confidence": 1.0,
    }
    resp = _call_check_answer(client, "5", mock_return)
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    # 0.5 → 1 балл (≥0.3 ветка). Уровень не меняется.
    assert data["score"] == 1
    assert data["new_level"] == 1


def test_wrong_answer_score_0_level_stable(client):
    """ТЗ FORMYLA: неверный ответ → score=0 (а не −1), уровень НЕ понижается."""
    mock_return = {
        "score": -1.0,  # legacy float value — мапится в 0 на новой шкале
        "feedback": "❌ Ответ не принят.",
        "category": "wrong_answer_wrong_method",
        "confidence": 1.0,
    }
    resp = _call_check_answer(client, "42", mock_return)
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    # По ТЗ: минимум 0, никаких −1.
    assert data["score"] == 0
    # Уровень не понижается (отрицательных оценок нет).
    assert data["new_level"] == 1


def test_correct_no_solution_score_1(client):
    """ТЗ FORMYLA: float 0.3 (верный ответ без обоснования) → +1 балл."""
    mock_return = {
        "score": 0.3,
        "feedback": "🟡 Верный ответ.",
        "category": "correct_no_justification",
        "confidence": 0.7,
    }
    resp = _call_check_answer(client, "5", mock_return)
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    assert data["score"] == 1  # +1 балл за верный ответ без решения
    assert data["new_level"] == 1


def test_low_confidence_partial_score_0(client):
    """float 0.0 (сбой AI / низкая уверенность) → score=0, уровень без изменений."""
    mock_return = {
        "score": 0.0,
        "feedback": "",
        "category": "suspicious",
        "confidence": 0.0,
    }
    resp = _call_check_answer(client, "5", mock_return)
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    assert data["score"] == 0
    assert data["new_level"] == 1  # уровень не изменился


def test_ai_down_streak_preserved(client):
    """ТЗ FORMYLA: сбой AI (legacy float=-1.0) → score=0, уровень без изменений."""
    mock_return = {
        "score": -1.0,
        "feedback": "",
        "category": "wrong_answer_wrong_method",
        "confidence": 0.0,
    }
    resp = _call_check_answer(client, "5", mock_return)
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    assert data["score"] == 0  # минимум 0
    # AI failure — уровень не трогаем
    assert data["new_level"] == 1, f"expected level unchanged, got {data['new_level']}"


def test_ai_failure_preserves_streak(client):
    """ТЗ FORMYLA: сбой AI (confidence=0.0, category='suspicious') → score=0."""
    mock_return = {
        "score": -1.0,
        "feedback": "",
        "category": "suspicious",
        "confidence": 0.0,
    }
    resp = _call_check_answer(client, "5", mock_return)
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    assert data["score"] == 0  # минимум 0
    assert data["new_level"] == 1


def test_negative_float_clipped_to_zero(client):
    """ТЗ FORMYLA: любые отрицательные float (-0.5, -1.0) → score=0."""
    mock_return = {
        "score": -0.5,
        "feedback": "❌ Неверный ответ.",
        "category": "wrong_answer_wrong_method",
        "confidence": 1.0,
    }
    resp = _call_check_answer(client, "wrong", mock_return)
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    assert data["score"] == 0  # минимум 0, никаких −1
    assert data["new_level"] == 1


def test_score_1_mid_streak_stays_unchanged(client):
    """float 0.3 при уровне>1 → score=1 (+1 балл), уровень без изменений."""
    mock_return = {
        "score": 0.3,
        "feedback": "🟡 Верный ответ.",
        "category": "correct_no_justification",
        "confidence": 0.7,
    }
    resp = _call_check_answer(client, "5", mock_return, difficulty=5, streak=3)
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    assert data["score"] == 1
    assert data["new_level"] == 5  # уровень не изменился (1-балльный ответ)


def test_rounding_float_0p3_to_1(client):
    """ТЗ FORMYLA: float 0.3 → score=1 (+1 балл), не 0."""
    mock_return = {
        "score": 0.3,
        "feedback": "🟡 Верный ответ.",
        "category": "correct_no_justification",
        "confidence": 0.7,
    }
    resp = _call_check_answer(client, "5", mock_return)
    data = resp.get_json()
    assert resp.status_code == 200, f"status_code={resp.status_code}, body={data}"
    assert data["status"] == "success"
    assert data["score"] == 1
    assert data["new_level"] == 1
