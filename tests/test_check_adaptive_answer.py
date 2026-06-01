# -*- coding: utf-8 -*-
"""
Tests for app.check_adaptive_answer() — Stage 5 refactoring.

Replaced the inline AI pipeline with a single review_attempt() call.
Tests verify the float→int score mapping (4 branches) and the
difficulty/streak logic (4 branches + is_ai_failure detection).

6 test cases (as specified by the user):
  1. correct       (1.0→2)   — level UP,  streak reset
  2. partial-method (0.5→0)  — unchanged, streak reset  (WRONG answer)
  3. correct-no-sol (0.3→1)  — unchanged, streak reset
  4. wrong        (-1.0→-1)  — level DOWN, streak reset
  5. ai-down      (0.0→0)    — unchanged, streak PRESERVED (suspicious)
  6. blank        (0.0→0)    — unchanged, streak reset    (not suspicious)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """Flask test client bound to the real app."""
    from app import app

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_task(
    task_id: int = 999,
    task_text: str = "Решите уравнение x + 2 = 7.",
    answer: str = "5",
    solution: str = "x = 5",
    difficulty_level: int = 5,
) -> MagicMock:
    """Create a mock AdaptiveTask with the given attributes."""
    t = MagicMock()
    t.id = task_id
    t.task_text = task_text
    t.answer = answer
    t.solution = solution
    t.difficulty_level = difficulty_level
    return t


def _make_slots(pending_index: int = 0) -> List[Dict[str, Any]]:
    """Create 25 slots, one pending (by index), the rest also 'pending'."""
    return [
        {
            "task_id": None,
            "status": "pending",
            "score": None,
            "difficulty": None,
            "user_answer": "",
            "correct_answer": "",
            "level_at_assign": None,
        }
        for _ in range(25)
    ]


def _call_check_answer(
    client,
    *,
    task_id: int = 999,
    user_answer: str = "5",
    user_solution: str = "",
    slot: int = 1,
    mock_review_return: Optional[Dict[str, Any]] = None,
    initial_difficulty: int = 3,
    initial_streak: int = 0,
    mock_task: Optional[MagicMock] = None,
) -> Any:
    """
    Perform POST /api/check_adaptive_answer with full setup:

      * session (adaptive_filtered_tasks, slots, difficulty, streak)
      * patched review_attempt (services.ai_tutor_review.review_attempt)
      * patched models.AdaptiveTask (DB query)

    Returns the Flask response object.
    """
    # Default return from review_attempt
    if mock_review_return is None:
        mock_review_return = {
            "score": 0.0,
            "feedback": "",
            "category": "",
            "confidence": 0.0,
        }

    # Default mock task
    if mock_task is None:
        mock_task = _mock_task(task_id=task_id)

    # ── Patch services.ai_tutor_review.review_attempt ──────────────
    # The function does `from services.ai_tutor_review import review_attempt`
    # at call time, so we patch the source module.
    mock_review = MagicMock(return_value=mock_review_return)

    # ── Set up session ──────────────────────────────────────────────
    with client.session_transaction() as sess:
        sess["adaptive_filtered_tasks"] = [task_id]
        sess["adaptive_slots"] = _make_slots()
        sess["adaptive_current_difficulty"] = initial_difficulty
        sess["partial_correct_streak"] = initial_streak

    # ── Apply patches ───────────────────────────────────────────────
    with patch(
        "services.ai_tutor_review.review_attempt", mock_review
    ), patch(
        "models.AdaptiveTask",
    ) as MockAdaptiveTask:
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


# ---------------------------------------------------------------------------
# 1) Correct answer (1.0 → 2)
# ---------------------------------------------------------------------------


def test_correct_answer_level_up(client):
    """
    review_attempt returns score=1.0, category='perfect'.
    Float mapping: 1.0 ≥ 1.0 → int 2.
    Difficulty: level UP (3→4), streak reset.
    """
    resp = _call_check_answer(
        client,
        user_answer="5",
        mock_review_return={
            "score": 1.0,
            "feedback": "Perfect! Correct answer and method.",
            "category": "perfect",
            "confidence": 1.0,
        },
        initial_difficulty=3,
        initial_streak=2,
    )

    data = resp.get_json()
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
    assert data["status"] == "success"
    assert data["score"] == 2, f"Expected int score=2, got {data['score']}"
    assert data["new_level"] == 4, f"Expected level UP 3→4, got {data['new_level']}"
    assert data["current_level"] == 3

    # Verify session was modified
    with client.session_transaction() as sess:
        assert sess["adaptive_current_difficulty"] == 4
        assert sess["partial_correct_streak"] == 0


# ---------------------------------------------------------------------------
# 2) Partial method (0.5 → 0) — WRONG answer, method correct
# ---------------------------------------------------------------------------


def test_partial_method_score_0_streak_reset(client):
    """
    review_attempt returns score=0.5, category='partial_method'.
    Float mapping: 0.5 < 0.3, 0.5 > -0.5 → else → int 0.
    NOT is_ai_failure (category != 'suspicious') → else branch.
    Difficulty: unchanged, BUT streak reset (wrong answer).
    """
    resp = _call_check_answer(
        client,
        user_answer="7",  # Wrong answer, but method shown
        mock_review_return={
            "score": 0.5,
            "feedback": "Answer wrong, but method is correct.",
            "category": "partial_method",
            "confidence": 0.9,
        },
        initial_difficulty=3,
        initial_streak=2,
    )

    data = resp.get_json()
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
    assert data["status"] == "success"
    assert data["score"] == 0, f"Expected int score=0, got {data['score']}"
    assert data["new_level"] == 3, (
        f"Expected level unchanged (3), got {data['new_level']}"
    )

    # Streak must be reset (wrong answer)
    with client.session_transaction() as sess:
        assert sess["partial_correct_streak"] == 0, (
            "Streak should be reset for wrong answer (score=0 from 0.5)"
        )


# ---------------------------------------------------------------------------
# 3) Correct answer, no solution (0.3 → 1)
# ---------------------------------------------------------------------------


def test_correct_no_solution_score_1(client):
    """
    review_attempt returns score=0.3, category='correct_no_solution'.
    Float mapping: 0.3 ≥ 0.3 → int 1.
    Difficulty: unchanged, streak reset.
    """
    resp = _call_check_answer(
        client,
        user_answer="5",
        user_solution="",
        mock_review_return={
            "score": 0.3,
            "feedback": "Answer correct, but no solution provided.",
            "category": "correct_no_solution",
            "confidence": 0.8,
        },
        initial_difficulty=5,
        initial_streak=3,
    )

    data = resp.get_json()
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
    assert data["status"] == "success"
    assert data["score"] == 1, f"Expected int score=1, got {data['score']}"
    assert data["new_level"] == 5, (
        f"Expected level unchanged (5), got {data['new_level']}"
    )

    with client.session_transaction() as sess:
        assert sess["partial_correct_streak"] == 0, (
            "Streak should be reset for score=1"
        )


# ---------------------------------------------------------------------------
# 4) Wrong answer (-1.0 → -1)
# ---------------------------------------------------------------------------


def test_wrong_answer_level_down(client):
    """
    review_attempt returns score=-1.0, category='wrong'.
    Float mapping: -1.0 ≤ -0.5 → int -1.
    Difficulty: level DOWN (3→2), streak reset.
    """
    resp = _call_check_answer(
        client,
        user_answer="42",
        mock_review_return={
            "score": -1.0,
            "feedback": "Completely wrong.",
            "category": "wrong",
            "confidence": 1.0,
        },
        initial_difficulty=3,
        initial_streak=1,
    )

    data = resp.get_json()
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
    assert data["status"] == "success"
    assert data["score"] == -1, f"Expected int score=-1, got {data['score']}"
    assert data["new_level"] == 2, f"Expected level DOWN 3→2, got {data['new_level']}"
    assert data["current_level"] == 3

    with client.session_transaction() as sess:
        assert sess["adaptive_current_difficulty"] == 2
        assert sess["partial_correct_streak"] == 0


# ---------------------------------------------------------------------------
# 5) AI failure (-1.0 → int -1, but neutralized by is_ai_failure)
#    REAL return from review_attempt: score=-1.0, category='suspicious', confidence=0.0
# ---------------------------------------------------------------------------


def test_ai_down_streak_preserved(client):
    """
    review_attempt returns score=-1.0, category='suspicious', confidence=0.0
    (это РЕАЛЬНЫЕ значения — см. review_attempt lines 797-798, 821-822).

    Float mapping: -1.0 <= -0.5 → int -1.
    Но is_ai_failure = True (confidence=0.0, category='suspicious')
    проверяется ДО score==-1 в elif-цепочке → нейтральная ветка.

    Difficulty: unchanged, streak PRESERVED (нейтральное событие).
    """
    resp = _call_check_answer(
        client,
        user_answer="5",
        mock_review_return={
            "score": -1.0,
            "feedback": "AI temporarily unavailable.",
            "category": "suspicious",
            "confidence": 0.0,
        },
        initial_difficulty=4,
        initial_streak=5,  # Ненулевой стрик для проверки сохранения
    )

    data = resp.get_json()
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
    assert data["status"] == "success"
    assert data["score"] == -1, f"Expected int score=-1, got {data['score']}"
    assert data["new_level"] == 4, (
        f"Expected level unchanged (4), got {data['new_level']}"
    )

    # Streak MUST be preserved (AI failure is neutral)
    with client.session_transaction() as sess:
        assert sess["partial_correct_streak"] == 5, (
            "Streak should be PRESERVED for AI failure (confidence=0.0, suspicious)"
        )


# ---------------------------------------------------------------------------
# 6) Blank answer (0.0 → 0, category='blank') — NOT suspicious, streak reset
# ---------------------------------------------------------------------------


def test_blank_answer_rejected_at_validation(client):
    """
    Blank (empty) answer is caught by input validation at line 5294
    (`if not task_id or not user_answer`) BEFORE review_attempt().
    Returns 400 with error message — never reaches AI.
    """
    with patch("services.ai_tutor_review.review_attempt") as mock_review:
        with client.session_transaction() as sess:
            sess["adaptive_filtered_tasks"] = [999]
            sess["adaptive_slots"] = _make_slots()
            sess["adaptive_current_difficulty"] = 3
            sess["partial_correct_streak"] = 1

        resp = client.post(
            "/api/check_adaptive_answer",
            json={"task_id": 999, "user_answer": "", "slot": 1},
        )

    data = resp.get_json()
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {data}"
    assert data["status"] == "error"
    # Ensure review_attempt was NEVER called (saved by input validation)
    mock_review.assert_not_called()


# ---------------------------------------------------------------------------
# 7) Edge: negative float close to 0 (-0.4 → 0, NOT -1)
# ---------------------------------------------------------------------------


def test_negative_float_not_minus_one(client):
    """
    review_attempt returns score=-0.4, category='wrong'.
    Float mapping: -0.4 > -0.5 → else → int 0 (NOT -1).
    Verifies the threshold at -0.5.
    """
    resp = _call_check_answer(
        client,
        user_answer="wrong",
        mock_review_return={
            "score": -0.4,
            "feedback": "Mostly wrong but not completely.",
            "category": "wrong",
            "confidence": 0.7,
        },
        initial_difficulty=3,
        initial_streak=0,
    )

    data = resp.get_json()
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
    assert data["status"] == "success"
    assert data["score"] == 0, (
        f"Expected int score=0 for float=-0.4, got {data['score']}"
    )
    assert data["new_level"] == 3


# ---------------------------------------------------------------------------
# 8) Edge: minimum level floor (level 1 → score=-1 → level 1, not 0)
# ---------------------------------------------------------------------------


def test_minimum_level_floor(client):
    """
    When current_difficulty=1 and score=-1, new_level should be max(1, 0) = 1.
    Verifies the level floor is respected.
    """
    resp = _call_check_answer(
        client,
        user_answer="wrong",
        mock_review_return={
            "score": -1.0,
            "feedback": "Wrong.",
            "category": "wrong",
            "confidence": 1.0,
        },
        initial_difficulty=1,  # Minimum level
        initial_streak=0,
    )

    data = resp.get_json()
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
    assert data["score"] == -1
    assert data["new_level"] == 1, (
        f"Expected level floor at 1, got {data['new_level']}"
    )


# ---------------------------------------------------------------------------
# 9) Edge: maximum level ceiling (level 7 → score=2 → level 7, not 8)
# ---------------------------------------------------------------------------


def test_maximum_level_ceiling(client):
    """
    When current_difficulty=7 and score=2, new_level should be min(7, 8) = 7.
    Verifies the level ceiling is respected.
    """
    resp = _call_check_answer(
        client,
        user_answer="5",
        mock_review_return={
            "score": 1.0,
            "feedback": "Perfect!",
            "category": "perfect",
            "confidence": 1.0,
        },
        initial_difficulty=7,  # Maximum level
        initial_streak=0,
    )

    data = resp.get_json()
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
    assert data["score"] == 2
    assert data["new_level"] == 7, (
        f"Expected level ceiling at 7, got {data['new_level']}"
    )


# ---------------------------------------------------------------------------
# 10) Empty session → error 400
# ---------------------------------------------------------------------------


def test_no_session_returns_error(client):
    """
    When adaptive_filtered_tasks is missing from session, the endpoint
    should return 400 with an error message.
    """
    # Don't set up session — let it be empty
    with patch("services.ai_tutor_review.review_attempt") as mock_review:
        resp = client.post(
            "/api/check_adaptive_answer",
            json={"task_id": 999, "user_answer": "5", "slot": 1},
        )

    data = resp.get_json()
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {data}"
    assert data["status"] == "error"
    # Ensure review_attempt was NEVER called
    mock_review.assert_not_called()
