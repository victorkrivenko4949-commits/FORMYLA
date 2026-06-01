# -*- coding: utf-8 -*-
"""
Tests for services/ai_tutor_review.py — the AI tutor review pipeline.

Covers 5 scenarios:
  1. blank answer      → score=0.0, category="blank"
  2. sympy-correct     → sympy matches, fast-path return
  3. sympy-wrong + AI unavailable → score=-1.0, elseif branch
  4. AI-correct        → mocked DeepSeek says correct
  5. AI-wrong          → mocked DeepSeek says wrong

These are pure unit tests — no DB, no actual API calls.
"""

import json
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from services.ai_tutor_review import (
    _compute_score,
    _pick_category,
    review_attempt,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_review(
    *,
    user_answer: str = "5",
    correct_answer: str = "5",
    solution_ref: str = "",
    user_solution: str = "",
    difficulty_level: int = 5,
    deepseek_available: bool = True,
    deepseek_client_cls: Any = None,
    **kwargs,
) -> Dict[str, Any]:
    """Thin wrapper to reduce boilerplate in tests."""
    return review_attempt(
        task_text="Решите уравнение x + 2 = 7.",
        correct_answer=correct_answer,
        solution_ref=solution_ref,
        user_answer=user_answer,
        user_solution=user_solution,
        difficulty_level=difficulty_level,
        deepseek_available=deepseek_available,
        deepseek_client_cls=deepseek_client_cls,
        **kwargs,
    )


def _mock_deepseek(json_payload: dict) -> type:
    """Build a mock *class* whose .generate() returns a JSON string."""
    raw = json.dumps(json_payload, ensure_ascii=False)
    instance = MagicMock()
    instance.generate.return_value = raw
    cls = MagicMock()
    cls.return_value = instance
    return cls


# ---------------------------------------------------------------------------
# 1) Blank answer
# ---------------------------------------------------------------------------

def test_blank_answer():
    """Empty / whitespace-only answer → score=0.0, category='blank'."""
    result = _call_review(user_answer="")
    assert result["score"] == 0.0
    assert result["is_correct"] is False
    assert result["category"] == "blank"
    assert result["answer_correct"] is False
    assert result["method_correct"] is False
    assert result["confidence"] == 1.0
    assert result["error_location"] is None
    assert result["needs_escalation"] is False

    # Whitespace-only also counts as blank
    result2 = _call_review(user_answer="   ")
    assert result2["score"] == 0.0
    assert result2["category"] == "blank"


# ---------------------------------------------------------------------------
# 2) Sympy-correct fast path
# ---------------------------------------------------------------------------

@patch("services.ai_tutor_review._HAS_SYMPY", True)
@patch("services.ai_tutor_review._compare_with_sympy")
def test_sympy_correct_with_solution(mock_compare):
    """sympy confirms answer correct, user provided solution → score=1.0."""
    mock_compare.return_value = (True, False)  # (is_correct, needs_ai)
    result = _call_review(
        user_answer="5",
        correct_answer="5",
        user_solution="x = 7 - 2 = 5",
        difficulty_level=5,
    )
    assert result["score"] == 1.0
    assert result["is_correct"] is True
    assert result["answer_correct"] is True
    assert result["method_correct"] is True
    assert result["category"] == "correct"
    assert result["confidence"] == 1.0
    assert result["needs_escalation"] is False


@patch("services.ai_tutor_review._HAS_SYMPY", True)
@patch("services.ai_tutor_review._compare_with_sympy")
def test_sympy_correct_no_solution_high_level(mock_compare):
    """sympy confirms correct, but no solution + level=7 → score=0.3, category='suspicious'."""
    mock_compare.return_value = (True, False)
    result = _call_review(
        user_answer="5",
        correct_answer="5",
        user_solution="",
        difficulty_level=7,
    )
    # correct answer without justification at level>=7 → 0.3
    assert result["score"] == 0.3
    assert result["is_correct"] is False   # 0.3 < 0.5
    assert result["answer_correct"] is True
    assert result["method_correct"] is True
    assert result["category"] == "suspicious"
    # No AI was called, so no escalation needed
    assert result["needs_escalation"] is False


# ---------------------------------------------------------------------------
# 3) Sympy-wrong + AI unavailable
# ---------------------------------------------------------------------------

@patch("services.ai_tutor_review._HAS_SYMPY", True)
@patch("services.ai_tutor_review._compare_with_sympy")
def test_sympy_wrong_ai_unavailable(mock_compare):
    """sympy says answer is wrong, AI not available → score=-1.0."""
    mock_compare.return_value = (False, False)  # (is_correct=False, needs_ai=False)
    result = _call_review(
        user_answer="42",
        correct_answer="5",
        user_solution="",
        deepseek_available=False,
        deepseek_client_cls=None,
        difficulty_level=5,
    )
    # sympy determined wrong → answer_correct=False, method_correct=False → -1.0
    assert result["score"] == -1.0
    assert result["is_correct"] is False
    assert result["answer_correct"] is False
    assert result["method_correct"] is False
    assert result["category"] == "wrong_answer_wrong_method"
    assert result["confidence"] == 0.0
    assert result["needs_escalation"] is False
    # Should mention "AI-проверка временно недоступна"
    assert "временно недоступна" in result["feedback"]


# ---------------------------------------------------------------------------
# 4) AI-correct (mocked)
# ---------------------------------------------------------------------------

@patch("services.ai_tutor_review._HAS_SYMPY", False)
@patch("services.ai_tutor_review.math_equivalent", return_value=False)
def test_ai_correct(mock_math):
    """AI returns answer_correct=true, method_correct=true → score=1.0."""
    mock_ai = _mock_deepseek({
        "answer_correct": True,
        "method_correct": True,
        "confidence": 0.95,
        "error_location": None,
        "feedback": "Отличное решение! Всё верно.",
    })
    result = _call_review(
        user_answer="5",
        correct_answer="5",
        user_solution="x = 7 - 2, x = 5",
        deepseek_client_cls=mock_ai,
        difficulty_level=5,
    )
    assert result["score"] == 1.0
    assert result["is_correct"] is True
    assert result["answer_correct"] is True
    assert result["method_correct"] is True
    assert result["confidence"] == 0.95
    assert result["needs_escalation"] is False
    assert "Отличное" in result["feedback"]


def test_ai_correct_low_confidence_escalation():
    """AI returns low confidence on a proof task at level 7 → needs_escalation=True."""
    mock_ai = _mock_deepseek({
        "answer_correct": True,
        "method_correct": True,
        "confidence": 0.5,
        "error_location": None,
        "feedback": "Похоже на правду, но не уверен.",
    })
    # proof_mode is auto-detected; use a task_text that triggers proof detection
    result = review_attempt(
        task_text="Докажите, что число 5 является корнем уравнения x + 2 = 7.",
        correct_answer="5",
        solution_ref="",
        user_answer="5",
        user_solution="подстановка x=5: 5+2=7, верно",
        deepseek_client_cls=mock_ai,
        difficulty_level=7,
    )
    # confidence=0.5 < 0.6 AND proof_mode AND level>=7 → needs_escalation
    assert result["needs_escalation"] is True
    assert result["is_correct"] is True  # score >= 0.5


# ---------------------------------------------------------------------------
# 5) AI-wrong (mocked)
# ---------------------------------------------------------------------------

def test_ai_wrong():
    """AI returns answer_correct=false, method_correct=false → score=-1.0."""
    mock_ai = _mock_deepseek({
        "answer_correct": False,
        "method_correct": False,
        "confidence": 0.9,
        "error_location": "Ошибка в раскрытии скобок",
        "feedback": "Неправильно. Начни заново.",
    })
    result = _call_review(
        user_answer="7",
        correct_answer="5",
        user_solution="x = 7 + 2",
        deepseek_client_cls=mock_ai,
        difficulty_level=5,
    )
    assert result["score"] == -1.0
    assert result["is_correct"] is False
    assert result["answer_correct"] is False
    assert result["method_correct"] is False
    assert result["category"] == "wrong_answer_wrong_method"
    assert result["error_location"] == "Ошибка в раскрытии скобок"
    assert result["needs_escalation"] is False


def test_ai_wrong_good_method():
    """AI says answer wrong but method correct → score=0.5."""
    mock_ai = _mock_deepseek({
        "answer_correct": False,
        "method_correct": True,
        "confidence": 0.85,
        "error_location": "Арифметическая ошибка",
        "feedback": "Ход мыслей верный, но в вычислениях ошибка.",
    })
    result = _call_review(
        user_answer="6",
        correct_answer="5",
        user_solution="x = 7 - 2 = 6",
        deepseek_client_cls=mock_ai,
        difficulty_level=5,
    )
    assert result["score"] == 0.5
    assert result["is_correct"] is True  # 0.5 >= 0.5
    assert result["answer_correct"] is False
    assert result["method_correct"] is True
    assert result["category"] == "wrong_answer_good_method"


# ---------------------------------------------------------------------------
# Unit tests for _compute_score
# ---------------------------------------------------------------------------

class TestComputeScore:
    """Direct unit tests for the scoring function."""

    def test_wrong_answer_wrong_method(self):
        assert _compute_score(answer_correct=False, method_correct=False, has_solution=False, difficulty_level=5) == -1.0

    def test_wrong_answer_good_method(self):
        assert _compute_score(answer_correct=False, method_correct=True, has_solution=False, difficulty_level=5) == 0.5

    def test_correct_with_solution(self):
        assert _compute_score(answer_correct=True, method_correct=True, has_solution=True, difficulty_level=5) == 1.0

    def test_correct_no_solution_low_level(self):
        assert _compute_score(answer_correct=True, method_correct=True, has_solution=False, difficulty_level=4) == 1.0

    def test_correct_no_solution_mid_level(self):
        assert _compute_score(answer_correct=True, method_correct=True, has_solution=False, difficulty_level=5) == 0.5
        assert _compute_score(answer_correct=True, method_correct=True, has_solution=False, difficulty_level=6) == 0.5

    def test_correct_no_solution_high_level(self):
        assert _compute_score(answer_correct=True, method_correct=True, has_solution=False, difficulty_level=7) == 0.3
        assert _compute_score(answer_correct=True, method_correct=True, has_solution=False, difficulty_level=8) == 0.3


# ---------------------------------------------------------------------------
# Unit tests for _pick_category
# ---------------------------------------------------------------------------

class TestPickCategory:
    """Direct unit tests for the category picker."""

    def test_blank(self):
        assert _pick_category(answer_correct=False, method_correct=False, has_solution=False, difficulty_level=5, score=0.0) == "blank"

    def test_correct(self):
        assert _pick_category(answer_correct=True, method_correct=True, has_solution=True, difficulty_level=5, score=1.0) == "correct"

    def test_correct_no_justification(self):
        assert _pick_category(answer_correct=True, method_correct=True, has_solution=False, difficulty_level=5, score=0.5) == "correct_no_justification"

    def test_suspicious(self):
        assert _pick_category(answer_correct=True, method_correct=True, has_solution=False, difficulty_level=7, score=0.3) == "suspicious"

    def test_wrong_answer_good_method(self):
        assert _pick_category(answer_correct=False, method_correct=True, has_solution=False, difficulty_level=5, score=0.5) == "wrong_answer_good_method"

    def test_wrong_answer_wrong_method(self):
        assert _pick_category(answer_correct=False, method_correct=False, has_solution=False, difficulty_level=5, score=-1.0) == "wrong_answer_wrong_method"
